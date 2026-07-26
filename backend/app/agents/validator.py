"""5.7 Strategic Honesty Validator.

The one agent whose job is to say "we do not know". It re-checks published artefacts against
the governance rules, verifies that every referenced id actually resolves, looks for
contradictory evidence, and names the unknowns explicitly.

A recommendation that fails validation is set to `needs_review`, not deleted. Deleting the
record would destroy the audit trail, which is the opposite of the point.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import Agent
from app.events.bus import bus
from app.events.types import EventName
from app.governance.rules import evaluate_prediction, evaluate_recommendation
from app.models.tables import Evidence, Prediction, Recommendation, Trend, ValidationResult
from app.services.periods import period_start_date


class StrategicHonestyValidator(Agent):
    name = "strategic_honesty_validator"
    supports_decision = "Is this artefact safe to act on, and what does it not know?"
    requires_evidence = "The artefact's own references; all must resolve to live rows."
    confidence_method = "Binary validity plus an explicit list of unknowns. No score is invented."
    correctness_check = "Validation is re-run on every pipeline pass; results are versioned rows."
    success_metric = "No artefact reaches an audience with an unresolved HARD finding."
    human_review = "outputs marked needs_review require a human decision"

    def execute(self, session: Session, **kwargs: Any) -> dict[str, Any]:
        prediction_ids: list[str] | None = kwargs.get("prediction_ids")
        recommendation_ids: list[str] | None = kwargs.get("recommendation_ids")

        results: list[str] = []
        invalid = 0

        predictions = self._load(session, Prediction, prediction_ids, Prediction.status == "published")
        for prediction in predictions:
            report = evaluate_prediction(
                confidence=prediction.confidence,
                supporting_evidence_ids=prediction.supporting_evidence_ids or [],
                trend_ids=prediction.trend_ids or [],
                review_date=prediction.review_date,
                expiration_date=prediction.expiration_date,
                created_on=period_start_date(_anchor_period(prediction)),
                periods_observed=len(prediction.trend_ids or []),
            )
            missing = self._missing_refs(session, prediction)
            for ref in missing:
                report.add("DANGLING_REFERENCE", "hard", f"reference does not resolve: {ref}")
            unknowns = self._prediction_unknowns(prediction)

            record = ValidationResult(
                target_type="prediction",
                target_id=prediction.id,
                is_valid=report.is_valid,
                issues=report.messages,
                missing_evidence=missing,
                contradictory_evidence=[],
                unknowns_noted=unknowns,
            )
            session.add(record)
            session.flush()
            results.append(record.id)
            if not report.is_valid:
                invalid += 1
                prediction.status = "needs_review"

        recommendations = self._load(
            session, Recommendation, recommendation_ids, Recommendation.status.in_(["draft", "approved"])
        )
        for recommendation in recommendations:
            report = evaluate_recommendation(
                confidence=recommendation.confidence,
                evidence_ids=recommendation.evidence_ids or [],
                trend_ids=recommendation.trend_ids or [],
                prediction_id=recommendation.prediction_id,
                text=recommendation.recommendation_text,
            )
            missing = self._missing_refs(session, recommendation)
            for ref in missing:
                report.add("DANGLING_REFERENCE", "hard", f"reference does not resolve: {ref}")
            contradictions = self._contradictions(session, recommendation)
            for note in contradictions:
                report.add("CONTRADICTORY_EVIDENCE", "soft", note)

            record = ValidationResult(
                target_type="recommendation",
                target_id=recommendation.id,
                is_valid=report.is_valid,
                issues=report.messages,
                missing_evidence=missing,
                contradictory_evidence=contradictions,
                unknowns_noted=self._recommendation_unknowns(recommendation),
            )
            session.add(record)
            session.flush()
            results.append(record.id)
            recommendation.status = "validated" if report.is_valid else "needs_review"
            if not report.is_valid:
                invalid += 1
            bus.publish(
                EventName.RECOMMENDATION_VALIDATED,
                {"recommendation_id": recommendation.id, "is_valid": report.is_valid},
                session,
            )

        session.flush()
        return {"validations": len(results), "validation_ids": results, "invalid": invalid}

    # -- helpers ------------------------------------------------------------

    def _load(self, session: Session, model, ids: list[str] | None, default_filter):
        query = select(model)
        query = query.where(model.id.in_(ids)) if ids else query.where(default_filter)
        return list(session.scalars(query.limit(500)))

    def _missing_refs(self, session: Session, artefact) -> list[str]:
        missing: list[str] = []
        evidence_ids = list(
            getattr(artefact, "supporting_evidence_ids", None) or getattr(artefact, "evidence_ids", []) or []
        )
        if evidence_ids:
            found = set(session.scalars(select(Evidence.id).where(Evidence.id.in_(evidence_ids))))
            missing += [f"evidence:{e}" for e in evidence_ids if e not in found]
        trend_ids = list(getattr(artefact, "trend_ids", []) or [])
        if trend_ids:
            found_trends = set(session.scalars(select(Trend.id).where(Trend.id.in_(trend_ids))))
            missing += [f"trend:{t}" for t in trend_ids if t not in found_trends]
        prediction_id = getattr(artefact, "prediction_id", None)
        if prediction_id and not session.get(Prediction, prediction_id):
            missing.append(f"prediction:{prediction_id}")
        return missing[:20]

    def _contradictions(self, session: Session, recommendation: Recommendation) -> list[str]:
        """Flag when the underlying series moved against the recommendation's direction."""
        trends = list(session.scalars(select(Trend).where(Trend.id.in_(recommendation.trend_ids or []))))
        trends.sort(key=lambda t: t.period)
        if len(trends) < 2:
            return []
        recent = trends[-2:]
        text = recommendation.recommendation_text.lower()
        claims_growth = "rising" in text or "build" in text or "fund" in text
        actual_down = all(t.direction == "down" for t in recent)
        if claims_growth and actual_down:
            return [
                f"Last two observed periods for {trends[-1].entity_name} moved down "
                f"({recent[0].value:.0f} then {recent[1].value:.0f}) while the recommendation implies growth."
            ]
        return []

    def _prediction_unknowns(self, prediction: Prediction) -> list[str]:
        unknowns = [
            "Actual hiring outcomes are not observed; only posting volume is.",
            "Sources outside ENABLED_SOURCES are entirely absent from this estimate.",
        ]
        if prediction.confidence < 0.4:
            unknowns.append("Confidence is low: direction may be usable, the point estimate is not.")
        return unknowns

    def _recommendation_unknowns(self, recommendation: Recommendation) -> list[str]:
        return [
            "Individual circumstances are not modelled; this is market-level guidance.",
            f"Nothing is known about outcomes beyond the source prediction's horizon "
            f"({recommendation.confidence:.2f} confidence).",
        ]


def _anchor_period(prediction: Prediction) -> str:
    from app.services.periods import shift_period

    weeks = int(prediction.horizon.rstrip("w") or 4)
    return shift_period(prediction.target_period, -weeks)
