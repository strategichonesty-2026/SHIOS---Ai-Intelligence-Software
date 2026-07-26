"""5.8 Reality Check Agent — compare what we said against what happened.

Runs on predictions whose expiration date has passed AND whose target period now has an
actual trend value. Both conditions matter: an expired prediction with no observed actual is
recorded as `unverifiable` rather than silently scored, because scoring a missing value is
how accuracy metrics get quietly inflated.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import Agent
from app.events.bus import bus
from app.events.types import EventName
from app.models.tables import Prediction, PredictionResult, Trend
from app.services.periods import shift_period
from app.services.stats import accuracy_score, direction_of


class RealityCheckAgent(Agent):
    name = "reality_check"
    supports_decision = "Was the forecast right, and by how much was it wrong?"
    requires_evidence = "The prediction plus the observed trend value for its target period."
    confidence_method = "Not applicable; this agent measures rather than estimates."
    correctness_check = "Scores are recomputable from stored predicted and actual values."
    success_metric = "Every expired prediction reaches a terminal state: scored or unverifiable."
    human_review = "none"

    def execute(self, session: Session, **kwargs: Any) -> dict[str, Any]:
        as_of: date = kwargs.get("as_of") or datetime.now(UTC).date()
        prediction_ids: list[str] | None = kwargs.get("prediction_ids")

        scored = select(PredictionResult.prediction_id)
        query = select(Prediction).where(Prediction.id.not_in(scored))
        if prediction_ids:
            query = query.where(Prediction.id.in_(prediction_ids))
        else:
            query = query.where(Prediction.expiration_date <= as_of)
        candidates = list(session.scalars(query.limit(1000)))

        results: list[str] = []
        unverifiable = 0

        for prediction in candidates:
            actual_trend = session.scalar(
                select(Trend)
                .where(Trend.metric == prediction.metric)
                .where(Trend.entity_type == prediction.entity_type)
                .where(Trend.entity_name == prediction.entity_name)
                .where(Trend.period == prediction.target_period)
            )
            if actual_trend is None:
                prediction.status = "unverifiable"
                unverifiable += 1
                continue

            horizon_weeks = int(prediction.horizon.rstrip("w") or 4)
            baseline_period = shift_period(prediction.target_period, -horizon_weeks)
            baseline = session.scalar(
                select(Trend)
                .where(Trend.metric == prediction.metric)
                .where(Trend.entity_type == prediction.entity_type)
                .where(Trend.entity_name == prediction.entity_name)
                .where(Trend.period == baseline_period)
            )
            baseline_value = baseline.value if baseline else actual_trend.value

            actual_value = float(actual_trend.value)
            deviation = round(prediction.predicted_value - actual_value, 4)
            score = round(accuracy_score(prediction.predicted_value, actual_value), 4)
            actual_direction = direction_of(actual_value - baseline_value, tolerance=0.5)
            direction_correct = actual_direction == prediction.predicted_direction

            result = PredictionResult(
                prediction_id=prediction.id,
                reality_period=prediction.target_period,
                actual_value=actual_value,
                predicted_value=prediction.predicted_value,
                accuracy_score=score,
                deviation=deviation,
                direction_correct=direction_correct,
                notes=(
                    f"Predicted {prediction.predicted_value:.1f} ({prediction.predicted_direction}), "
                    f"observed {actual_value:.1f} ({actual_direction}) in {prediction.target_period}."
                ),
            )
            session.add(result)
            prediction.status = "evaluated"
            session.flush()
            results.append(result.id)
            bus.publish(
                EventName.PREDICTION_EVALUATED,
                {
                    "prediction_id": prediction.id,
                    "prediction_result_id": result.id,
                    "accuracy_score": score,
                },
                session,
            )

        session.flush()
        return {
            "prediction_results": len(results),
            "prediction_result_ids": results,
            "unverifiable": unverifiable,
            "evaluated_as_of": as_of.isoformat(),
        }
