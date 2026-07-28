"""Executive Intelligence endpoints.

Three additions that make the system answer "how do we know?" for every artefact:

  GET /evidence/breakdown        what the evidence base is actually made of
  GET /jobs                      the job corpus as a first-class, filterable surface
  GET /trust/{type}/{id}         one uniform Trust Panel payload for any artefact

Design rule carried over from the rest of SHIOS: nothing here invents a category,
a rating, or a number. Source categories are derived from documents actually
collected; source types the system does *not* read are listed explicitly under
`not_collected` so the gap is visible rather than silently omitted.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.tables import (
    Company,
    Evidence,
    Job,
    NormalizedDocument,
    Prediction,
    PredictionResult,
    Recommendation,
    Report,
    Trend,
    ValidationResult,
)

router = APIRouter(tags=["intelligence"])

# --- source catalogue ------------------------------------------------------
# Rating is a stated editorial assessment with an explicit basis, not a computed
# score. Anything synthetic is flagged so it can never be mistaken for market signal.

SOURCE_CATALOGUE: dict[str, dict[str, Any]] = {
    "sample_jobs": {
        "label": "Synthetic job postings",
        "category": "Job Postings",
        "reliability": "reference-only",
        "basis": "Deterministically generated for demonstration and testing. Not market data.",
        "synthetic": True,
        "primary": False,
    },
    "rss": {
        "label": "News & article feeds",
        "category": "News & Articles",
        "reliability": "moderate",
        "basis": "Publisher-controlled feeds. Timely, but headline-led and not first-party hiring data.",
        "synthetic": False,
        "primary": False,
    },
    "github": {
        "label": "GitHub repositories",
        "category": "Open-Source Repositories",
        "reliability": "high",
        "basis": "First-party developer activity from the GitHub API. Leading indicator, not a hiring signal.",
        "synthetic": False,
        "primary": True,
    },
    "gmail_linkedin_jobs": {
        "label": "LinkedIn job alerts (email)",
        "category": "Job Postings",
        "reliability": "high",
        "basis": "First-party job alerts delivered to the operator's inbox. Narrow by construction.",
        "synthetic": False,
        "primary": True,
    },
}

DOC_TYPE_CATEGORY = {
    "job": "Job Postings",
    "article": "News & Articles",
    "repo": "Open-Source Repositories",
    "email": "Job Postings",
    "other": "Uncategorised",
}

# Source types this specification asks for that SHIOS does not currently read.
# Listed so the UI can show the gap instead of implying coverage that isn't there.
NOT_COLLECTED = [
    {"category": "Research Papers", "note": "No arXiv/Semantic Scholar collector exists yet."},
    {"category": "Company Career Pages", "note": "No direct ATS/career-site scraper exists yet."},
    {"category": "Government Data", "note": "No BLS/ONS or equivalent labour-statistics collector exists yet."},
    {"category": "SEC Filings", "note": "No EDGAR collector exists yet."},
    {"category": "User Uploaded Documents", "note": "No upload ingestion path exists yet."},
]


# ---------------------------------------------------------------------------
# 3. Evidence base breakdown
# ---------------------------------------------------------------------------


@router.get("/evidence/breakdown")
def evidence_breakdown(session: Session = Depends(get_session)) -> dict:
    """What the evidence base is actually made of, by category and by source."""
    rows = session.execute(
        select(
            Evidence.source,
            NormalizedDocument.doc_type,
            func.count(Evidence.id),
            func.max(NormalizedDocument.observed_at),
            func.count(func.distinct(Evidence.normalized_document_id)),
        )
        .join(NormalizedDocument, NormalizedDocument.id == Evidence.normalized_document_id)
        .group_by(Evidence.source, NormalizedDocument.doc_type)
    ).all()

    total_evidence = session.scalar(select(func.count()).select_from(Evidence)) or 0
    total_documents = session.scalar(select(func.count()).select_from(NormalizedDocument)) or 0

    by_category: dict[str, dict[str, Any]] = {}
    sources: list[dict[str, Any]] = []

    for source, doc_type, evidence_count, last_seen, doc_count in rows:
        meta = SOURCE_CATALOGUE.get(
            source,
            {
                "label": source,
                "category": DOC_TYPE_CATEGORY.get(doc_type, "Uncategorised"),
                "reliability": "unrated",
                "basis": "Source is not in the catalogue; no assessment has been recorded.",
                "synthetic": False,
                "primary": False,
            },
        )
        category = DOC_TYPE_CATEGORY.get(doc_type, meta["category"])

        sources.append(
            {
                "source": source,
                "label": meta["label"],
                "category": category,
                "doc_type": doc_type,
                "evidence_count": int(evidence_count),
                "document_count": int(doc_count),
                "last_updated": last_seen,
                "reliability": meta["reliability"],
                "reliability_basis": meta["basis"],
                "synthetic": meta["synthetic"],
                "primary_source": meta["primary"],
            }
        )

        bucket = by_category.setdefault(
            category,
            {
                "category": category,
                "evidence_count": 0,
                "document_count": 0,
                "last_updated": None,
                "sources": [],
                "synthetic_only": True,
            },
        )
        bucket["evidence_count"] += int(evidence_count)
        bucket["document_count"] += int(doc_count)
        bucket["sources"].append(source)
        if not meta["synthetic"]:
            bucket["synthetic_only"] = False
        if last_seen and (bucket["last_updated"] is None or last_seen > bucket["last_updated"]):
            bucket["last_updated"] = last_seen

    return {
        "total_evidence": total_evidence,
        "total_documents": total_documents,
        "categories": sorted(by_category.values(), key=lambda c: c["evidence_count"], reverse=True),
        "sources": sorted(sources, key=lambda s: s["evidence_count"], reverse=True),
        "not_collected": NOT_COLLECTED,
        "note": (
            "Categories reflect documents the system actually collected. Source types under "
            "'not_collected' have no collector yet and are shown so the gap is visible."
        ),
    }


@router.get("/evidence/by-source/{source}")
def evidence_by_source(
    source: str,
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> dict:
    """Drill from a source straight into the underlying documents."""
    rows = session.execute(
        select(
            Evidence.id,
            Evidence.entity_type,
            Evidence.entity_name,
            Evidence.period,
            Evidence.snippet,
            NormalizedDocument.id,
            NormalizedDocument.title,
            NormalizedDocument.doc_type,
            NormalizedDocument.observed_at,
        )
        .join(NormalizedDocument, NormalizedDocument.id == Evidence.normalized_document_id)
        .where(Evidence.source == source)
        .order_by(NormalizedDocument.observed_at.desc())
        .limit(limit)
    ).all()

    meta = SOURCE_CATALOGUE.get(source)
    return {
        "source": source,
        "label": meta["label"] if meta else source,
        "reliability": meta["reliability"] if meta else "unrated",
        "reliability_basis": meta["basis"] if meta else "Source is not in the catalogue.",
        "synthetic": meta["synthetic"] if meta else False,
        "items": [
            {
                "evidence_id": r[0],
                "entity_type": r[1],
                "entity_name": r[2],
                "period": r[3],
                "snippet": r[4],
                "document_id": r[5],
                "title": r[6],
                "doc_type": r[7],
                "observed_at": r[8],
            }
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# 8. Job intelligence
# ---------------------------------------------------------------------------


@router.get("/jobs")
def list_jobs(
    role: str | None = Query(default=None),
    seniority: str | None = Query(default=None),
    remote_type: str | None = Query(default=None),
    company: str | None = Query(default=None),
    skill: str | None = Query(default=None),
    has_salary: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> dict:
    """The job corpus as a first-class surface, not just trend fuel."""
    query = (
        select(Job, Company.name, NormalizedDocument.source)
        .join(NormalizedDocument, NormalizedDocument.id == Job.normalized_document_id)
        .outerjoin(Company, Company.id == Job.company_id)
    )
    if role:
        query = query.where(Job.normalized_role == role)
    if seniority:
        query = query.where(Job.seniority == seniority)
    if remote_type:
        query = query.where(Job.remote_type == remote_type)
    if company:
        query = query.where(Company.name == company)
    if has_salary is True:
        query = query.where(Job.salary_min.is_not(None))
    elif has_salary is False:
        query = query.where(Job.salary_min.is_(None))

    total = session.scalar(
        select(func.count()).select_from(query.subquery())
    ) or 0

    rows = session.execute(
        query.order_by(Job.posted_at.desc()).limit(limit).offset(offset)
    ).all()

    items = []
    for job, company_name, source in rows:
        # Skill filter applied in Python: skills live in a JSON column and the
        # corpus is small enough that a portable filter beats a dialect-specific one.
        if skill and skill not in (job.skills or []):
            continue
        items.append(
            {
                "id": job.id,
                "position": job.title,
                "normalized_role": job.normalized_role,
                "company": company_name,
                "location": job.location,
                "remote_type": job.remote_type,
                "seniority": job.seniority,
                "salary_min": job.salary_min,
                "salary_max": job.salary_max,
                "salary_known": job.salary_min is not None,
                "posted_at": job.posted_at,
                "collected_at": job.created_at,
                "source": source,
                "synthetic": SOURCE_CATALOGUE.get(source, {}).get("synthetic", False),
                "skills": job.skills or [],
                "technologies": job.technologies or [],
                "document_id": job.normalized_document_id,
            }
        )

    return {
        "total": total,
        "returned": len(items),
        "limit": limit,
        "offset": offset,
        "items": items,
        "note": (
            "Industry is not captured by the current extractor; normalized_role is the "
            "closest available classification."
        ),
    }


@router.get("/jobs/facets")
def job_facets(session: Session = Depends(get_session)) -> dict:
    """Filter options, derived from the data rather than hard-coded."""

    def distinct(column) -> list[str]:
        return sorted({v for (v,) in session.execute(select(column).distinct()).all() if v})

    salaried = session.scalar(
        select(func.count()).select_from(Job).where(Job.salary_min.is_not(None))
    ) or 0
    total = session.scalar(select(func.count()).select_from(Job)) or 0

    skills: set[str] = set()
    for (job_skills,) in session.execute(select(Job.skills)).all():
        skills.update(job_skills or [])

    return {
        "roles": distinct(Job.normalized_role),
        "seniority": distinct(Job.seniority),
        "remote_type": distinct(Job.remote_type),
        "companies": distinct(Company.name),
        "skills": sorted(skills),
        "total_jobs": total,
        "with_salary": salaried,
        "salary_coverage": round(salaried / total, 4) if total else None,
    }


# ---------------------------------------------------------------------------
# 6 + 9. Trust panel
# ---------------------------------------------------------------------------


def _source_diversity(session: Session, evidence_ids: list[str]) -> dict:
    """How many distinct sources stand behind a claim, and which."""
    if not evidence_ids:
        return {"distinct_sources": 0, "sources": [], "concentration": None}
    rows = session.execute(
        select(Evidence.source, func.count(Evidence.id))
        .where(Evidence.id.in_(evidence_ids))
        .group_by(Evidence.source)
    ).all()
    total = sum(int(c) for _, c in rows) or 1
    breakdown = [
        {"source": s, "count": int(c), "share": round(int(c) / total, 4)} for s, c in rows
    ]
    breakdown.sort(key=lambda b: b["count"], reverse=True)
    return {
        "distinct_sources": len(breakdown),
        "sources": breakdown,
        # 1.0 means every piece of evidence came from a single source.
        "concentration": breakdown[0]["share"] if breakdown else None,
    }


def _related_documents(session: Session, evidence_ids: list[str], limit: int = 12) -> list[dict]:
    if not evidence_ids:
        return []
    rows = session.execute(
        select(
            NormalizedDocument.id,
            NormalizedDocument.title,
            NormalizedDocument.doc_type,
            NormalizedDocument.source,
            NormalizedDocument.observed_at,
        )
        .join(Evidence, Evidence.normalized_document_id == NormalizedDocument.id)
        .where(Evidence.id.in_(evidence_ids))
        .distinct()
        .limit(limit)
    ).all()
    return [
        {"document_id": r[0], "title": r[1], "doc_type": r[2], "source": r[3], "observed_at": r[4]}
        for r in rows
    ]


@router.get("/trust/{target_type}/{target_id}")
def trust_panel(target_type: str, target_id: str, session: Session = Depends(get_session)) -> dict:
    """One uniform trust payload for a prediction, recommendation, trend or report."""
    if target_type not in {"prediction", "recommendation", "trend", "report"}:
        raise HTTPException(status_code=422, detail="target_type must be prediction, recommendation, trend or report.")

    evidence_ids: list[str] = []
    confidence: float | None = None
    last_updated: datetime | None = None
    explainability: dict[str, Any] = {}
    reality: dict[str, Any] | None = None
    history: dict[str, Any] | None = None
    headline = ""

    if target_type == "prediction":
        prediction = session.get(Prediction, target_id)
        if prediction is None:
            raise HTTPException(status_code=404, detail="Prediction not found.")
        evidence_ids = list(prediction.supporting_evidence_ids or [])
        confidence = prediction.confidence
        last_updated = prediction.created_at
        headline = prediction.statement
        explainability = {
            "method": prediction.method,
            "assumptions": prediction.assumptions,
            "risks": prediction.risks,
            "horizon": prediction.horizon,
            "target_period": prediction.target_period,
            "review_date": prediction.review_date,
            "immutable": True,
        }
        result = session.scalar(
            select(PredictionResult).where(PredictionResult.prediction_id == target_id)
        )
        reality = (
            None
            if result is None
            else {
                "scored": True,
                "predicted_value": result.predicted_value,
                "actual_value": result.actual_value,
                "accuracy_score": result.accuracy_score,
                "direction_correct": result.direction_correct,
                "evaluated_at": result.evaluated_at,
                "notes": result.notes,
            }
        )
        if reality is None:
            reality = {"scored": False, "status": prediction.status}
        # How this entity's forecasts have fared historically.
        siblings = list(
            session.scalars(
                select(Prediction)
                .where(Prediction.entity_type == prediction.entity_type)
                .where(Prediction.entity_name == prediction.entity_name)
            )
        )
        scored = list(
            session.scalars(
                select(PredictionResult).where(
                    PredictionResult.prediction_id.in_([p.id for p in siblings])
                )
            )
        )
        history = {
            "entity": prediction.entity_name,
            "forecasts_published": len(siblings),
            "forecasts_scored": len(scored),
            "mean_accuracy": round(sum(s.accuracy_score for s in scored) / len(scored), 4)
            if scored
            else None,
        }

    elif target_type == "recommendation":
        recommendation = session.get(Recommendation, target_id)
        if recommendation is None:
            raise HTTPException(status_code=404, detail="Recommendation not found.")
        evidence_ids = list(recommendation.evidence_ids or [])
        confidence = recommendation.confidence
        last_updated = recommendation.created_at
        headline = recommendation.recommendation_text
        explainability = {
            "rationale": recommendation.rationale,
            "risks": recommendation.risks,
            "alternative_scenarios": recommendation.alternative_scenarios,
            "expected_outcomes": recommendation.expected_outcomes,
            "status": recommendation.status,
            "derived_from_prediction": recommendation.prediction_id,
        }
        validations = list(
            session.scalars(
                select(ValidationResult)
                .where(ValidationResult.target_type == "recommendation")
                .where(ValidationResult.target_id == target_id)
                .order_by(ValidationResult.validated_at.desc())
            )
        )
        reality = {
            "scored": False,
            "validated": bool(validations and validations[0].is_valid),
            "issues": validations[0].issues if validations else [],
            "unknowns_noted": validations[0].unknowns_noted if validations else [],
        }

    elif target_type == "trend":
        trend = session.get(Trend, target_id)
        if trend is None:
            raise HTTPException(status_code=404, detail="Trend not found.")
        evidence_ids = list(trend.evidence_ids or [])
        last_updated = trend.computed_at
        headline = f"{trend.entity_name} — {trend.metric} in {trend.period}"
        explainability = {
            "method": "count of distinct documents mentioning the entity in the ISO week",
            "metric": trend.metric,
            "period": trend.period,
            "value": trend.value,
            "delta": trend.delta,
            "direction": trend.direction,
            "sample_size": trend.sample_size,
            "immutable": False,
        }
        reality = {"scored": False, "note": "Trends are counts, not estimates — nothing to score."}

    else:  # report
        report = session.get(Report, target_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found.")
        evidence_ids = list(report.evidence_ids or [])
        last_updated = report.created_at
        headline = report.title
        explainability = {
            "report_type": report.report_type,
            "period_start": report.period_start,
            "period_end": report.period_end,
            "note": "Every figure in a report is restated from a trend, prediction or result row.",
        }
        reality = {"scored": False}

    return {
        "target_type": target_type,
        "target_id": target_id,
        "headline": headline,
        "evidence_count": len({e for e in evidence_ids if e}),
        "confidence": confidence,
        "source_diversity": _source_diversity(session, evidence_ids),
        "last_updated": last_updated,
        "prediction_history": history,
        "reality_validation": reality,
        "explainability": explainability,
        "related_sources": _related_documents(session, evidence_ids),
    }
