"""5.9 Learning Agent — turn scored predictions into a correction signal.

For interval predictions the calibration delta is `coverage - claimed interval confidence`,
where coverage is 1.0 if the actual value landed inside the published interval and 0.0 if it
missed. Averaged over a slice this is exactly `empirical coverage - nominal coverage`, two
numbers of the same kind — which is what the old `accuracy - confidence` delta was not
(ANALYSIS.md 5.1). Negative means the intervals miss more often than claimed and the
Prediction Agent will publish lower confidence for that slice next time. Legacy point
predictions with no recorded coverage keep the old delta. The single number remains the
entire learning mechanism, and it is deliberately legible: anyone can audit why confidence
moved.
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
    confidence_method = (
        "Calibration delta = interval coverage (0 or 1) - claimed interval confidence; "
        "accuracy_score - confidence for legacy point predictions."
    )
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

            coverage_correct = result.interval_covered
            if coverage_correct is not None:
                nominal = prediction.interval_confidence or 0.0
                delta = round(float(coverage_correct) - nominal, 4)
            else:
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
            ]
            if coverage_correct is not None:
                notes.append(f"interval_{'covered' if coverage_correct else 'missed'}")
            notes.append(
                "overconfident" if delta < -0.1 else "underconfident" if delta > 0.1 else "calibrated"
            )

            feedback = LearningFeedback(
                prediction_id=prediction.id,
                prediction_result_id=result.id,
                metric=prediction.metric,
                entity_type=prediction.entity_type,
                accuracy_score=result.accuracy_score,
                false_positive=false_positive,
                false_negative=false_negative,
                coverage_correct=coverage_correct,
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
