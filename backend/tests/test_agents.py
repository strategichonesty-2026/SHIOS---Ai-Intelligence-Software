"""Agent-level tests: contracts, failure isolation and honesty behaviour."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.agents import AGENTS, CollectorAgent, ExtractionAgent, RecommendationAgent
from app.agents.base import Agent
from app.agents.validator import StrategicHonestyValidator
from app.models.tables import AgentRun, Evidence, Prediction, Recommendation, Trend, ValidationResult
from app.orchestrator.orchestrator import run_mvp_loop
from app.schemas.contracts import PredictionRecordV1, RecommendationRecordV1, TrendRecordV1
from app.sources.base import CollectedItem, Source, SourceUnavailable


class BrokenSource(Source):
    source_id = "sample_jobs"
    doc_type = "job"

    def collect(self, limit: int = 100):
        raise SourceUnavailable("upstream is down")


class TinySource(Source):
    source_id = "rss"
    doc_type = "article"

    def collect(self, limit: int = 100):
        return [
            CollectedItem(
                external_id="tiny-1",
                content="Senior Agile Coach wanted. Scrum, coaching and change management in AWS.",
                doc_type="article",
                metadata={"title": "Tiny article"},
            )
        ]


@pytest.mark.slow
def test_every_agent_answers_the_governance_questions():
    for name, cls in AGENTS.items():
        governance = cls.governance()
        assert governance["agent"] == name
        required = (
            "supports_decision",
            "requires_evidence",
            "confidence_method",
            "correctness_check",
            "success_metric",
        )
        for field in required:
            assert governance[field].strip(), f"{name} has no answer for {field}"


@pytest.mark.slow
def test_failing_source_is_isolated_and_logged(db):
    output = CollectorAgent().run(db, sources=[BrokenSource(), TinySource()])

    assert output["collected"] == 1, "a healthy source was blocked by a failing one"
    assert output["failures"] and output["failures"][0]["source"] == "sample_jobs"

    from app.models.tables import EventLog

    events = {e.name for e in db.scalars(select(EventLog))}
    assert "document.collection_failed" in events


@pytest.mark.slow
def test_agent_run_is_recorded_on_failure(db):
    class Exploding(Agent):
        name = "exploding"

        def execute(self, session, **kwargs):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        Exploding().run(db)

    run = db.scalar(select(AgentRun).where(AgentRun.agent == "exploding"))
    assert run is not None
    assert run.status == "failed"
    assert "boom" in run.error


@pytest.mark.slow
def test_extraction_writes_evidence_for_recognised_entities(db):
    collected = CollectorAgent().run(db, sources=[TinySource()])
    output = ExtractionAgent().run(db, raw_document_ids=collected["raw_document_ids"])

    assert output["normalized"] == 1
    evidence = list(db.scalars(select(Evidence)))
    assert evidence
    names = {e.entity_name for e in evidence}
    assert "agile delivery" in names or "coaching" in names
    assert all(e.snippet for e in evidence)


@pytest.mark.slow
def test_trend_agent_produces_a_gap_free_series(db):
    run_mvp_loop(db, source_ids=["sample_jobs"], limit=1000)

    rows = list(db.scalars(
        select(Trend)
        .where(Trend.entity_type == "skill")
        .where(Trend.metric == "job_postings_count")
    ))
    by_entity: dict[str, list[str]] = {}
    for trend in rows:
        by_entity.setdefault(trend.entity_name, []).append(trend.period)

    for periods in by_entity.values():
        assert len(periods) == len(set(periods)), "duplicate period in a series"
        assert periods == sorted(periods) or sorted(periods) == sorted(set(periods))


@pytest.mark.slow
def test_records_satisfy_their_published_contracts(db):
    run_mvp_loop(db, source_ids=["sample_jobs"], limit=1000)

    trend = db.scalar(select(Trend))
    contract = TrendRecordV1.model_validate(trend)
    assert contract.schema_version == "v1"

    prediction = db.scalar(select(Prediction))
    assert PredictionRecordV1.model_validate(prediction).confidence <= 1.0

    recommendation = db.scalar(select(Recommendation))
    assert len(RecommendationRecordV1.model_validate(recommendation).evidence_ids) >= 2


@pytest.mark.slow
def test_recommendation_agent_refuses_without_evidence(db):
    run_mvp_loop(db, source_ids=["sample_jobs"], limit=1000)

    prediction = db.scalar(select(Prediction).where(Prediction.status == "published"))
    prediction.supporting_evidence_ids = []
    db.flush()

    before = db.query(Recommendation).count()
    output = RecommendationAgent().run(db, prediction_ids=[prediction.id], top_n=1)

    assert output["recommendations"] == 0
    assert output["rejected_by_governance"], "governance rejection was not reported"
    assert db.query(Recommendation).count() == before


@pytest.mark.slow
def test_validator_flags_a_dangling_reference(db):
    run_mvp_loop(db, source_ids=["sample_jobs"], limit=1000)

    recommendation = db.scalar(select(Recommendation))
    recommendation.evidence_ids = ["does-not-exist-1", "does-not-exist-2"]
    db.flush()

    StrategicHonestyValidator().run(db, recommendation_ids=[recommendation.id])

    validation = db.scalar(
        select(ValidationResult)
        .where(ValidationResult.target_id == recommendation.id)
        .order_by(ValidationResult.validated_at.desc())
    )
    assert not validation.is_valid
    assert validation.missing_evidence
    assert recommendation.status == "needs_review"


@pytest.mark.slow
def test_reality_check_marks_unverifiable_rather_than_scoring_a_guess(db):
    run_mvp_loop(db, source_ids=["sample_jobs"], limit=1000)

    from app.agents import RealityCheckAgent

    prediction = db.scalar(select(Prediction).where(Prediction.status == "published"))
    prediction.entity_name = "entity-with-no-actuals"
    prediction.expiration_date = date.today() - timedelta(days=1)
    db.flush()

    output = RealityCheckAgent().run(db, prediction_ids=[prediction.id])

    assert output["prediction_results"] == 0
    assert output["unverifiable"] == 1
    assert prediction.status == "unverifiable"
