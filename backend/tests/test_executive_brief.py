"""Tests for the executive_brief report type (spec sections 5 and 7).

The test DB fixture runs with ENABLED_SOURCES=sample_jobs only, so no article documents
exist from run_full_loop.  We insert RawDocument → NormalizedDocument → Evidence rows
directly, mirroring what ExtractionAgent._write_evidence would produce.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.agents.reporting import ReportingAgent
from app.models.tables import Evidence, NormalizedDocument, RawDocument, Report
from app.orchestrator.orchestrator import run_full_loop  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_article(db, *, idx: int = 0, body: str | None = None, source: str = "rss") -> tuple:
    """Insert a minimal RawDocument + NormalizedDocument of doc_type='article'.
    Returns (raw, normalized).
    """
    if body is None:
        body = (
            "Machine learning engineers are in high demand. "
            "Python skills continue to rise across the industry. "
            "Data science roles have seen steady growth this quarter. " * 30
        )
    raw = RawDocument(
        source=source,
        external_id=f"article-{idx}",
        content=body,
        content_hash=f"hash-article-{idx}",
        doc_metadata={"link": f"https://example.com/article-{idx}"},
    )
    db.add(raw)
    db.flush()

    observed_at = datetime(2026, 1, 20 + idx, 12, 0, 0, tzinfo=UTC)
    normalized = NormalizedDocument(
        raw_document_id=raw.id,
        doc_type="article",
        title=f"Article Title {idx}",
        body_text=body,
        entities={"skills": ["python"], "technologies": ["machine learning"], "roles": ["data scientist"]},
        source=source,
        observed_at=observed_at,
    )
    db.add(normalized)
    db.flush()
    return raw, normalized


def _add_evidence(db, normalized: NormalizedDocument, entity_pairs: list[tuple[str, str]]) -> list[Evidence]:
    evs = []
    for entity_type, entity_name in entity_pairs:
        ev = Evidence(
            normalized_document_id=normalized.id,
            entity_type=entity_type,
            entity_name=entity_name,
            period="2026-W03",
            snippet=f"...{entity_name}...",
            source=normalized.source,
        )
        db.add(ev)
        evs.append(ev)
    db.flush()
    return evs


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def seeded_with_articles(db):
    """Seed the DB with job trend data (via run_full_loop) and two article documents."""
    run_full_loop(db, source_ids=["sample_jobs"], limit=1000)
    db.commit()

    raw1, norm1 = _make_article(db, idx=0)
    _add_evidence(db, norm1, [("skill", "python"), ("technology", "machine learning")])

    raw2, norm2 = _make_article(db, idx=1, body=(
        "Agile project management and cloud computing are reshaping modern software teams. "
        "DevOps adoption is accelerating. " * 25
    ))
    _add_evidence(db, norm2, [("skill", "agile"), ("technology", "cloud computing")])

    db.commit()
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_executive_brief_generates_and_has_required_fields(seeded_with_articles):
    db = seeded_with_articles
    result = ReportingAgent().run(db, report_types=["executive_brief"])

    assert result["reports"] == 1
    report_id = result["report_ids"][0]
    report = db.get(Report, report_id)

    assert report is not None
    assert report.report_type == "executive_brief"
    assert "stories" in report.payload

    stories = report.payload["stories"]
    assert len(stories) >= 1

    required_fields = {
        "document_id", "title", "source", "published_at", "original_url",
        "reading_time_minutes", "related_entities", "related_trends",
        "executive_summary", "why_it_matters", "business_impact",
        "technology_impact", "strategic_recommendation",
    }
    for story in stories:
        missing = required_fields - set(story.keys())
        assert not missing, f"Story missing fields: {missing}"


@pytest.mark.slow
def test_reading_time_matches_formula(seeded_with_articles):
    db = seeded_with_articles
    result = ReportingAgent().run(db, report_types=["executive_brief"])
    report = db.get(Report, result["report_ids"][0])

    for story in report.payload["stories"]:
        doc_id = story["document_id"]
        nd = db.get(NormalizedDocument, doc_id)
        expected = math.ceil(len(nd.body_text.split()) / 220) or 1
        assert story["reading_time_minutes"] == expected, (
            f"reading_time_minutes mismatch for {doc_id}: got {story['reading_time_minutes']}, expected {expected}"
        )


@pytest.mark.slow
def test_evidence_summary_reconciles(seeded_with_articles):
    db = seeded_with_articles
    result = ReportingAgent().run(db, report_types=["executive_brief"])
    report = db.get(Report, result["report_ids"][0])

    evidence_summary = report.payload["evidence_summary"]
    report_evidence_ids = set(report.evidence_ids)

    # Fetch the actual evidence rows for this report.
    actual_ev = list(
        db.scalars(select(Evidence).where(Evidence.id.in_(report_evidence_ids)))
    )
    actual_nd_ids = [ev.normalized_document_id for ev in actual_ev]
    actual_nds = list(db.scalars(select(NormalizedDocument).where(NormalizedDocument.id.in_(actual_nd_ids))))
    nd_by_id = {nd.id: nd for nd in actual_nds}

    expected_news_articles = sum(
        1 for ev in actual_ev if nd_by_id.get(ev.normalized_document_id, None) and
        nd_by_id[ev.normalized_document_id].doc_type == "article"
    )
    # Note: evidence_summary counts are per Evidence row, same as the implementation.
    assert evidence_summary["news_articles"] == expected_news_articles


@pytest.mark.slow
def test_research_papers_none_in_payload_and_not_collected_in_markdown(seeded_with_articles):
    db = seeded_with_articles
    result = ReportingAgent().run(db, report_types=["executive_brief"])
    report = db.get(Report, result["report_ids"][0])

    # research_papers must be None in payload, not 0.
    assert report.payload["evidence_summary"]["research_papers"] is None

    # The string "not collected" (not "0") must appear in body_markdown.
    assert "not collected" in report.body_markdown
    # Make sure "0" is not used where "not collected" is required.
    lines = report.body_markdown.splitlines()
    for line in lines:
        if "Research papers" in line or "research papers" in line:
            assert "not collected" in line, f"Expected 'not collected' in line: {line!r}"


@pytest.mark.slow
def test_related_entities_resolve_to_real_evidence_rows(seeded_with_articles):
    db = seeded_with_articles
    result = ReportingAgent().run(db, report_types=["executive_brief"])
    report = db.get(Report, result["report_ids"][0])

    for story in report.payload["stories"]:
        doc_id = story["document_id"]
        actual_evidence = list(
            db.scalars(select(Evidence).where(Evidence.normalized_document_id == doc_id))
        )
        actual_pairs = {(ev.entity_type, ev.entity_name) for ev in actual_evidence}
        for entity in story["related_entities"]:
            pair = (entity["entity_type"], entity["entity_name"])
            assert pair in actual_pairs, (
                f"Story entity {pair} not found in Evidence rows for document {doc_id}"
            )


@pytest.mark.slow
def test_rule_provider_produces_deterministic_output(seeded_with_articles):
    """With LLM_PROVIDER=rule, two runs against the same data must produce byte-identical body_markdown."""
    db = seeded_with_articles

    result1 = ReportingAgent().run(db, report_types=["executive_brief"])
    result2 = ReportingAgent().run(db, report_types=["executive_brief"])

    report1 = db.get(Report, result1["report_ids"][0])
    report2 = db.get(Report, result2["report_ids"][0])

    assert report1.body_markdown == report2.body_markdown


@pytest.mark.slow
def test_no_articles_produces_no_report(db):
    """Calling with zero article documents returns {reports: 0} and creates no Report row."""
    run_full_loop(db, source_ids=["sample_jobs"], limit=1000)
    db.commit()

    # Confirm there are no article documents.
    article_count = db.scalar(
        select(NormalizedDocument).where(NormalizedDocument.doc_type == "article").limit(1)
    )
    assert article_count is None, "Expected no article documents in this fixture"

    result = ReportingAgent().run(db, report_types=["executive_brief"])
    assert result["reports"] == 0

    existing = list(db.scalars(select(Report).where(Report.report_type == "executive_brief")))
    assert len(existing) == 0


@pytest.mark.slow
def test_blog_and_linkedin_carry_evidence_summary(db):
    """blog_draft and linkedin_article_draft must include an Evidence Summary section."""
    run_full_loop(db, source_ids=["sample_jobs"], limit=1000)
    db.commit()

    result = ReportingAgent().run(db, report_types=["blog_draft", "linkedin_article_draft"])
    assert result["reports"] == 2

    for report_id in result["report_ids"]:
        report = db.get(Report, report_id)
        assert "## Evidence Summary" in report.body_markdown, (
            f"{report.report_type} is missing '## Evidence Summary' section"
        )
        assert "evidence_summary" in report.payload, (
            f"{report.report_type} payload is missing 'evidence_summary'"
        )
        # research_papers must say "not collected" in the markdown.
        assert "not collected" in report.body_markdown


@pytest.mark.slow
def test_original_url_populated_from_raw_metadata(seeded_with_articles):
    """original_url should come from raw.doc_metadata['link']."""
    db = seeded_with_articles
    result = ReportingAgent().run(db, report_types=["executive_brief"])
    report = db.get(Report, result["report_ids"][0])

    for story in report.payload["stories"]:
        assert story["original_url"] is not None
        assert story["original_url"].startswith("https://")


@pytest.mark.slow
def test_executive_brief_not_in_default_report_types(db):
    """executive_brief must not appear unless explicitly requested."""
    run_full_loop(db, source_ids=["sample_jobs"], limit=1000)
    db.commit()

    result = ReportingAgent().run(db)
    brief_reports = list(db.scalars(select(Report).where(Report.report_type == "executive_brief")))
    assert len(brief_reports) == 0, "executive_brief was created without being explicitly requested"
