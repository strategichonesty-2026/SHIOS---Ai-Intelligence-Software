"""Confidence calibration.

This is the loop closing. The Learning Agent records, for each metric/entity_type slice, the
gap between the confidence we claimed and the accuracy we achieved. The Prediction Agent
reads that gap back through `calibration_multiplier` before it publishes anything new.

A system that never lowers its own confidence after being wrong is not honest.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tables import LearningFeedback
from app.services.stats import clamp, mean

MIN_SAMPLES = 3
MAX_ADJUSTMENT = 0.35


def calibration_multiplier(session: Session, metric: str, entity_type: str) -> float:
    """1.0 means "no evidence to adjust". <1 means we have been overconfident."""
    deltas = list(
        session.scalars(
            select(LearningFeedback.confidence_calibration_delta)
            .where(LearningFeedback.metric == metric)
            .where(LearningFeedback.entity_type == entity_type)
            .order_by(LearningFeedback.created_at.desc())
            .limit(50)
        )
    )
    if len(deltas) < MIN_SAMPLES:
        return 1.0
    average_delta = mean([float(d) for d in deltas])
    return clamp(1.0 + average_delta, 1.0 - MAX_ADJUSTMENT, 1.0 + MAX_ADJUSTMENT)


def calibration_summary(session: Session) -> list[dict]:
    rows = session.execute(
        select(
            LearningFeedback.metric,
            LearningFeedback.entity_type,
            LearningFeedback.accuracy_score,
            LearningFeedback.confidence_calibration_delta,
        )
    ).all()
    grouped: dict[tuple[str, str], list[tuple[float, float]]] = {}
    for metric, entity_type, accuracy, delta in rows:
        grouped.setdefault((metric, entity_type), []).append((float(accuracy), float(delta)))
    return [
        {
            "metric": metric,
            "entity_type": entity_type,
            "samples": len(values),
            "mean_accuracy": round(mean([v[0] for v in values]), 4),
            "mean_calibration_delta": round(mean([v[1] for v in values]), 4),
            "multiplier": round(clamp(1.0 + mean([v[1] for v in values]), 0.65, 1.35), 4),
        }
        for (metric, entity_type), values in sorted(grouped.items())
    ]
