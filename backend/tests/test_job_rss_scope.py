"""Tests that JobRSSSource actually applies US/English/tech-role scoping to what it
collects — using response shapes mirroring real Jobicy (RSS) and Arbeitnow (JSON) output."""

from __future__ import annotations

import json

import httpx

from app.models.tables import RawDocument
from app.sources.job_rss import JobRSSSource

_JOBICY_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:job_listing="urn:job_listing">
<channel>
<item>
  <title>Senior Python Engineer</title>
  <id>https://jobicy.com/jobs/1</id>
  <link>https://jobicy.com/jobs/1</link>
  <description><![CDATA[We are hiring a Senior Python Engineer with kubernetes experience.]]></description>
  <job_listing:location><![CDATA[USA]]></job_listing:location>
</item>
<item>
  <title>Senior Embedded Linux Software Engineer</title>
  <id>https://jobicy.com/jobs/2</id>
  <link>https://jobicy.com/jobs/2</link>
  <description><![CDATA[We are hiring a software engineer with python experience.]]></description>
  <job_listing:location><![CDATA[Munich]]></job_listing:location>
</item>
</channel>
</rss>
"""

_ARBEITNOW_JSON = json.dumps({
    "data": [
        {
            "slug": "us-python-role",
            "title": "Python Engineer",
            "company_name": "Acme",
            "description": "Python and kubernetes experience required.",
            "location": "Remote",
            "remote": True,
            "tags": ["python", "kubernetes"],
        },
        {
            "slug": "de-python-role",
            "title": "Python Engineer",
            "company_name": "Acme GmbH",
            "description": "Wir suchen einen Mitarbeiter mit Erfahrung in Python.",
            "location": "Berlin",
            "remote": False,
            "tags": ["python"],
        },
        {
            "slug": "us-nontech-role",
            "title": "Warehouse Associate",
            "company_name": "Acme Logistics",
            "description": "Loading and unloading trucks.",
            "location": "USA",
            "remote": False,
            "tags": [],
        },
    ]
})


def _fake_response(text: str, content_type: str) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": content_type}, text=text)


def test_jobicy_rss_drops_the_german_posting(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _fake_response(_JOBICY_RSS, "application/rss+xml"))

    source = JobRSSSource(feeds=["https://jobicy.com/?feed=job_feed"])
    items = source.collect(limit=10)

    locations = {i.metadata["location"] for i in items}
    assert locations == {"USA"}
    assert all("Munich" not in i.content for i in items)


def test_arbeitnow_json_drops_german_and_nontech_postings(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _fake_response(_ARBEITNOW_JSON, "application/json"))

    source = JobRSSSource(feeds=["https://arbeitnow.com/api/job-board-api"])
    items = source.collect(limit=10)

    assert len(items) == 1
    assert items[0].external_id == "us-python-role"
    assert items[0].metadata["location"] == "Remote"


def test_purge_off_scope_endpoint_only_removes_out_of_scope_job_rss_rows(db, client):
    us_doc = RawDocument(
        source="job_rss",
        external_id="us-1",
        content="Python Engineer\n\nLocation: USA\n\nPython and kubernetes experience.",
        content_hash="hash-us-1",
        doc_metadata={"title": "Python Engineer", "location": "USA"},
    )
    de_doc = RawDocument(
        source="job_rss",
        external_id="de-1",
        content="Python Engineer\n\nLocation: Munich\n\nPython experience required.",
        content_hash="hash-de-1",
        doc_metadata={"title": "Python Engineer", "location": "Munich"},
    )
    other_source_doc = RawDocument(
        source="github",
        external_id="repo-1",
        content="some repo",
        content_hash="hash-repo-1",
        doc_metadata={},
    )
    db.add_all([us_doc, de_doc, other_source_doc])
    db.commit()

    response = client.delete("/api/v1/runs/source/job_rss/off-scope")
    assert response.status_code == 200
    payload = response.json()
    assert payload["checked"] == 2
    assert payload["deleted_raw_documents"] == 1

    remaining = {row.external_id for row in db.query(RawDocument).all()}
    assert remaining == {"us-1", "repo-1"}
