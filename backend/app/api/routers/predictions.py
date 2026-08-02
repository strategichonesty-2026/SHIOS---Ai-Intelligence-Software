from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Page
from app.db import get_session
from app.models.tables import LearningFeedback, Prediction, PredictionResult, Trend, ValidationResult
from app.services.calibration import calibration_summary
from app.services.stats import mean

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("")
def list_predictions(
    status: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    page: Page = Depends(),
    session: Session = Depends(get_session),
) -> dict:
    query = select(Prediction)
    if status:
        query = query.where(Prediction.status == status)
    if entity_type:
        query = query.where(Prediction.entity_type == entity_type)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    query = query.order_by(Prediction.target_period.desc(), Prediction.created_at.desc())
    rows = list(session.scalars(query.limit(page.limit).offset(page.offset)))
    return {
        "items": [_serialize(p) for p in rows],
        "limit": page.limit,
        "offset": page.offset,
        "total": total,
    }


@router.get("/accuracy")
def accuracy(session: Session = Depends(get_session)) -> dict:
    results = list(session.scalars(select(PredictionResult)))
    feedback = list(session.scalars(select(LearningFeedback)))
    by_period: dict[str, list[float]] = {}
    for result in results:
        by_period.setdefault(result.reality_period, []).append(result.accuracy_score)
    covered = [r.interval_covered for r in results if r.interval_covered is not None]
    return {
        "scored": len(results),
        "interval_scored": len(covered),
        "interval_coverage_rate": round(sum(covered) / len(covered), 4) if covered else None,
        "mean_accuracy": round(mean([r.accuracy_score for r in results]), 4) if results else None,
        "direction_hit_rate": round(
            sum(1 for r in results if r.direction_correct) / len(results), 4
        )
        if results
        else None,
        "mean_calibration_delta": round(
            mean([f.confidence_calibration_delta for f in feedback]), 4
        )
        if feedback
        else None,
        "by_period": [
            {"period": period, "mean_accuracy": round(mean(scores), 4), "count": len(scores)}
            for period, scores in sorted(by_period.items())
        ],
        "calibration": calibration_summary(session),
    }


@router.get("/{prediction_id}")
def get_prediction(prediction_id: str, session: Session = Depends(get_session)) -> dict:
    prediction = session.get(Prediction, prediction_id)
    if prediction is None:
        raise HTTPException(status_code=404, detail="Prediction not found.")
    result = session.scalar(select(PredictionResult).where(PredictionResult.prediction_id == prediction_id))
    validations = list(
        session.scalars(
            select(ValidationResult)
            .where(ValidationResult.target_type == "prediction")
            .where(ValidationResult.target_id == prediction_id)
            .order_by(ValidationResult.validated_at.desc())
        )
    )
    trends = list(session.scalars(select(Trend).where(Trend.id.in_(prediction.trend_ids or []))))
    trends.sort(key=lambda t: t.period)
    payload = _serialize(prediction)
    payload.update(
        {
            "assumptions": prediction.assumptions,
            "risks": prediction.risks,
            "supporting_evidence_ids": prediction.supporting_evidence_ids,
            "series": [{"period": t.period, "value": t.value} for t in trends],
            "result": None
            if result is None
            else {
                "actual_value": result.actual_value,
                "accuracy_score": result.accuracy_score,
                "deviation": result.deviation,
                "interval_covered": result.interval_covered,
                "direction_correct": result.direction_correct,
                "notes": result.notes,
                "evaluated_at": result.evaluated_at,
            },
            "validations": [
                {
                    "is_valid": v.is_valid,
                    "issues": v.issues,
                    "unknowns_noted": v.unknowns_noted,
                    "validated_at": v.validated_at,
                }
                for v in validations
            ],
        }
    )
    return payload


def _serialize(prediction: Prediction) -> dict:
    return {
        "id": prediction.id,
        "statement": prediction.statement,
        "domain": prediction.domain,
        "metric": prediction.metric,
        "entity_type": prediction.entity_type,
        "entity_name": prediction.entity_name,
        "horizon": prediction.horizon,
        "target_period": prediction.target_period,
        "predicted_value": prediction.predicted_value,
        "lower_bound": prediction.lower_bound,
        "upper_bound": prediction.upper_bound,
        "interval_confidence": prediction.interval_confidence,
        "predicted_direction": prediction.predicted_direction,
        "confidence": prediction.confidence,
        "method": prediction.method,
        "review_date": prediction.review_date,
        "expiration_date": prediction.expiration_date,
        "status": prediction.status,
        "version": prediction.version,
        "evidence_count": len(prediction.supporting_evidence_ids or []),
        "created_at": prediction.created_at,
    }
