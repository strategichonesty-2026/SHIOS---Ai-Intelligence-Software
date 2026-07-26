"""Interval forecasts and coverage scoring.

Covers the v1.1 change that resolves ANALYSIS.md 5.1: predictions publish an 80% interval
computed from the OLS residual standard error, the Reality Check scores whether reality
landed inside it, and the Learning Agent's calibration delta becomes
`coverage - claimed interval confidence` — two numbers of the same kind.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.agents import LearningAgent, PredictionAgent, RealityCheckAgent
from app.agents.prediction import INTERVAL_CONFIDENCE, METHOD
from app.models.tables import LearningFeedback, Prediction, PredictionResult
from app.orchestrator.orchestrator import run_full_loop
from app.schemas.contracts import LearningFeedbackV1, PredictionRecordV1, PredictionResultV1
from app.services.stats import linear_fit, prediction_interval_80, t_quantile_80


@pytest.fixture
def seeded(db):
    """One full loop against the deterministic sample source: predictions published,
    backtests expired, reality checked, learning recorded."""
    run_full_loop(db, source_ids=["sample_jobs"], limit=1000)
    return db


# --- statistics --------------------------------------------------------------


def test_prediction_interval_matches_hand_computation():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [2.0, 4.0, 5.0, 4.0, 5.0]
    fit = linear_fit(xs, ys)

    # Recompute the half-width from first principles.
    x0 = 7.0
    point = fit.predict(x0)
    n = 5
    mean_x = 3.0
    sxx = sum((x - mean_x) ** 2 for x in xs)
    ss_res = sum((y - fit.predict(x)) ** 2 for x, y in zip(xs, ys, strict=True))
    s = (ss_res / (n - 2)) ** 0.5
    expected_half = 1.638 * s * (1 + 1 / n + (x0 - mean_x) ** 2 / sxx) ** 0.5

    lower, upper = prediction_interval_80(fit, x0)
    assert abs((upper - lower) / 2 - expected_half) < 1e-9
    assert abs((upper + lower) / 2 - point) < 1e-9
    assert lower < point < upper


def test_interval_widens_with_extrapolation_distance():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    ys = [3.0, 5.0, 4.0, 6.0, 7.0, 6.0]
    fit = linear_fit(xs, ys)
    near = prediction_interval_80(fit, 7.0)
    far = prediction_interval_80(fit, 12.0)
    assert (far[1] - far[0]) > (near[1] - near[0])


def test_t_quantile_table_edges():
    assert t_quantile_80(1) == 3.078
    assert t_quantile_80(30) == 1.310
    assert t_quantile_80(31) == 1.2816  # normal approximation beyond the table
    assert t_quantile_80(0) == 3.078  # defensive floor


def test_degenerate_fit_collapses_to_the_point():
    fit = linear_fit([1.0, 2.0], [3.0, 5.0])
    lower, upper = prediction_interval_80(fit, 4.0)
    assert lower == upper == fit.predict(4.0)


# --- prediction agent --------------------------------------------------------


def test_published_predictions_carry_an_ordered_interval(db, seeded):
    predictions = list(db.scalars(select(Prediction).where(Prediction.method == METHOD)))
    assert predictions, "no interval predictions were published"
    for prediction in predictions:
        assert prediction.lower_bound is not None
        assert prediction.upper_bound is not None
        assert prediction.interval_confidence == INTERVAL_CONFIDENCE
        assert 0.0 <= prediction.lower_bound <= prediction.upper_bound
        assert "at 80% confidence" in prediction.statement
        contract = PredictionRecordV1.model_validate(prediction)
        assert contract.lower_bound == prediction.lower_bound


def test_interval_predictions_remain_immutable_on_rerun(db, seeded):
    before = {p.id: (p.lower_bound, p.upper_bound) for p in db.scalars(select(Prediction))}
    output = PredictionAgent().run(db)
    assert output["predictions"] == 0, "re-running published a duplicate for the same target"
    after = {p.id: (p.lower_bound, p.upper_bound) for p in db.scalars(select(Prediction))}
    assert before == after


# --- reality check -----------------------------------------------------------


def test_reality_check_scores_coverage_not_just_points(db, seeded):
    results = list(db.scalars(select(PredictionResult)))
    assert results, "reality check produced no results"
    for result in results:
        prediction = db.get(Prediction, result.prediction_id)
        assert result.interval_covered is not None
        recomputed = prediction.lower_bound <= result.actual_value <= prediction.upper_bound
        assert result.interval_covered == recomputed
        assert ("covered" in result.notes) or ("missed" in result.notes)
        contract = PredictionResultV1.model_validate(result)
        assert contract.interval_covered == result.interval_covered


def test_legacy_point_prediction_still_scores_on_accuracy(db, seeded):
    # Clone an already-evaluated prediction: its target period is guaranteed to have an
    # observed actual, so the legacy row scores instead of going unverifiable.
    prediction = db.scalar(select(Prediction).where(Prediction.status == "evaluated"))
    assert prediction is not None, "full loop produced no evaluated prediction to clone"
    legacy = Prediction(
        statement="legacy point forecast for coverage-fallback test",
        domain="career",
        metric=prediction.metric,
        entity_type=prediction.entity_type,
        entity_name=prediction.entity_name,
        horizon=prediction.horizon,
        target_period=prediction.target_period,
        predicted_value=prediction.predicted_value,
        lower_bound=None,
        upper_bound=None,
        interval_confidence=None,
        predicted_direction=prediction.predicted_direction,
        confidence=0.5,
        supporting_evidence_ids=prediction.supporting_evidence_ids,
        trend_ids=prediction.trend_ids,
        assumptions=[],
        risks=[],
        method="ols_linear_v1",
        review_date=date.today() - timedelta(days=8),
        expiration_date=date.today() - timedelta(days=1),
        version=1,
        status="published",
    )
    db.add(legacy)
    db.flush()

    RealityCheckAgent().run(db, prediction_ids=[legacy.id])
    result = db.scalar(
        select(PredictionResult).where(PredictionResult.prediction_id == legacy.id)
    )
    assert result is not None
    assert result.interval_covered is None
    assert 0.0 <= result.accuracy_score <= 1.0

    LearningAgent().run(db, prediction_result_ids=[result.id])
    feedback = db.scalar(
        select(LearningFeedback).where(LearningFeedback.prediction_id == legacy.id)
    )
    assert feedback.coverage_correct is None
    assert feedback.confidence_calibration_delta == round(
        result.accuracy_score - legacy.confidence, 4
    )


# --- learning ----------------------------------------------------------------


def test_learning_records_coverage_and_a_coverage_delta(db, seeded):
    feedback_rows = list(db.scalars(select(LearningFeedback)))
    assert feedback_rows
    for feedback in feedback_rows:
        result = db.get(PredictionResult, feedback.prediction_result_id)
        prediction = db.get(Prediction, feedback.prediction_id)
        if result.interval_covered is None:
            continue
        assert feedback.coverage_correct == result.interval_covered
        expected = round(float(result.interval_covered) - prediction.interval_confidence, 4)
        assert feedback.confidence_calibration_delta == expected
        assert "interval_covered" in feedback.signal_quality_notes or (
            "interval_missed" in feedback.signal_quality_notes
        )
        contract = LearningFeedbackV1.model_validate(feedback)
        assert contract.coverage_correct == feedback.coverage_correct
    assert any(f.coverage_correct is not None for f in feedback_rows)


def test_calibration_delta_is_coverage_minus_nominal_in_aggregate(db, seeded):
    feedback_rows = [
        f for f in db.scalars(select(LearningFeedback)) if f.coverage_correct is not None
    ]
    assert feedback_rows
    empirical = sum(1.0 for f in feedback_rows if f.coverage_correct) / len(feedback_rows)
    mean_delta = sum(f.confidence_calibration_delta for f in feedback_rows) / len(feedback_rows)
    assert abs(mean_delta - (empirical - INTERVAL_CONFIDENCE)) < 1e-6
    # The point of the change: the delta is now bounded by the nominal level on both sides,
    # so a +0.50 structural skew is no longer possible.
    assert -INTERVAL_CONFIDENCE <= mean_delta <= 1.0 - INTERVAL_CONFIDENCE
