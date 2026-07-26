"""Tests for the median_salary metric added in Task 3."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.agents.trend import TrendAgent
from app.models.tables import Job, NormalizedDocument, RawDocument, Trend
from app.orchestrator.orchestrator import run_mvp_loop

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job(db, entity_name: str, period: str, salary_min: float, salary_max: float):
    """Insert a minimal job row with salary data tied to a normalized document."""
    from app.services.periods import period_start_date

    posted_at = period_start_date(period).replace(month=period_start_date(period).month)
    import datetime as dt
    posted_dt = dt.datetime.combine(posted_at, dt.time(9, 0), tzinfo=dt.UTC)

    raw = RawDocument(
        source="sample_jobs",
        external_id=f"salary-test-{entity_name}-{period}-{salary_min}",
        content=f"{entity_name} role with salary",
        content_hash=f"hash-{entity_name}-{period}-{salary_min}",
        doc_metadata={"doc_type": "job", "observed_at": posted_dt.isoformat()},
    )
    db.add(raw)
    db.flush()

    norm = NormalizedDocument(
        raw_document_id=raw.id,
        doc_type="job",
        title=f"{entity_name} engineer",
        body_text=f"agile scrum {entity_name} coaching",
        entities={"skills": [entity_name], "technologies": [], "roles": [],
                  "seniority": "senior", "remote_type": "hybrid"},
        source="sample_jobs",
        observed_at=posted_dt,
    )
    db.add(norm)
    db.flush()

    job = Job(
        normalized_document_id=norm.id,
        title=f"{entity_name} engineer",
        normalized_role="other",
        seniority="senior",
        location="Remote",
        remote_type="hybrid",
        posted_at=posted_dt,
        skills=[entity_name],
        technologies=[],
        salary_min=salary_min,
        salary_max=salary_max,
    )
    db.add(job)
    db.flush()
    return norm.id


# ---------------------------------------------------------------------------
# Unit tests — median_salary metric
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_median_salary_appears_after_full_loop(db):
    """After a bootstrap loop, median_salary trends exist alongside job_postings_count."""
    run_mvp_loop(db, source_ids=["sample_jobs"], limit=1000)

    salary_trends = list(db.scalars(select(Trend).where(Trend.metric == "median_salary")))
    count_trends = list(db.scalars(select(Trend).where(Trend.metric == "job_postings_count")))

    assert count_trends, "job_postings_count trends must exist"
    assert salary_trends, "median_salary trends must exist (sample source includes salary data)"


@pytest.mark.slow
def test_salary_trends_only_where_data_exists(db):
    """median_salary rows must never be written for (entity, period) with no salary data."""
    run_mvp_loop(db, source_ids=["sample_jobs"], limit=1000)

    salary_trends = list(db.scalars(select(Trend).where(Trend.metric == "median_salary")))
    count_trends = list(db.scalars(select(Trend).where(Trend.metric == "job_postings_count")))

    # Salary rows must be a subset of count rows — never more
    salary_keys = {(t.entity_type, t.entity_name, t.period) for t in salary_trends}
    count_keys = {(t.entity_type, t.entity_name, t.period) for t in count_trends}
    assert salary_keys.issubset(count_keys), (
        "salary trend exists for a (entity, period) with no posting count row"
    )


def test_median_salary_computed_correctly(db):
    """Median is (salary_min + salary_max) / 2 per posting, then median across postings."""
    period = "2026-W20"
    _make_job(db, "agile delivery", period, 120_000, 160_000)  # midpoint 140k
    _make_job(db, "agile delivery", period, 130_000, 170_000)  # midpoint 150k
    _make_job(db, "agile delivery", period, 110_000, 150_000)  # midpoint 130k
    # median of [140k, 150k, 130k] = 140k

    # Also add evidence so the entity passes min_total check
    from app.models.tables import Evidence
    norm_ids = [r.id for r in db.scalars(select(NormalizedDocument))]
    for norm_id in norm_ids:
        db.add(Evidence(
            normalized_document_id=norm_id,
            entity_type="skill",
            entity_name="agile delivery",
            period=period,
            snippet="agile delivery",
            source="sample_jobs",
        ))
    db.flush()

    TrendAgent().run(db, min_total_evidence=1)

    salary_trend = db.scalar(
        select(Trend)
        .where(Trend.metric == "median_salary")
        .where(Trend.entity_name == "agile delivery")
        .where(Trend.period == period)
    )
    assert salary_trend is not None, "salary trend not written"
    assert salary_trend.value == 140_000.0
    assert salary_trend.sample_size == 3


def test_no_salary_row_when_no_salary_data(db):
    """An entity with evidence but no salary data produces no median_salary row."""
    period = "2026-W21"
    from app.models.tables import Evidence

    raw = RawDocument(
        source="sample_jobs",
        external_id="no-salary-doc",
        content="agile coaching and scrum",
        content_hash="no-salary-hash",
        doc_metadata={"doc_type": "article", "observed_at": "2026-05-18T09:00:00+00:00"},
    )
    db.add(raw)
    db.flush()
    norm = NormalizedDocument(
        raw_document_id=raw.id,
        doc_type="article",
        title="no salary article",
        body_text="agile coaching and scrum",
        entities={},
        source="sample_jobs",
        observed_at=raw.collected_at,
    )
    db.add(norm)
    db.flush()
    for _ in range(5):
        db.add(Evidence(
            normalized_document_id=norm.id,
            entity_type="skill",
            entity_name="coaching",
            period=period,
            snippet="coaching",
            source="sample_jobs",
        ))
    db.flush()

    TrendAgent().run(db, min_total_evidence=1)

    salary_trend = db.scalar(
        select(Trend)
        .where(Trend.metric == "median_salary")
        .where(Trend.entity_name == "coaching")
        .where(Trend.period == period)
    )
    assert salary_trend is None, "salary row written despite no salary data — dishonest"


def test_salary_trend_is_idempotent(db):
    """Running TrendAgent twice produces identical median_salary values."""
    period = "2026-W22"
    norm_id1 = _make_job(db, "agile delivery", period, 120_000, 160_000)
    norm_id2 = _make_job(db, "agile delivery", period, 130_000, 170_000)

    from app.models.tables import Evidence
    for norm_id in [norm_id1, norm_id2]:
        db.add(Evidence(
            normalized_document_id=norm_id,
            entity_type="skill",
            entity_name="agile delivery",
            period=period,
            snippet="agile",
            source="sample_jobs",
        ))
    db.flush()

    TrendAgent().run(db, min_total_evidence=1)
    first = db.scalar(
        select(Trend)
        .where(Trend.metric == "median_salary")
        .where(Trend.entity_name == "agile delivery")
    )
    first_value = first.value if first else None

    TrendAgent().run(db, min_total_evidence=1)
    second = db.scalar(
        select(Trend)
        .where(Trend.metric == "median_salary")
        .where(Trend.entity_name == "agile delivery")
    )
    assert second is not None
    assert second.value == first_value, "recomputation changed the salary value — not idempotent"
    assert db.query(Trend).filter_by(metric="median_salary", entity_name="agile delivery").count() == 1


@pytest.mark.slow
def test_career_dashboard_includes_salary_trends(client, db):
    """GET /api/v1/dashboard/career returns salary_trends in its payload."""
    run_mvp_loop(db, source_ids=["sample_jobs"], limit=1000)
    db.commit()

    response = client.get("/api/v1/dashboard/career")
    assert response.status_code == 200
    payload = response.json()
    assert "salary_trends" in payload, "salary_trends key missing from career dashboard"


@pytest.mark.slow
def test_technology_dashboard_includes_salary_trends(client, db):
    """GET /api/v1/dashboard/technology returns salary_trends in its payload."""
    run_mvp_loop(db, source_ids=["sample_jobs"], limit=1000)
    db.commit()

    response = client.get("/api/v1/dashboard/technology")
    assert response.status_code == 200
    payload = response.json()
    assert "salary_trends" in payload, "salary_trends key missing from technology dashboard"


@pytest.mark.slow
def test_salary_trends_have_required_fields(client, db):
    """Each salary_trend item has entity_name, median_salary, sample_size and note."""
    run_mvp_loop(db, source_ids=["sample_jobs"], limit=1000)
    db.commit()

    response = client.get("/api/v1/dashboard/career")
    salary_trends = response.json().get("salary_trends", [])
    if not salary_trends:
        pytest.skip("no salary data in sample source for this run")
    for item in salary_trends:
        assert "entity_name" in item
        assert "median_salary" in item
        assert "sample_size" in item
        assert "note" in item
        assert item["median_salary"] > 0
        assert item["sample_size"] > 0
