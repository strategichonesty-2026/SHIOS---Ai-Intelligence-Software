"""End-to-end tests for the intelligence loop.

These are the tests that matter most: they assert that the loop actually closes — evidence
becomes trends, trends become forecasts, forecasts get scored, and scores change confidence.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models.tables import (
    AgentRun,
    EventLog,
    Evidence,
    LearningFeedback,
    NormalizedDocument,
    Prediction,
    PredictionResult,
    RawDocument,
    Recommendation,
    Report,
    Trend,
    ValidationResult,
)
from app.orchestrator.orchestrator import run_full_loop, run_mvp_loop
from app.sources.sample_jobs import SampleJobsSource


def _count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


@pytest.mark.slow
def test_mvp_loop_produces_the_specified_chain(db):
    result = run_mvp_loop(db, source_ids=["sample_jobs"], limit=1000)

    assert result.collected > 0
    assert result.normalized == result.collected
    assert result.evidence > 0
    assert result.trends > 0
    assert result.recommendations > 0
    assert result.errors == []

    assert _count(db, RawDocument) == result.collected
    assert _count(db, NormalizedDocument) == result.normalized
    assert _count(db, Evidence) == result.evidence


@pytest.mark.slow
def test_full_loop_closes_the_learning_cycle(db):
    result = run_full_loop(db, source_ids=["sample_jobs"], limit=1000)

    assert result.predictions > 0, "no forecast survived governance"
    assert result.prediction_results > 0, "reality check never ran against an actual"
    assert result.learning_feedback == result.prediction_results
    assert result.reports > 0

    # Every scored result must trace back to a real prediction and forward to feedback.
    for feedback in db.scalars(select(LearningFeedback)):
        assert db.get(Prediction, feedback.prediction_id) is not None
        assert db.get(PredictionResult, feedback.prediction_result_id) is not None


@pytest.mark.slow
def test_collection_is_idempotent(db):
    first = run_mvp_loop(db, source_ids=["sample_jobs"], limit=150)
    second = run_mvp_loop(db, source_ids=["sample_jobs"], limit=150)

    assert second.collected == 0, "duplicate documents were re-collected"
    assert _count(db, RawDocument) == first.collected


@pytest.mark.slow
def test_trend_recomputation_is_stable(db):
    run_mvp_loop(db, source_ids=["sample_jobs"], limit=150)
    before = {(t.entity_type, t.entity_name, t.period): t.value for t in db.scalars(select(Trend))}

    from app.agents import TrendAgent

    TrendAgent().run(db)
    after = {(t.entity_type, t.entity_name, t.period): t.value for t in db.scalars(select(Trend))}

    assert before == after


@pytest.mark.slow
def test_predictions_are_not_duplicated_for_the_same_target(db):
    run_mvp_loop(db, source_ids=["sample_jobs"], limit=150)
    before = _count(db, Prediction)

    from app.agents import PredictionAgent

    output = PredictionAgent().run(db, horizon_weeks=4)

    assert output["predictions"] == 0
    assert output["skipped"] > 0
    assert _count(db, Prediction) == before


@pytest.mark.slow
def test_every_recommendation_carries_at_least_two_evidence_ids(db):
    run_full_loop(db, source_ids=["sample_jobs"], limit=1000)

    recommendations = list(db.scalars(select(Recommendation)))
    assert recommendations
    for recommendation in recommendations:
        assert len(set(recommendation.evidence_ids)) >= 2
        assert recommendation.trend_ids or recommendation.prediction_id


@pytest.mark.slow
def test_truth_maintenance_chain_has_no_dangling_references(db):
    run_full_loop(db, source_ids=["sample_jobs"], limit=1000)

    evidence_ids = set(db.scalars(select(Evidence.id)))
    trend_ids = set(db.scalars(select(Trend.id)))

    for prediction in db.scalars(select(Prediction)):
        assert set(prediction.trend_ids).issubset(trend_ids)
        assert set(prediction.supporting_evidence_ids).issubset(evidence_ids)

    for result in db.scalars(select(PredictionResult)):
        assert db.get(Prediction, result.prediction_id) is not None


@pytest.mark.slow
def test_predictions_respect_the_ninety_day_review_rule(db):
    run_full_loop(db, source_ids=["sample_jobs"], limit=1000)

    for prediction in db.scalars(select(Prediction)):
        assert 0.0 <= prediction.confidence <= 1.0
        assert prediction.expiration_date >= prediction.review_date
        assert (prediction.expiration_date - prediction.review_date).days <= 90


@pytest.mark.slow
def test_validator_records_unknowns_for_every_artefact(db):
    run_full_loop(db, source_ids=["sample_jobs"], limit=1000)

    validations = list(db.scalars(select(ValidationResult)))
    assert validations
    assert all(v.unknowns_noted for v in validations)


@pytest.mark.slow
def test_learning_feedback_moves_confidence_on_a_second_pass(db):
    run_full_loop(db, source_ids=["sample_jobs"], limit=1000)

    from app.services.calibration import calibration_multiplier

    multiplier = calibration_multiplier(db, "job_postings_count", "skill")
    assert multiplier != 1.0, "scored forecasts did not feed back into confidence"


@pytest.mark.slow
def test_agent_runs_and_events_are_logged(db):
    run_full_loop(db, source_ids=["sample_jobs"], limit=150)

    runs = list(db.scalars(select(AgentRun)))
    assert runs
    assert all(r.status == "success" for r in runs)
    assert all(r.duration_ms >= 0 and r.agent_version for r in runs)

    events = {e.name for e in db.scalars(select(EventLog))}
    assert {"document.collected", "document.normalized", "trend.updated"}.issubset(events)


@pytest.mark.slow
def test_reports_are_generated_with_evidence(db):
    run_full_loop(db, source_ids=["sample_jobs"], limit=1000)

    reports = list(db.scalars(select(Report)))
    assert reports
    for report in reports:
        assert report.body_markdown.strip()
        assert report.period_end

    types = {r.report_type for r in reports}
    assert "linkedin_article_draft" in types
    assert "linkedin_post_draft" in types


@pytest.mark.slow
def test_sample_source_is_deterministic():
    first = SampleJobsSource(weeks=6, seed=7).collect(limit=60)
    second = SampleJobsSource(weeks=6, seed=7).collect(limit=60)

    assert [i.external_id for i in first] == [i.external_id for i in second]
    assert [i.content_hash for i in first] == [i.content_hash for i in second]
