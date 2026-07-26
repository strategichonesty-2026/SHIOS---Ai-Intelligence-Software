from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import AGENTS
from app.db import get_session, session_scope
from app.models.tables import AgentRun, EventLog
from app.orchestrator.orchestrator import run_agent, run_full_loop, run_mvp_loop

router = APIRouter(prefix="/runs", tags=["orchestration"])


@router.post("/pipeline")
def trigger_pipeline(
    background_tasks: BackgroundTasks,
    mode: str = Body(default="full", embed=True),
    source_ids: list[str] | None = Body(default=None, embed=True),
    limit: int = Body(default=500, embed=True),
    horizon_weeks: int = Body(default=4, embed=True),
    background: bool = Body(default=False, embed=True),
    session: Session = Depends(get_session),
) -> dict:
    if mode not in {"full", "mvp"}:
        raise HTTPException(status_code=422, detail="Mode must be 'full' or 'mvp'.")

    def execute() -> dict:
        with session_scope() as scoped:
            runner = run_full_loop if mode == "full" else run_mvp_loop
            return runner(
                scoped, source_ids=source_ids, limit=limit, horizon_weeks=horizon_weeks
            ).model_dump()

    if background:
        background_tasks.add_task(execute)
        return {"status": "accepted", "mode": mode}
    return {"status": "completed", "mode": mode, "result": execute()}


@router.post("/agents/{name}")
def trigger_agent(
    name: str,
    payload: dict = Body(default_factory=dict),
    session: Session = Depends(get_session),
) -> dict:
    if name not in AGENTS:
        raise HTTPException(status_code=404, detail=f"Unknown agent. Known: {sorted(AGENTS)}")
    with session_scope() as scoped:
        return {"agent": name, "result": run_agent(scoped, name, **payload)}


@router.get("")
def list_runs(
    agent: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> dict:
    query = select(AgentRun).order_by(AgentRun.started_at.desc())
    if agent:
        query = query.where(AgentRun.agent == agent)
    rows = list(session.scalars(query.limit(limit)))
    return {
        "items": [
            {
                "id": r.id,
                "agent": r.agent,
                "agent_version": r.agent_version,
                "status": r.status,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
                "duration_ms": r.duration_ms,
                "outputs": r.outputs,
                "error": r.error,
            }
            for r in rows
        ]
    }


@router.get("/events")
def list_events(
    name: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> dict:
    query = select(EventLog).order_by(EventLog.created_at.desc())
    if name:
        query = query.where(EventLog.name == name)
    rows = list(session.scalars(query.limit(limit)))
    return {
        "items": [
            {"id": e.id, "name": e.name, "payload": e.payload, "created_at": e.created_at} for e in rows
        ]
    }
