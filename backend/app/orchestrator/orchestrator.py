"""Agent orchestrator.

Simple, event-aware, in-process. Two entry points:

  run_mvp_loop()   Collect -> Extract -> Store -> Trend -> Recommend -> Dashboard  (spec 4)
  run_full_loop()  the MVP loop plus knowledge, backtest, reality check, learning, reporting

The full loop deliberately publishes a *backtested* forecast alongside the live one. Anchoring
a prediction at `latest - horizon` means its target period already has an observed actual, so
the Reality Check and Learning agents have something real to score on the very first run.
Without that, calibration would stay empty for a month and the loop would only look closed.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.agents import (
    CollectorAgent,
    ExtractionAgent,
    KnowledgeAgent,
    LearningAgent,
    PredictionAgent,
    RealityCheckAgent,
    RecommendationAgent,
    ReportingAgent,
    StrategicHonestyValidator,
    TrendAgent,
)
from app.schemas.contracts import PipelineResult
from app.services.periods import shift_period

log = logging.getLogger("shios.orchestrator")

# Weeks of extra lag applied to backtest anchors. Three anchors give the Learning Agent
# enough scored samples to start moving calibration on the very first run.
_BACKTEST_LAGS = (2, 3, 4)


def run_mvp_loop(
    session: Session,
    *,
    source_ids: list[str] | None = None,
    sources=None,
    limit: int = 500,
    horizon_weeks: int = 4,
    top_n: int = 5,
) -> PipelineResult:
    result = PipelineResult()

    collected = CollectorAgent().run(session, source_ids=source_ids, sources=sources, limit=limit)
    result.collected = collected["collected"]
    result.errors += [f"collector:{f['source']}:{f['error']}" for f in collected.get("failures", [])]

    extracted = ExtractionAgent().run(session, raw_document_ids=collected["raw_document_ids"] or None)
    result.normalized = extracted["normalized"]
    result.evidence = extracted["evidence_written"]

    trended = TrendAgent().run(session)
    result.trends = trended["trends"]

    predicted = PredictionAgent().run(session, horizon_weeks=horizon_weeks)
    result.predictions = predicted["predictions"]

    recommended = RecommendationAgent().run(session, top_n=top_n)
    result.recommendations = recommended.get("recommendations", 0)

    validated = StrategicHonestyValidator().run(session)
    result.validations = validated["validations"]

    return result


def run_full_loop(
    session: Session,
    *,
    source_ids: list[str] | None = None,
    limit: int = 500,
    horizon_weeks: int = 4,
    top_n: int = 5,
    report_types: list[str] | None = None,
    backtest: bool = True,
) -> PipelineResult:
    result = run_mvp_loop(
        session,
        source_ids=source_ids,
        limit=limit,
        horizon_weeks=horizon_weeks,
        top_n=top_n,
    )

    KnowledgeAgent().run(session)

    if backtest:
        latest = _latest_period(session)
        if latest:
            # A backtest is only useful if its target period has already expired under the
            # governance rules (target week end + 7 days). Anchoring at horizon+2 or further
            # back guarantees that, so the Reality Check agent has something real to score.
            earliest = _earliest_period(session)
            for lag in _BACKTEST_LAGS:
                anchor = shift_period(latest, -(horizon_weeks + lag))
                if not _anchor_is_usable(anchor, earliest):
                    log.info("skipping backtest anchor=%s: not enough history behind it", anchor)
                    continue
                backtested = PredictionAgent().run(
                    session, horizon_weeks=horizon_weeks, as_of_period=anchor
                )
                result.predictions += backtested["predictions"]

    checked = RealityCheckAgent().run(session)
    result.prediction_results = checked["prediction_results"]

    learned = LearningAgent().run(session)
    result.learning_feedback = learned["learning_feedback"]

    reported = ReportingAgent().run(session, report_types=report_types, top_n=top_n)
    result.reports = reported.get("reports", 0)

    return result


def run_agent(session: Session, name: str, **kwargs: Any) -> dict[str, Any]:
    from app.agents import get_agent

    return get_agent(name).run(session, **kwargs)


def _latest_period(session: Session) -> str | None:
    from sqlalchemy import func, select

    from app.models.tables import Trend

    return session.scalar(select(func.max(Trend.period)))


def _earliest_period(session: Session) -> str | None:
    from sqlalchemy import func, select

    from app.models.tables import Trend

    return session.scalar(select(func.min(Trend.period)))


def _anchor_is_usable(anchor: str, earliest: str | None) -> bool:
    """A backtest anchor needs at least `min_periods_for_prediction` weeks of history behind it."""
    if earliest is None:
        return False
    from app.config import settings
    from app.services.periods import period_index

    return period_index(anchor) - period_index(earliest) >= settings.min_periods_for_prediction - 1
