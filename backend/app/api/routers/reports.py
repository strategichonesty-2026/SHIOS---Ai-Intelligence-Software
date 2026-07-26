from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Page
from app.db import get_session
from app.models.tables import Report

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("")
def list_reports(
    report_type: str | None = Query(default=None),
    page: Page = Depends(),
    session: Session = Depends(get_session),
) -> dict:
    query = select(Report).order_by(Report.created_at.desc())
    if report_type:
        query = query.where(Report.report_type == report_type)
    rows = list(session.scalars(query.limit(page.limit).offset(page.offset)))
    return {
        "items": [
            {
                "id": r.id,
                "report_type": r.report_type,
                "title": r.title,
                "subtitle": r.subtitle,
                "period_start": r.period_start,
                "period_end": r.period_end,
                "created_at": r.created_at,
            }
            for r in rows
        ],
        "limit": page.limit,
        "offset": page.offset,
    }


@router.get("/{report_id}")
def get_report(report_id: str, session: Session = Depends(get_session)) -> dict:
    report = session.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    return {
        "id": report.id,
        "report_type": report.report_type,
        "title": report.title,
        "subtitle": report.subtitle,
        "body_markdown": report.body_markdown,
        "payload": report.payload,
        "evidence_ids": report.evidence_ids,
        "period_start": report.period_start,
        "period_end": report.period_end,
        "created_at": report.created_at,
    }


@router.get("/{report_id}/export.md", response_class=Response)
def export_report(report_id: str, session: Session = Depends(get_session)) -> Response:
    report = session.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    return Response(
        content=report.body_markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{report.report_type}-{report.period_end}.md"'},
    )
