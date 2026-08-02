from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.tables import (
    Job,
    KnowledgeRecord,
    LearningFeedback,
    NormalizedDocument,
    Prediction,
    PredictionResult,
    Recommendation,
    Report,
    Trend,
)
from app.services.periods import period_range
from app.services.stats import mean

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview")
def overview(session: Session = Depends(get_session)) -> dict:
    latest = session.scalar(select(func.max(Trend.period)))
    first = session.scalar(select(func.min(Trend.period)))
    results = list(session.scalars(select(PredictionResult)))
    feedback = list(session.scalars(select(LearningFeedback)))
    latest_trends = (
        list(session.scalars(select(Trend).where(Trend.period == latest))) if latest else []
    )
    risers = sorted([t for t in latest_trends if t.delta > 0], key=lambda t: t.delta, reverse=True)[:5]
    fallers = sorted([t for t in latest_trends if t.delta < 0], key=lambda t: t.delta)[:5]

    return {
        "window": {"first_period": first, "latest_period": latest},
        "counts": {
            "documents": session.scalar(select(func.count()).select_from(NormalizedDocument)) or 0,
            "jobs": session.scalar(select(func.count()).select_from(Job)) or 0,
            "tracked_entities": session.scalar(
                select(func.count(func.distinct(Trend.entity_name)))
            )
            or 0,
            "open_predictions": session.scalar(
                select(func.count()).select_from(Prediction).where(Prediction.status == "published")
            )
            or 0,
            "recommendations": session.scalar(select(func.count()).select_from(Recommendation)) or 0,
            "reports": session.scalar(select(func.count()).select_from(Report)) or 0,
            "knowledge_records": session.scalar(select(func.count()).select_from(KnowledgeRecord)) or 0,
        },
        "accuracy": {
            "scored": len(results),
            "mean_accuracy": round(mean([r.accuracy_score for r in results]), 4) if results else None,
            "direction_hit_rate": round(sum(1 for r in results if r.direction_correct) / len(results), 4)
            if results
            else None,
            "mean_calibration_delta": round(mean([f.confidence_calibration_delta for f in feedback]), 4)
            if feedback
            else None,
        },
        "risers": [_trend(t) for t in risers],
        "fallers": [_trend(t) for t in fallers],
    }


@router.get("/archive")
def archive_windows(session: Session = Depends(get_session)) -> dict:
    """One row per closed observation window — every Trend period except the current (open) one."""
    latest = session.scalar(select(func.max(Trend.period)))
    periods = list(
        session.scalars(select(Trend.period).distinct().order_by(Trend.period.desc()))
    )
    closed_periods = [p for p in periods if p != latest]
    trend_counts = dict(
        session.execute(select(Trend.period, func.count()).group_by(Trend.period)).all()
    )
    scored_counts = dict(
        session.execute(
            select(PredictionResult.reality_period, func.count()).group_by(
                PredictionResult.reality_period
            )
        ).all()
    )
    return {
        "items": [
            {
                "period": period,
                "trend_count": trend_counts.get(period, 0),
                "scored_forecasts": scored_counts.get(period, 0),
            }
            for period in closed_periods
        ]
    }


@router.get("/archive/{period}")
def archive_window(period: str, session: Session = Depends(get_session)) -> dict:
    """Frozen Rising/Falling tables plus forecasts scored against this window."""
    trends = list(session.scalars(select(Trend).where(Trend.period == period)))
    if not trends:
        raise HTTPException(status_code=404, detail="No trend data for that observation window.")

    risers = sorted([t for t in trends if t.delta > 0], key=lambda t: t.delta, reverse=True)[:5]
    fallers = sorted([t for t in trends if t.delta < 0], key=lambda t: t.delta)[:5]

    results = list(
        session.scalars(
            select(PredictionResult).where(PredictionResult.reality_period == period)
        )
    )
    predictions = {
        p.id: p
        for p in session.scalars(
            select(Prediction).where(
                Prediction.id.in_([r.prediction_id for r in results])
            )
        )
    }

    return {
        "period": period,
        "risers": [_trend(t) for t in risers],
        "fallers": [_trend(t) for t in fallers],
        "scored_forecasts": [
            {
                "id": r.prediction_id,
                "statement": predictions[r.prediction_id].statement
                if r.prediction_id in predictions
                else None,
                "target_period": predictions[r.prediction_id].target_period
                if r.prediction_id in predictions
                else None,
                "predicted_value": r.predicted_value,
                "actual_value": r.actual_value,
                "accuracy_score": r.accuracy_score,
                "direction_correct": r.direction_correct,
            }
            for r in results
        ],
    }


