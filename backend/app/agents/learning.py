"""5.9 Learning Agent — turn scored predictions into a correction signal.

The calibration delta is `accuracy - confidence`. Negative means the system claimed more
certainty than it earned, and the Prediction Agent will publish lower confidence for that
metric slice next time. That single number is the entire learning mechanism in v1, and it is
deliberately legible: anyone can audit why confidence moved.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import Agent
from app.events.bus import bus
from app.events.types import EventName
from app.models.tables import LearningFeedback, Prediction, PredictionResult

FALSE_SIGNAL_THRESHOLD = 0.5


class LearningAgent(Agent):
    name = "learning"
    supports_decision = "How much should the system trust its own next forecast?"
    requires_evidence = "A scored PredictionResult linked to a published Prediction."
    confidence_method = "Calibration delta = accuracy_score - claimed confidence."
    correctness_check = "Mean absolute calibration delta should shrink as sample size grows."
    success_metric = "Calibration delta within +/-0.10 after 20 scored predictions per slice."
    human_review = "none"

    def execute(self, session: Session, **kwargs: Any) -> dict[str, Any]:
        result_ids: list[str] | None = kwargs.get("prediction_result_ids")

        already = select(LearningFeedback.prediction_result_id)
        query = select(PredictionResult).where(PredictionResult.id.not_in(already))
        if result_ids:
            query = query.where(PredictionResult.id.in_(result_ids))
        results = list(session.scalars(query.limit(1000)))

        written: list[str] = []
        for result in results:
            prediction = session.get(Prediction, result.prediction_id)
            if prediction is None:
                continue

            delta = round(result.accuracy_score - prediction.confidence, 4)
            false_positive = (
                prediction.predicted_direction == "up"
                and not result.direction_correct
                and result.accuracy_score < FALSE_SIGNAL_THRESHOLD
            )
            false_negative = (
                prediction.predicted_direction in {"down", "flat"}
                and not result.direction_correct
                and result.accuracy_score < FALSE_SIGNAL_THRESHOLD
            )

            notes = [
                f"method={prediction.method}",
                f"periods_used={len(prediction.trend_ids or [])}",
                f"evidence={len(prediction.supporting_evidence_ids or [])}",
                "overconfident" if delta < -0.1 else "underconfident" if delta > 0.1 else "calibrated",
            ]

            feedback = LearningFeedback(
                prediction_id=prediction.id,
                prediction_result_id=result.id,
                metric=prediction.metric,
                entity_type=prediction.entity_type,
                accuracy_score=result.accuracy_score,
                false_positive=false_positive,
                false_negative=false_negative,
                confidence_calibration_delta=delta,
                signal_quality_notes="; ".join(notes),
            )
            session.add(feedback)
            session.flush()
            written.append(feedback.id)
            bus.publish(
                EventName.LEARNING_RECORDED,
                {"learning_feedback_id": feedback.id, "calibration_delta": delta},
                session,
            )

        session.flush()
        return {"learning_feedback": len(written), "learning_feedback_ids": written}
