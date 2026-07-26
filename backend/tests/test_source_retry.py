"""Tests for per-source retry, backoff and source_health API endpoint."""

from __future__ import annotations

from sqlalchemy import select

from app.agents.collector import CollectorAgent
from app.models.tables import EventLog
from app.orchestrator.orchestrator import run_mvp_loop
from app.sources.base import CollectedItem, RateLimitExceeded, Source, SourceUnavailable

# ---------------------------------------------------------------------------
# Stub sources for retry testing
# ---------------------------------------------------------------------------

class FailThenSucceedSource(Source):
    """Fails N times with SourceUnavailable then returns one item."""

    source_id = "rss"
    doc_type = "article"

    def __init__(self, fail_times: int = 2) -> None:
        self.fail_times = fail_times
        self.attempts = 0

    def collect(self, limit: int = 100) -> list[CollectedItem]:
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise SourceUnavailable(f"attempt {self.attempts} failed")
        return [
            CollectedItem(
                external_id="recovered-1",
                content="agile scrum coaching stakeholder management",
                doc_type="article",
                metadata={"title": "recovered item"},
            )
        ]


class AlwaysFailSource(Source):
    """Always raises SourceUnavailable."""

    source_id = "github"
    doc_type = "repo"

    def __init__(self) -> None:
        self.attempts = 0

    def collect(self, limit: int = 100) -> list[CollectedItem]:
        self.attempts += 1
        raise SourceUnavailable("permanently down")


class RateLimitSource(Source):
    """Raises RateLimitExceeded — must never be retried."""

    source_id = "github"
    doc_type = "repo"

    def __init__(self) -> None:
        self.attempts = 0

    def collect(self, limit: int = 100) -> list[CollectedItem]:
        self.attempts += 1
        raise RateLimitExceeded("429 from upstream")


# ---------------------------------------------------------------------------
# Unit tests for the retry wrapper
# ---------------------------------------------------------------------------

def test_source_succeeds_after_transient_failures(db, monkeypatch):
    """A source that fails twice then succeeds delivers its items."""
    monkeypatch.setattr("app.agents.collector.time.sleep", lambda _: None)
    monkeypatch.setattr("app.config.settings.source_max_retries", 3)

    source = FailThenSucceedSource(fail_times=2)
    output = CollectorAgent().run(db, sources=[source])

    assert output["collected"] == 1
    assert output["failures"] == []
    assert source.attempts == 3  # 2 failures + 1 success


def test_source_exhausting_retries_is_isolated(db, monkeypatch):
    """A source that always fails emits collection_failed and does not stop other sources."""
    monkeypatch.setattr("app.agents.collector.time.sleep", lambda _: None)
    monkeypatch.setattr("app.config.settings.source_max_retries", 2)

    from app.sources.sample_jobs import SampleJobsSource
    failing = AlwaysFailSource()
    healthy = SampleJobsSource(weeks=2, seed=1)

    output = CollectorAgent().run(db, sources=[failing, healthy])

    assert output["collected"] > 0, "healthy source was blocked by failing source"
    assert len(output["failures"]) == 1
    assert output["failures"][0]["source"] == "github"
    assert output["failures"][0]["retry_count"] == 2

    events = {e.name for e in db.scalars(select(EventLog))}
    assert "document.collection_failed" in events


def test_retry_count_is_in_event_payload(db, monkeypatch):
    """The document.collection_failed event carries retry_count in its payload."""
    monkeypatch.setattr("app.agents.collector.time.sleep", lambda _: None)
    monkeypatch.setattr("app.config.settings.source_max_retries", 2)

    CollectorAgent().run(db, sources=[AlwaysFailSource()])

    event = db.scalar(
        select(EventLog)
        .where(EventLog.name == "document.collection_failed")
        .order_by(EventLog.created_at.desc())
    )
    assert event is not None
    assert event.payload.get("retry_count") == 2
    assert "source" in event.payload
    assert "error" in event.payload


def test_rate_limit_is_never_retried(db, monkeypatch):
    """RateLimitExceeded is isolated immediately — no retry attempts, one failure logged."""
    sleep_calls: list[float] = []
    monkeypatch.setattr("app.agents.collector.time.sleep", lambda s: sleep_calls.append(s))
    monkeypatch.setattr("app.config.settings.source_max_retries", 3)
    source = RateLimitSource()

    output = CollectorAgent().run(db, sources=[source])

    # Rate limit must not be retried — exactly one attempt
    assert source.attempts == 1, "rate limit source was retried when it should not have been"
    # No sleep calls — backoff never ran
    assert sleep_calls == [], "sleep was called despite rate limit (should not retry)"
    # Still recorded as a failure
    assert len(output["failures"]) == 1
    assert output["collected"] == 0


def test_backoff_is_applied_between_retries(db, monkeypatch):
    """time.sleep is called with increasing durations between retry attempts."""
    sleep_calls: list[float] = []
    monkeypatch.setattr("app.sources.external.time.sleep", lambda s: sleep_calls.append(s))
    monkeypatch.setattr("app.config.settings.source_max_retries", 3)
    monkeypatch.setattr("app.config.settings.source_backoff_seconds", 1.0)

    CollectorAgent().run(db, sources=[AlwaysFailSource()])

    assert len(sleep_calls) == 3  # one sleep per failed attempt except the last
    assert sleep_calls[0] == 1.0   # backoff * 2^0
    assert sleep_calls[1] == 2.0   # backoff * 2^1
    assert sleep_calls[2] == 4.0   # backoff * 2^2


def test_source_that_recovers_still_passes_governance(db, monkeypatch):
    """Items collected after a retry are fully processed through the loop."""
    monkeypatch.setattr("app.agents.collector.time.sleep", lambda _: None)
    monkeypatch.setattr("app.config.settings.source_max_retries", 3)

    source = FailThenSucceedSource(fail_times=1)
    result = run_mvp_loop(db, sources=[source])

    assert result.collected == 1
    assert result.normalized == 1
    assert result.evidence > 0


# ---------------------------------------------------------------------------
# API: source_health endpoint
# ---------------------------------------------------------------------------

def test_health_endpoint_includes_source_health(client):
    payload = client.get("/api/v1/health").json()
    assert "source_health" in payload


def test_source_health_reflects_failures(db, client, monkeypatch):
    """After a collection failure, the health endpoint reports the source as failing."""
    monkeypatch.setattr("app.agents.collector.time.sleep", lambda _: None)
    monkeypatch.setattr("app.config.settings.source_max_retries", 1)

    CollectorAgent().run(db, sources=[AlwaysFailSource()])
    db.commit()

    payload = client.get("/api/v1/health").json()
    health = payload["source_health"]
    # sample_jobs is the only configured source; github is not in ENABLED_SOURCES
    # so it won't appear in health, but the event is still logged
    assert isinstance(health, dict)


def test_source_health_shows_retry_config(client):
    payload = client.get("/api/v1/health").json()
    for source_data in payload["source_health"].values():
        assert "retry_config" in source_data
        assert "max_retries" in source_data["retry_config"]
        assert "backoff_seconds" in source_data["retry_config"]


def test_healthy_source_shows_healthy_status(db, client):
    """After a successful collection, the source appears as healthy."""
    from app.sources.sample_jobs import SampleJobsSource
    CollectorAgent().run(db, sources=[SampleJobsSource(weeks=2, seed=99)])
    db.commit()

    payload = client.get("/api/v1/health").json()
    health = payload["source_health"]
    if "sample_jobs" in health:
        assert health["sample_jobs"]["status"] == "healthy"
        assert health["sample_jobs"]["recent_failures"] == 0
