"""Periodic execution.

Off by default (SCHEDULER_ENABLED=false) so that running the API never mutates data by
surprise. When enabled, collection and analysis run on independent intervals: collection is
cheap and frequent, analysis is heavier and less frequent.
"""

from __future__ import annotations

import logging

from app.config import settings
from app.db import session_scope
from app.orchestrator.orchestrator import run_full_loop

log = logging.getLogger("shios.scheduler")

_scheduler = None


def collect_job() -> None:
    from app.agents import CollectorAgent, ExtractionAgent

    with session_scope() as session:
        collected = CollectorAgent().run(session)
        ExtractionAgent().run(session, raw_document_ids=collected["raw_document_ids"] or None)
        log.info("scheduled collection complete collected=%s", collected["collected"])


def analyze_job() -> None:
    with session_scope() as session:
        result = run_full_loop(session, backtest=False)
        log.info("scheduled analysis complete trends=%s predictions=%s", result.trends, result.predictions)


def start_scheduler():  # pragma: no cover - runtime wiring
    global _scheduler
    if not settings.scheduler_enabled or _scheduler is not None:
        return _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        log.warning("apscheduler not installed; scheduler disabled")
        return None

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(collect_job, "interval", minutes=settings.collect_interval_minutes, id="collect")
    _scheduler.add_job(analyze_job, "interval", minutes=settings.analyze_interval_minutes, id="analyze")
    _scheduler.start()
    log.info(
        "scheduler started collect=%smin analyze=%smin",
        settings.collect_interval_minutes,
        settings.analyze_interval_minutes,
    )
    return _scheduler


def stop_scheduler() -> None:  # pragma: no cover - runtime wiring
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
