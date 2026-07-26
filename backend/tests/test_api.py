"""API contract tests."""

from __future__ import annotations

import pytest

from app.orchestrator.orchestrator import run_full_loop


@pytest.fixture
def seeded(db, client):
    run_full_loop(db, source_ids=["sample_jobs"], limit=1000)
    db.commit()
    return client


@pytest.mark.slow
def test_health_and_root(client):
    assert client.get("/").json()["name"] == "SHIOS"

    health = client.get("/api/v1/health").json()
    assert health["status"] == "ok"
    assert health["database"] == "up"


@pytest.mark.slow
def test_agent_catalog_is_exposed(client):
    payload = client.get("/api/v1/agents").json()
    names = {a["agent"] for a in payload["agents"]}
    assert {"collector", "trend", "prediction", "strategic_honesty_validator", "learning"} <= names
    assert "sample_jobs" in payload["sources_available"]


@pytest.mark.slow
def test_dashboard_overview(seeded):
    payload = seeded.get("/api/v1/dashboard/overview").json()
    assert payload["counts"]["documents"] > 0
    assert payload["window"]["latest_period"]
    assert payload["accuracy"]["scored"] > 0
    assert payload["risers"] or payload["fallers"]


@pytest.mark.slow
def test_trend_endpoints(seeded):
    latest = seeded.get("/api/v1/trends/latest?entity_type=skill").json()
    assert latest["items"], "no latest trends returned"
    first = latest["items"][0]

    series = seeded.get(f"/api/v1/trends/series/skill/{first['entity_name']}").json()
    assert len(series["points"]) > 1

    evidence = seeded.get(f"/api/v1/trends/{first['id']}/evidence").json()
    assert evidence["evidence"], "trend has no retrievable evidence"
    assert evidence["evidence"][0]["snippet"]


@pytest.mark.slow
def test_prediction_detail_exposes_its_own_uncertainty(seeded):
    listing = seeded.get("/api/v1/predictions?limit=5").json()
    assert listing["items"]

    detail = seeded.get(f"/api/v1/predictions/{listing['items'][0]['id']}").json()
    assert detail["assumptions"] and detail["risks"]
    assert detail["series"]
    assert 0.0 <= detail["confidence"] <= 1.0


@pytest.mark.slow
def test_accuracy_endpoint_reports_calibration(seeded):
    payload = seeded.get("/api/v1/predictions/accuracy").json()
    assert payload["scored"] > 0
    assert 0.0 <= payload["mean_accuracy"] <= 1.0
    assert payload["calibration"]


@pytest.mark.slow
def test_recommendation_detail_and_human_decision(seeded):
    listing = seeded.get("/api/v1/recommendations?limit=5").json()
    assert listing["items"]
    recommendation_id = listing["items"][0]["id"]

    detail = seeded.get(f"/api/v1/recommendations/{recommendation_id}").json()
    assert detail["evidence_count"] >= 2
    assert detail["evidence"]
    assert detail["risks"]

    response = seeded.post(
        f"/api/v1/recommendations/{recommendation_id}/decision",
        json={"status": "approved", "note": "reviewed in weekly"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"

    rejected = seeded.post(
        f"/api/v1/recommendations/{recommendation_id}/decision", json={"status": "nonsense"}
    )
    assert rejected.status_code == 422


@pytest.mark.slow
def test_reports_list_and_markdown_export(seeded):
    listing = seeded.get("/api/v1/reports").json()
    assert listing["items"]
    report_id = listing["items"][0]["id"]

    detail = seeded.get(f"/api/v1/reports/{report_id}").json()
    assert detail["body_markdown"].strip()

    export = seeded.get(f"/api/v1/reports/{report_id}/export.md")
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/markdown")


@pytest.mark.slow
def test_documents_and_evidence_are_traceable(seeded):
    listing = seeded.get("/api/v1/documents?doc_type=job&limit=3").json()
    assert listing["items"]

    detail = seeded.get(f"/api/v1/documents/{listing['items'][0]['id']}").json()
    assert detail["job"] is not None
    assert detail["evidence"]

    evidence = seeded.get(f"/api/v1/documents/evidence/{detail['evidence'][0]['id']}").json()
    assert evidence["document"]["id"] == detail["id"]


@pytest.mark.slow
def test_explorer_returns_aligned_series(seeded):
    payload = seeded.get("/api/v1/dashboard/explorer?entity_type=skill&top=4").json()
    assert payload["periods"]
    assert payload["series"]
    for series in payload["series"]:
        assert len(series["values"]) == len(payload["periods"])


@pytest.mark.slow
def test_runs_and_events_are_queryable(seeded):
    runs = seeded.get("/api/v1/runs?limit=10").json()
    assert runs["items"]
    assert all("agent" in r for r in runs["items"])

    events = seeded.get("/api/v1/runs/events?limit=10").json()
    assert events["items"]


@pytest.mark.slow
def test_unknown_agent_returns_404(client):
    assert client.post("/api/v1/runs/agents/not-an-agent", json={}).status_code == 404


@pytest.mark.slow
def test_missing_resources_return_404(client):
    assert client.get("/api/v1/predictions/missing").status_code == 404
    assert client.get("/api/v1/reports/missing").status_code == 404
    assert client.get("/api/v1/recommendations/missing").status_code == 404


@pytest.mark.slow
def test_api_key_is_enforced_when_configured(client, monkeypatch):
    from app.api import deps

    monkeypatch.setattr(deps.settings, "api_key", "secret-key")

    assert client.get("/api/v1/health").status_code == 200, "health must stay open for probes"
    assert client.get("/api/v1/trends/latest").status_code == 401
    assert client.get("/api/v1/trends/latest", headers={"x-api-key": "wrong"}).status_code == 401
    assert client.get("/api/v1/trends/latest", headers={"x-api-key": "secret-key"}).status_code == 200
