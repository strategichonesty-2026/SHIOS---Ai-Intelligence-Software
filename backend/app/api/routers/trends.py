from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Page
from app.db import get_session
from app.models.tables import Evidence, Trend

router = APIRouter(prefix="/trends", tags=["trends"])


@router.get("")
def list_trends(
    entity_type: str | None = Query(default=None),
    entity_name: str | None = Query(default=None),
    period: str | None = Query(default=None),
    metric: str = Query(default="job_postings_count"),
    page: Page = Depends(),
    session: Session = Depends(get_session),
) -> dict:
    query = select(Trend).where(Trend.metric == metric)
    if entity_type:
        query = query.where(Trend.entity_type == entity_type)
    if entity_name:
        query = query.where(Trend.entity_name == entity_name)
    if period:
        query = query.where(Trend.period == period)
    query = query.order_by(Trend.period.desc(), Trend.value.desc())
    rows = list(session.scalars(query.limit(page.limit).offset(page.offset)))
    return {"items": [_serialize(t) for t in rows], "limit": page.limit, "offset": page.offset}


@router.get("/latest")
def latest_trends(
    entity_type: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    session: Session = Depends(get_session),
) -> dict:
    latest = session.scalar(select(func.max(Trend.period)))
    if latest is None:
        return {"period": None, "items": []}
    query = select(Trend).where(Trend.period == latest)
    if entity_type:
        query = query.where(Trend.entity_type == entity_type)
    rows = list(session.scalars(query.order_by(Trend.value.desc()).limit(limit)))
    return {"period": latest, "items": [_serialize(t) for t in rows]}


@router.get("/series/{entity_type}/{entity_name}")
def trend_series(
    entity_type: str,
    entity_name: str,
    metric: str = Query(default="job_postings_count"),
    session: Session = Depends(get_session),
) -> dict:
    rows = list(
        session.scalars(
            select(Trend)
            .where(Trend.metric == metric)
            .where(Trend.entity_type == entity_type)
            .where(Trend.entity_name == entity_name)
            .order_by(Trend.period)
        )
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No series for that entity.")
    return {
        "entity_type": entity_type,
        "entity_name": entity_name,
        "metric": metric,
        "points": [{"period": t.period, "value": t.value, "delta": t.delta, "direction": t.direction} for t in rows],
    }


@router.get("/{trend_id}/evidence")
def trend_evidence(trend_id: str, session: Session = Depends(get_session)) -> dict:
    trend = session.get(Trend, trend_id)
    if trend is None:
        raise HTTPException(status_code=404, detail="Trend not found.")
    rows = list(session.scalars(select(Evidence).where(Evidence.id.in_(trend.evidence_ids or []))))
    return {
        "trend_id": trend_id,
        "entity_name": trend.entity_name,
        "period": trend.period,
        "evidence": [
            {
                "id": e.id,
                "snippet": e.snippet,
                "source": e.source,
                "normalized_document_id": e.normalized_document_id,
            }
            for e in rows
        ],
    }


def _serialize(trend: Trend) -> dict:
    return {
        "id": trend.id,
        "metric": trend.metric,
        "entity_type": trend.entity_type,
        "entity_name": trend.entity_name,
        "period": trend.period,
        "value": trend.value,
        "delta": trend.delta,
        "delta_pct": trend.delta_pct,
        "direction": trend.direction,
        "sample_size": trend.sample_size,
        "evidence_count": len(trend.evidence_ids or []),
        "computed_at": trend.computed_at,
    }