@router.get("/career")
def career_intelligence(
    limit: int = Query(default=10, ge=1, le=50), session: Session = Depends(get_session)
) -> dict:
    return _section(session, ["skill", "role"], limit)


@router.get("/technology")
def technology_intelligence(
    limit: int = Query(default=10, ge=1, le=50), session: Session = Depends(get_session)
) -> dict:
    return _section(session, ["technology"], limit)


@router.get("/explorer")
def trend_explorer(
    entity_type: str = Query(default="skill"),
    top: int = Query(default=8, ge=1, le=25),
    session: Session = Depends(get_session),
) -> dict:
    """Series for the top entities, aligned on a common period axis for charting."""
    latest = session.scalar(select(func.max(Trend.period)))
    first = session.scalar(select(func.min(Trend.period)))
    if not latest or not first:
        return {"periods": [], "series": []}
    top_names = list(
        session.scalars(
            select(Trend.entity_name)
            .where(Trend.entity_type == entity_type)
            .where(Trend.period == latest)
            .order_by(Trend.value.desc())
            .limit(top)
        )
    )
    periods = period_range(first, latest)
    rows = list(
        session.scalars(
            select(Trend)
            .where(Trend.entity_type == entity_type)
            .where(Trend.entity_name.in_(top_names))
            .order_by(Trend.period)
        )
    )
    by_name: dict[str, dict[str, float]] = {}
    for trend in rows:
        by_name.setdefault(trend.entity_name, {})[trend.period] = trend.value
    return {
        "entity_type": entity_type,
        "periods": periods,
        "series": [
            {"name": name, "values": [by_name.get(name, {}).get(p, 0.0) for p in periods]}
            for name in top_names
        ],
    }


@router.get("/recommendation-history")
def recommendation_history(
    limit: int = Query(default=50, ge=1, le=200), session: Session = Depends(get_session)
) -> dict:
    rows = list(
        session.scalars(select(Recommendation).order_by(Recommendation.created_at.desc()).limit(limit))
    )
    by_audience: dict[str, int] = {}
    for recommendation in rows:
        by_audience[recommendation.audience_type] = by_audience.get(recommendation.audience_type, 0) + 1
    return {
        "by_audience": by_audience,
        "items": [
            {
                "id": r.id,
                "audience_type": r.audience_type,
                "recommendation_text": r.recommendation_text,
                "confidence": r.confidence,
                "status": r.status,
                "created_at": r.created_at,
            }
            for r in rows
        ],
    }


def _section(session: Session, entity_types: list[str], limit: int) -> dict:
    latest = session.scalar(select(func.max(Trend.period)))
    if latest is None:
        return {"period": None, "top": [], "predictions": [], "salary_trends": []}
    top = list(
        session.scalars(
            select(Trend)
            .where(Trend.period == latest)
            .where(Trend.entity_type.in_(entity_types))
            .order_by(Trend.value.desc())
            .limit(limit)
        )
    )
    top_names = [t.entity_name for t in top]
    salary_trends = (
        list(
            session.scalars(
                select(Trend)
                .where(Trend.metric == "median_salary")
                .where(Trend.period == latest)
                .where(Trend.entity_type.in_(entity_types))
                .where(Trend.entity_name.in_(top_names))
                .order_by(Trend.value.desc())
            )
        )
        if top_names
        else []
    )
    predictions = list(
        session.scalars(
            select(Prediction)
            .where(Prediction.entity_type.in_(entity_types))
            .where(Prediction.status == "published")
            .order_by(Prediction.confidence.desc())
            .limit(limit)
        )
    )
    return {
        "period": latest,
        "top": [_trend(t) for t in top],
        "salary_trends": [
            {
                "entity_name": t.entity_name,
                "entity_type": t.entity_type,
                "period": t.period,
                "median_salary": t.value,
                "delta": t.delta,
                "direction": t.direction,
                "sample_size": t.sample_size,
                "note": "median of (salary_min + salary_max) / 2 across job postings with salary data",
            }
            for t in salary_trends
        ],
        "predictions": [
            {
                "id": p.id,
                "entity_name": p.entity_name,
                "statement": p.statement,
                "predicted_value": p.predicted_value,
                "lower_bound": p.lower_bound,
                "upper_bound": p.upper_bound,
                "predicted_direction": p.predicted_direction,
                "confidence": p.confidence,
                "target_period": p.target_period,
            }
            for p in predictions
        ],
    }


def _trend(trend: Trend) -> dict:
    return {
        "id": trend.id,
        "entity_type": trend.entity_type,
        "entity_name": trend.entity_name,
        "period": trend.period,
        "value": trend.value,
        "delta": trend.delta,
        "delta_pct": trend.delta_pct,
        "direction": trend.direction,
        "evidence_count": len(trend.evidence_ids or []),
    }
