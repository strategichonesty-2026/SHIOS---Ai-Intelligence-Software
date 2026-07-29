"""5.5 Prediction Agent — simple, explainable forecasts.

Method `ols_interval_v1`: ordinary least squares over the weekly series, extrapolated to the
target period and published as a two-sided 80% prediction interval (lower/upper bound) around
the point estimate. The interval comes from the OLS residual standard error and a printed
t-table — no model ever produces a number. Chosen over anything fancier because every
published number has to be defensible in one sentence, and because with 8-12 observations a
linear fit is the honest ceiling on what the data supports.

Predictions are immutable once published (spec 5.5). Re-running the agent for a period that
already has a prediction is a no-op; a changed forecast becomes a new version, never an edit.
Predictions published under the earlier point method `ols_linear_v1` are left exactly as they
were and continue to be scored on point accuracy by the Reality Check Agent.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import Agent
from app.config import settings
from app.events.bus import bus
from app.events.types import EventName
from app.governance.rules import GovernanceError, enforce, evaluate_prediction
from app.models.tables import Prediction, Trend
from app.services.calibration import calibration_multiplier
from app.services.periods import period_index, period_start_date, shift_period, week_label
from app.services.stats import clamp, direction_of, linear_fit, prediction_interval_80, stdev

log = logging.getLogger("shios.agents.prediction")

METHOD = "ols_interval_v1"
INTERVAL_CONFIDENCE = 0.80  # nominal two-sided coverage of the published interval


class PredictionAgent(Agent):
    name = "prediction"
    supports_decision = "Where is demand for this capability heading over the next few weeks?"
    requires_evidence = "At least three consecutive trend periods, each backed by evidence rows."
    confidence_method = (
        "R-squared of the linear fit, discounted by series volatility and short history, "
        "then multiplied by the learned calibration factor for the metric."
    )
    correctness_check = (
        "Reality Check Agent scores whether the actual value fell inside the published "
        "80% interval after expiry."
    )
    success_metric = "Empirical interval coverage near 80%, with calibration delta trending toward zero."
    human_review = "required before external publication of any prediction below 0.5 confidence"

    def execute(self, session: Session, **kwargs: Any) -> dict[str, Any]:
        metric: str = kwargs.get("metric", "job_postings_count")
        horizon_weeks: int = int(kwargs.get("horizon_weeks", 4))
        as_of_period: str | None = kwargs.get("as_of_period")
        entity_types: list[str] = kwargs.get("entity_types") or ["skill", "technology", "role"]
        top_n: int = int(kwargs.get("top_n", 25))

        trends = list(
            session.scalars(
                select(Trend)
                .where(Trend.metric == metric)
                .where(Trend.entity_type.in_(entity_types))
                .order_by(Trend.period)
            )
        )
        if not trends:
            return {"predictions": 0, "skipped": 0, "reason": "no trends available"}

        series: dict[tuple[str, str], list[Trend]] = defaultdict(list)
        for trend in trends:
            series[(trend.entity_type, trend.entity_name)].append(trend)

        latest_period = max(t.period for t in trends)
        anchor_period = as_of_period or latest_period

        published: list[str] = []
        skipped = 0
        rejected: list[str] = []

        ranked = sorted(
            series.items(),
            key=lambda kv: sum(t.value for t in kv[1]),
            reverse=True,
        )[:top_n]

        for (entity_type, entity_name), points in ranked:
            usable = [p for p in points if p.period <= anchor_period]
            if len(usable) < settings.min_periods_for_prediction:
                skipped += 1
                continue

            target_period = shift_period(anchor_period, horizon_weeks)
            duplicate = session.scalar(
                select(Prediction)
                .where(Prediction.metric == metric)
                .where(Prediction.entity_type == entity_type)
                .where(Prediction.entity_name == entity_name)
                .where(Prediction.target_period == target_period)
                .where(Prediction.method == METHOD)
            )
            if duplicate is not None:
                skipped += 1
                continue

            xs = [float(period_index(p.period)) for p in usable]
            ys = [float(p.value) for p in usable]
            fit = linear_fit(xs, ys)
            target_x = float(period_index(target_period))
            predicted_value = max(0.0, round(fit.predict(target_x), 2))
            raw_lower, raw_upper = prediction_interval_80(fit, target_x)
            lower_bound = max(0.0, round(raw_lower, 2))
            upper_bound = max(lower_bound, round(raw_upper, 2))
            last_value = ys[-1]

            confidence = self._confidence(session, fit, ys, metric, entity_type)
            evidence_ids = [eid for p in usable[-6:] for eid in (p.evidence_ids or [])][:40]
            trend_ids = [p.id for p in usable[-6:]]
            direction = direction_of(predicted_value - last_value, tolerance=0.5)

            anchor_date = period_start_date(anchor_period)
            review_date = period_start_date(target_period) + timedelta(days=6)
            expiration_date = review_date + timedelta(days=7)

            # Plain-English forecast statement (phase 2c)
            if entity_type == "role":
                subject = f"job postings for {entity_name} roles"
            else:
                subject = f"job postings mentioning {entity_name}"

            dir_phrase = (
                f"up from {last_value:.0f}"
                if direction == "up"
                else f"down from {last_value:.0f}"
                if direction == "down"
                else f"roughly flat from {last_value:.0f}"
            )

            statement = (
                f"Around {predicted_value:.0f} {subject} are expected the week of "
                f"{week_label(target_period)} (likely range: {lower_bound:.0f}–{upper_bound:.0f}, "
                f"{INTERVAL_CONFIDENCE:.0%} confidence) — {dir_phrase} the week of "
                f"{week_label(anchor_period)}."
            )

            report = evaluate_prediction(
                confidence=confidence,
                supporting_evidence_ids=evidence_ids,
                trend_ids=trend_ids,
                review_date=review_date,
                expiration_date=expiration_date,
                created_on=anchor_date,
                periods_observed=len(usable),
            )
            try:
                enforce(report, f"prediction for {entity_name}")
            except GovernanceError as exc:
                rejected.append(str(exc))
                continue

            prediction = Prediction(
                statement=statement,
                domain="career",
                metric=metric,
                entity_type=entity_type,
                entity_name=entity_name,
                horizon=f"{horizon_weeks}w",
                target_period=target_period,
                predicted_value=predicted_value,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
                interval_confidence=INTERVAL_CONFIDENCE,
                predicted_direction=direction,
                confidence=round(confidence, 4),
                supporting_evidence_ids=evidence_ids,
                trend_ids=trend_ids,
                assumptions=self._assumptions(len(usable), anchor_period),
                risks=self._risks(report.messages, ys),
                method=METHOD,
                review_date=review_date,
                expiration_date=expiration_date,
                version=1,
                status="published",
            )
            session.add(prediction)
            session.flush()
            published.append(prediction.id)
            bus.publish(
                EventName.PREDICTION_PUBLISHED,
                {
                    "prediction_id": prediction.id,
                    "entity_name": entity_name,
                    "target_period": target_period,
                    "confidence": prediction.confidence,
                },
                session,
            )

        session.flush()
        return {
            "predictions": len(published),
            "prediction_ids": published,
            "skipped": skipped,
            "rejected_by_governance": rejected,
            "anchor_period": anchor_period,
            "target_period": shift_period(anchor_period, horizon_weeks),
        }

    # -- helpers ------------------------------------------------------------

    def _confidence(
        self, session: Session, fit, values: list[float], metric: str, entity_type: str
    ) -> float:
        fit_quality = fit.r_squared
        history_factor = clamp(len(values) / 8.0, 0.35, 1.0)
        mean_value = sum(values) / len(values) if values else 0.0
        volatility = stdev(values) / mean_value if mean_value else 1.0
        volatility_factor = clamp(1.0 - volatility, 0.3, 1.0)
        raw = 0.25 + 0.55 * fit_quality
        adjusted = raw * history_factor * volatility_factor
        adjusted *= calibration_multiplier(session, metric, entity_type)
        return clamp(adjusted, settings.min_confidence, settings.max_confidence)

    def _assumptions(self, periods: int, anchor_period: str) -> list[str]:
        return [
            f"Source mix stays comparable to the {periods} weeks ending {anchor_period}.",
            "Posting volume is a usable proxy for demand, accepting a multi-week lag.",
            "No structural break (layoff wave, hiring freeze, acquisition) inside the horizon.",
        ]

    def _risks(self, governance_messages: list[str], values: list[float]) -> list[str]:
        risks = [
            "Linear extrapolation understates inflection points by construction.",
            "Deduplication is by source id; a repost under a new id inflates counts.",
        ]
        if values and stdev(values) > (sum(values) / len(values)) * 0.5:
            risks.append("Series is volatile; the point estimate is weaker than the direction.")
        risks.extend(m for m in governance_messages if m.startswith("[soft]"))
        return risks


def default_target_period(anchor: str, horizon_weeks: int = 4) -> str:
    return shift_period(anchor, horizon_weeks)


def today() -> date:
    from datetime import datetime

    return datetime.now(UTC).date()
