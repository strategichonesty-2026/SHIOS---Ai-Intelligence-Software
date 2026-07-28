"""Tests for the Executive Intelligence endpoints (evidence breakdown, jobs, trust panel)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.tables import Prediction, Recommendation, Trend
from app.orchestrator.orchestrator import run_full_loop


@pytest.fixture
def seeded(db, client):
    run_full_loop(db, source_ids=["sample_jobs"], limit=1000)
    db.commit()
    return client


@pytest.mark.slow
def test_evidence_breakdown_reports_real_categories(seeded):
    payload = seeded.get("/api/v1/evidence/breakdown").json()

    assert payload["total_evidence"] > 0
    assert payload["categories"], "no categories derived from collected documents"
    assert any(c["category"] == "Job Postings" for c in payload["categories"])

    # Every category total must reconcile against the evidence base.
    assert sum(c["evidence_count"] for c in payload["categories"]) == payload["total_evidence"]


@pytest.mark.slow
def test_breakdown_flags_synthetic_sources_honestly(seeded):
    payload = seeded.get("/api/v1/evidence/breakdown").json()
    sample = next(s for s in payload["sources"] if s["source"] == "sample_jobs")

    assert sample["synthetic"] is True
    assert sample["reliability"] == "reference-only"
    assert sample["reliability_basis"], "a rating without a stated basis is not honest"


@pytest.mark.slow
def test_breakdown_names_uncollected_sources_instead_of_hiding_them(seeded):
    payload = seeded.get("/api/v1/evidence/breakdown").json()
    missing = {item["category"] for item in payload["not_collected"]}

    # The spec asked for these; the system does not read them, and says so.
    assert {"Research Papers", "SEC Filings", "Government Data"} <= missing
    for item in payload["not_collected"]:
        assert item["note"], "a gap must explain itself"


@pytest.mark.slow
def test_evidence_drilldown_by_source(seeded):
    payload = seeded.get("/api/v1/evidence/by-source/sample_jobs?limit=5").json()
    assert payload["items"]
    for item in payload["items"]:
        assert item["document_id"]
        assert item["snippet"]


@pytest.mark.slow
def test_jobs_endpoint_returns_corpus(seeded):
    payload = seeded.get("/api/v1/jobs?limit=10").json()

    assert payload["total"] > 0
    assert payload["items"]
    first = payload["items"][0]
    for field in ("position", "location", "remote_type", "posted_at", "source", "skills"):
        assert field in first
    assert first["synthetic"] is True, "sample_jobs rows must be flagged synthetic"


@pytest.mark.slow
def test_jobs_filtering_narrows_results(seeded):
    unfiltered = seeded.get("/api/v1/jobs?limit=200").json()
    remote = seeded.get("/api/v1/jobs?remote_type=remote&limit=200").json()

    assert remote["total"] <= unfiltered["total"]
    assert all(j["remote_type"] == "remote" for j in remote["items"])


@pytest.mark.slow
def test_jobs_salary_filter_only_returns_known_salaries(seeded):
    payload = seeded.get("/api/v1/jobs?has_salary=true&limit=50").json()
    assert all(j["salary_known"] and j["salary_min"] is not None for j in payload["items"])


@pytest.mark.slow
def test_job_facets_are_derived_from_data(seeded):
    payload = seeded.get("/api/v1/jobs/facets").json()

    assert payload["total_jobs"] > 0
    assert payload["roles"] and payload["skills"]
    assert 0.0 <= payload["salary_coverage"] <= 1.0


@pytest.mark.slow
def test_trust_panel_for_prediction_is_complete(db, seeded):
    prediction = db.scalar(select(Prediction).where(Prediction.status == "published"))
    payload = seeded.get(f"/api/v1/trust/prediction/{prediction.id}").json()

    assert payload["evidence_count"] > 0
    assert 0.0 <= payload["confidence"] <= 1.0
    assert payload["source_diversity"]["distinct_sources"] >= 1
    assert payload["explainability"]["method"]
    assert payload["explainability"]["immutable"] is True
    assert payload["reality_validation"] is not None
    assert payload["prediction_history"]["forecasts_published"] >= 1
    assert payload["related_sources"], "trust panel must be able to name its documents"


@pytest.mark.slow
def test_trust_panel_for_recommendation_exposes_unknowns(db, seeded):
    recommendation = db.scalar(select(Recommendation))
    payload = seeded.get(f"/api/v1/trust/recommendation/{recommendation.id}").json()

    assert payload["evidence_count"] >= 2, "governance requires two evidence ids"
    assert payload["explainability"]["rationale"]
    assert "unknowns_noted" in payload["reality_validation"]


@pytest.mark.slow
def test_trust_panel_for_trend_does_not_fake_a_score(db, seeded):
    trend = db.scalar(select(Trend))
    payload = seeded.get(f"/api/v1/trust/trend/{trend.id}").json()

    assert payload["confidence"] is None, "trends are counts; they must not claim confidence"
    assert payload["reality_validation"]["scored"] is False


def test_trust_panel_rejects_unknown_target_type(client):
    assert client.get("/api/v1/trust/nonsense/abc").status_code == 422


def test_trust_panel_missing_artefact_returns_404(client):
    assert client.get("/api/v1/trust/prediction/does-not-exist").status_code == 404
