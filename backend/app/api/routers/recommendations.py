from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Page
from app.db import get_session
from app.models.tables import Evidence, Prediction, Recommendation, ValidationResult

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

ALLOWED_STATUS = {"draft", "validated", "approved", "rejected", "needs_review"}


@router.get("")
def list_recommendations(
    audience_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: Page = Depends(),
    session: Session = Depends(get_session),
) -> dict:
    query = select(Recommendation).order_by(Recommendation.created_at.desc())
    if audience_type:
        query = query.where(Recommendation.audience_type == audience_type)
    if status:
        query = query.where(Recommendation.status == status)
    rows = list(session.scalars(query.limit(page.limit).offset(page.offset)))
    return {"items": [_serialize(r) for r in rows], "limit": page.limit, "offset": page.offset}


@router.get("/{recommendation_id}")
def get_recommendation(recommendation_id: str, session: Session = Depends(get_session)) -> dict:
    recommendation = session.get(Recommendation, recommendation_id)
    if recommendation is None:
        raise HTTPException(status_code=404, detail="Recommendation not found.")
    evidence = list(
        session.scalars(select(Evidence).where(Evidence.id.in_(recommendation.evidence_ids or [])).limit(25))
    )
    prediction = (
        session.get(Prediction, recommendation.prediction_id) if recommendation.prediction_id else None
    )
    validations = list(
        session.scalars(
            select(ValidationResult)
            .where(ValidationResult.target_type == "recommendation")
            .where(ValidationResult.target_id == recommendation_id)
            .order_by(ValidationResult.validated_at.desc())
        )
    )
    payload = _serialize(recommendation)
    payload.update(
        {
            "rationale": recommendation.rationale,
            "risks": recommendation.risks,
            "alternative_scenarios": recommendation.alternative_scenarios,
            "expected_outcomes": recommendation.expected_outcomes,
            "prediction": None
            if prediction is None
            else {
                "id": prediction.id,
                "statement": prediction.statement,
                "confidence": prediction.confidence,
                "target_period": prediction.target_period,
            },
            "evidence": [
                {"id": e.id, "entity_name": e.entity_name, "period": e.period, "snippet": e.snippet}
                for e in evidence
            ],
            "validations": [
                {
                    "is_valid": v.is_valid,
                    "issues": v.issues,
                    "contradictory_evidence": v.contradictory_evidence,
                    "unknowns_noted": v.unknowns_noted,
                }
                for v in validations
            ],
        }
    )
    return payload


@router.post("/{recommendation_id}/decision")
def record_decision(
    recommendation_id: str,
    status: str = Body(embed=True),
    note: str = Body(default="", embed=True),
    session: Session = Depends(get_session),
) -> dict:
    """Human approval step for high-impact decisions (core principle 6)."""
    if status not in ALLOWED_STATUS:
        raise HTTPException(status_code=422, detail=f"Status must be one of {sorted(ALLOWED_STATUS)}.")
    recommendation = session.get(Recommendation, recommendation_id)
    if recommendation is None:
        raise HTTPException(status_code=404, detail="Recommendation not found.")
    recommendation.status = status
    session.add(
        ValidationResult(
            target_type="recommendation",
            target_id=recommendation_id,
            is_valid=status in {"approved", "validated"},
            issues=[f"human decision: {status}"] + ([note] if note else []),
        )
    )
    session.commit()
    return {"id": recommendation_id, "status": status}


def _serialize(recommendation: Recommendation) -> dict:
    return {
        "id": recommendation.id,
        "audience_type": recommendation.audience_type,
        "domain": recommendation.domain,
        "recommendation_text": recommendation.recommendation_text,
        "confidence": recommendation.confidence,
        "status": recommendation.status,
        "prediction_id": recommendation.prediction_id,
        "evidence_count": len(recommendation.evidence_ids or []),
        "created_at": recommendation.created_at,
    }
