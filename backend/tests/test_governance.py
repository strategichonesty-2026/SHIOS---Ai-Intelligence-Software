from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.governance.rules import (
    GovernanceError,
    default_review_dates,
    enforce,
    evaluate_prediction,
    evaluate_recommendation,
)

TODAY = date(2026, 7, 25)


def test_recommendation_requires_two_evidence_ids():
    report = evaluate_recommendation(
        confidence=0.6,
        evidence_ids=["e1"],
        trend_ids=["t1"],
        prediction_id="p1",
        text="Build capability in agile delivery over the next quarter.",
    )
    assert not report.is_valid
    assert any("MIN_EVIDENCE" in m for m in report.messages)


def test_recommendation_passes_with_two_evidence_and_a_reference():
    report = evaluate_recommendation(
        confidence=0.6,
        evidence_ids=["e1", "e2"],
        trend_ids=["t1"],
        prediction_id=None,
        text="Build capability in agile delivery over the next quarter.",
    )
    assert report.is_valid


def test_recommendation_requires_a_trend_or_prediction():
    report = evaluate_recommendation(
        confidence=0.6,
        evidence_ids=["e1", "e2"],
        trend_ids=[],
        prediction_id=None,
        text="Build capability in agile delivery over the next quarter.",
    )
    assert not report.is_valid
    assert any("TRACEABILITY" in m for m in report.messages)


def test_confidence_outside_range_is_a_hard_failure():
    report = evaluate_recommendation(
        confidence=1.4,
        evidence_ids=["e1", "e2"],
        trend_ids=["t1"],
        prediction_id="p1",
        text="Build capability in agile delivery over the next quarter.",
    )
    assert not report.is_valid
    assert any("CONFIDENCE_RANGE" in m for m in report.messages)


def test_prediction_review_window_capped_at_ninety_days():
    report = evaluate_prediction(
        confidence=0.5,
        supporting_evidence_ids=["e1"],
        trend_ids=["t1"],
        review_date=TODAY + timedelta(days=120),
        expiration_date=TODAY + timedelta(days=127),
        created_on=TODAY,
        periods_observed=6,
    )
    assert not report.is_valid
    assert any("REVIEW_WINDOW" in m for m in report.messages)


def test_prediction_requires_expiration_after_review():
    report = evaluate_prediction(
        confidence=0.5,
        supporting_evidence_ids=["e1"],
        trend_ids=["t1"],
        review_date=TODAY + timedelta(days=28),
        expiration_date=TODAY + timedelta(days=14),
        created_on=TODAY,
        periods_observed=6,
    )
    assert not report.is_valid
    assert any("EXPIRATION_ORDER" in m for m in report.messages)


def test_small_sample_is_soft_not_hard():
    report = evaluate_prediction(
        confidence=0.5,
        supporting_evidence_ids=["e1"],
        trend_ids=["t1"],
        review_date=TODAY + timedelta(days=28),
        expiration_date=TODAY + timedelta(days=35),
        created_on=TODAY,
        periods_observed=1,
    )
    assert report.is_valid
    assert any("SAMPLE_SIZE" in m and m.startswith("[soft]") for m in report.messages)


def test_enforce_raises_on_hard_failure():
    report = evaluate_recommendation(
        confidence=0.6, evidence_ids=[], trend_ids=[], prediction_id=None, text="too short"
    )
    with pytest.raises(GovernanceError):
        enforce(report, "unit test")


def test_default_review_dates_are_clamped():
    review, expiration = default_review_dates(TODAY, 400)
    assert (review - TODAY).days == 90
    assert expiration > review
