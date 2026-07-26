from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Page
from app.db import get_session
from app.models.tables import Evidence, Job, NormalizedDocument, RawDocument

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("")
def list_documents(
    doc_type: str | None = Query(default=None),
    source: str | None = Query(default=None),
    page: Page = Depends(),
    session: Session = Depends(get_session),
) -> dict:
    query = select(NormalizedDocument).order_by(NormalizedDocument.observed_at.desc())
    if doc_type:
        query = query.where(NormalizedDocument.doc_type == doc_type)
    if source:
        query = query.where(NormalizedDocument.source == source)
    rows = list(session.scalars(query.limit(page.limit).offset(page.offset)))
    return {
        "items": [
            {
                "id": d.id,
                "raw_document_id": d.raw_document_id,
                "doc_type": d.doc_type,
                "title": d.title,
                "source": d.source,
                "observed_at": d.observed_at,
                "entities": d.entities,
            }
            for d in rows
        ],
        "limit": page.limit,
        "offset": page.offset,
    }


@router.get("/{document_id}")
def get_document(document_id: str, session: Session = Depends(get_session)) -> dict:
    document = session.get(NormalizedDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    raw = session.get(RawDocument, document.raw_document_id)
    evidence = list(session.scalars(select(Evidence).where(Evidence.normalized_document_id == document.id)))
    job = session.scalar(select(Job).where(Job.normalized_document_id == document.id))
    return {
        "id": document.id,
        "doc_type": document.doc_type,
        "title": document.title,
        "source": document.source,
        "observed_at": document.observed_at,
        "entities": document.entities,
        "body_text": document.body_text,
        "raw": {"source": raw.source, "external_id": raw.external_id} if raw else None,
        "job": None
        if job is None
        else {
            "title": job.title,
            "normalized_role": job.normalized_role,
            "seniority": job.seniority,
            "location": job.location,
            "remote_type": job.remote_type,
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
        },
        "evidence": [
            {"id": e.id, "entity_type": e.entity_type, "entity_name": e.entity_name, "period": e.period}
            for e in evidence
        ],
    }


@router.get("/evidence/{evidence_id}")
def get_evidence(evidence_id: str, session: Session = Depends(get_session)) -> dict:
    evidence = session.get(Evidence, evidence_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail="Evidence not found.")
    document = session.get(NormalizedDocument, evidence.normalized_document_id)
    return {
        "id": evidence.id,
        "entity_type": evidence.entity_type,
        "entity_name": evidence.entity_name,
        "period": evidence.period,
        "snippet": evidence.snippet,
        "source": evidence.source,
        "document": None if document is None else {"id": document.id, "title": document.title},
    }
