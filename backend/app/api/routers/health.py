from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.agents import governance_catalog
from app.config import settings
from app.config import settings as app_settings
from app.db import get_session
from app.models.tables import (
    EventLog,
    Evidence,
    NormalizedDocument,
    Prediction,
    RawDocument,
    Recommendation,
    Report,
    Trend,
)
from app.sources import available_source_ids, build_sources

router = APIRouter(tags=["system"])


@router.get("/health")
def health(session: Session = Depends(get_session)) -> dict:
    try:
        session.execute(text("SELECT 1"))
        database = "up"
    except Exception as exc:  # pragma: no cover - infra
        database = f"down: {exc}"
    return {
        "status": "ok" if database == "up" else "degraded",
        "version": settings.app_version,
        "environment": settings.environment,
        "database": database,
        "llm_provider": settings.llm_provider,
        "source_health": _source_health(session),
    }


def _source_health(session: Session) -> dict:
    """Summarise recent collection success/failure per source from the event log."""
    recent_failures: dict[str, int] = {}
    recent_successes: dict[str, int] = {}

    failure_events = list(
        session.scalars(
            select(EventLog)
            .where(EventLog.name == "document.collection_failed")
            .order_by(EventLog.created_at.desc())
            .limit(200)
        )
    )
    success_events = list(
        session.scalars(
            select(EventLog)
            .where(EventLog.name == "document.collected")
            .order_by(EventLog.created_at.desc())
            .limit(200)
        )
    )

    for event in failure_events:
        src = event.payload.get("source", "unknown")
        recent_failures[src] = recent_failures.get(src, 0) + 1

    for event in success_events:
        src = event.payload.get("source", event.payload.get("raw_document_id", "unknown"))
        recent_successes[src] = recent_successes.get(src, 0) + 1

    configured = [s.source_id for s in build_sources() if s.is_configured()]
    result: dict[str, dict] = {}
    for source_id in configured:
        failures = recent_failures.get(source_id, 0)
        successes = recent_successes.get(source_id, 0)
        total = failures + successes
        result[source_id] = {
            "status": "healthy" if failures == 0 else (
                "degraded" if successes > 0 else "failing"
            ),
            "recent_successes": successes,
            "recent_failures": failures,
            "success_rate": round(successes / total, 2) if total else None,
            "retry_config": {
                "max_retries": app_settings.source_max_retries,
                "backoff_seconds": app_settings.source_backoff_seconds,
            },
        }
    return result


@router.get("/ready")
def ready(session: Session = Depends(get_session)) -> dict:
    counts = {
        "raw_documents": session.scalar(select(func.count()).select_from(RawDocument)) or 0,
        "normalized_documents": session.scalar(select(func.count()).select_from(NormalizedDocument)) or 0,
        "evidence": session.scalar(select(func.count()).select_from(Evidence)) or 0,
        "trends": session.scalar(select(func.count()).select_from(Trend)) or 0,
        "predictions": session.scalar(select(func.count()).select_from(Prediction)) or 0,
        "recommendations": session.scalar(select(func.count()).select_from(Recommendation)) or 0,
        "reports": session.scalar(select(func.count()).select_from(Report)) or 0,
    }
    return {"ready": counts["trends"] > 0, "counts": counts}


@router.get("/agents")
def agents() -> dict:
    return {"agents": governance_catalog(), "sources_available": available_source_ids()}
