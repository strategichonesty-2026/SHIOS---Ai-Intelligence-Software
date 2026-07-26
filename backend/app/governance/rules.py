"""Governance as code.

Section 9 of the specification is implemented here as a set of pure functions plus a single
`enforce()` entry point. Agents call `check_*` before writing. Nothing gets published that
fails a HARD rule; SOFT findings are recorded as issues on the ValidationResult.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.config import settings

HARD = "hard"
SOFT = "soft"


class GovernanceError(ValueError):
    """Raised when a HARD governance rule is violated."""


@dataclass
class RuleFinding:
    rule: str
    severity: str
    message: str


@dataclass
class GovernanceReport:
    findings: list[RuleFinding] = field(default_factory=list)

    @property
    def hard_failures(self) -> list[RuleFinding]:
        return [f for f in self.findings if f.severity == HARD]

    @property
    def is_valid(self) -> bool:
        return not self.hard_failures

    @property
    def messages(self) -> list[str]:
        return [f"[{f.severity}] {f.rule}: {f.message}" for f in self.findings]

    def add(self, rule: str, severity: str, message: str) -> None:
        self.findings.append(RuleFinding(rule=rule, severity=severity, message=message))


# --- individual rules ------------------------------------------------------


def check_confidence(value: float, report: GovernanceReport) -> None:
    if not 0.0 <= value <= 1.0:
        report.add("CONFIDENCE_RANGE", HARD, f"confidence {value} outside 0.0-1.0")
    elif value < settings.min_confidence:
        report.add("CONFIDENCE_FLOOR", SOFT, f"confidence {value:.2f} below reporting floor")


def check_evidence_count(evidence_ids: list[str], minimum: int, report: GovernanceReport) -> None:
    unique = {e for e in evidence_ids if e}
    if len(unique) < minimum:
        report.add(
            "MIN_EVIDENCE",
            HARD,
            f"{len(unique)} evidence id(s) supplied, minimum is {minimum}",
        )


def check_review_window(review_date: date, created: date, report: GovernanceReport) -> None:
    if review_date is None:
        report.add("REVIEW_DATE_REQUIRED", HARD, "prediction has no review_date")
        return
    horizon_days = (review_date - created).days
    if horizon_days <= 0:
        report.add("REVIEW_DATE_FUTURE", HARD, "review_date must be after creation date")
    elif horizon_days > settings.max_prediction_review_days:
        report.add(
            "REVIEW_WINDOW",
            HARD,
            f"review_date is {horizon_days}d out, limit is {settings.max_prediction_review_days}d",
        )


def check_expiration(expiration_date: date, review_date: date, report: GovernanceReport) -> None:
    if expiration_date is None:
        report.add("EXPIRATION_REQUIRED", HARD, "prediction has no expiration_date")
    elif review_date and expiration_date < review_date:
        report.add("EXPIRATION_ORDER", HARD, "expiration_date precedes review_date")


def check_traceability(refs: dict[str, list[str] | str | None], report: GovernanceReport) -> None:
    """Truth Maintenance System: every link in the chain must be present."""
    for label, value in refs.items():
        empty = value is None or (isinstance(value, list) and len(value) == 0) or value == ""
        if empty:
            report.add("TRACEABILITY", HARD, f"missing required reference: {label}")


def check_sample_size(sample_size: int, minimum: int, report: GovernanceReport) -> None:
    if sample_size < minimum:
        report.add(
            "SAMPLE_SIZE",
            SOFT,
            f"only {sample_size} observation period(s); treat direction as provisional",
        )


# --- composite entry points ------------------------------------------------


def evaluate_prediction(
    *,
    confidence: float,
    supporting_evidence_ids: list[str],
    trend_ids: list[str],
    review_date: date,
    expiration_date: date,
    created_on: date,
    periods_observed: int,
) -> GovernanceReport:
    report = GovernanceReport()
    check_confidence(confidence, report)
    check_evidence_count(supporting_evidence_ids, 1, report)
    check_traceability({"trend_ids": trend_ids}, report)
    check_review_window(review_date, created_on, report)
    check_expiration(expiration_date, review_date, report)
    check_sample_size(periods_observed, settings.min_periods_for_prediction, report)
    return report


def evaluate_recommendation(
    *,
    confidence: float,
    evidence_ids: list[str],
    trend_ids: list[str],
    prediction_id: str | None,
    text: str,
) -> GovernanceReport:
    report = GovernanceReport()
    check_confidence(confidence, report)
    check_evidence_count(evidence_ids, settings.min_evidence_per_recommendation, report)
    if not trend_ids and not prediction_id:
        report.add(
            "TRACEABILITY",
            HARD,
            "recommendation must reference at least one trend or prediction",
        )
    if len(text.strip()) < 20:
        report.add("SUBSTANCE", HARD, "recommendation text is too thin to act on")
    return report


def enforce(report: GovernanceReport, context: str) -> None:
    if not report.is_valid:
        raise GovernanceError(f"{context} rejected by governance: " + "; ".join(report.messages))


def default_review_dates(created_on: date, horizon_days: int) -> tuple[date, date]:
    """Clamp any requested horizon into the governance window."""
    horizon_days = max(7, min(horizon_days, settings.max_prediction_review_days))
    review = created_on + timedelta(days=horizon_days)
    expiration = review + timedelta(days=7)
    return review, expiration
