from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.agents import governance_catalog
from app.config import settings
from app.db import get_session
from app.models.tables import (
    Evidence,
    NormalizedDocument,
    Prediction,
    RawDocument,
    Recommendation,
    Report,
    Trend,
)
from app.sources import available_source_ids

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
    }


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
