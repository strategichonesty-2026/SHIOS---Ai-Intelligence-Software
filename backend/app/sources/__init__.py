from __future__ import annotations

from app.config import settings
from app.sources.base import (
    CollectedItem,
    ParseError,
    RateLimitExceeded,
    Source,
    SourceError,
    SourceUnavailable,
)
from app.sources.external import GitHubSource, GmailSource, RSSSource
from app.sources.remoteok import RemoteOKSource
from app.sources.sample_jobs import SampleJobsSource

_FACTORIES = {
    SampleJobsSource.source_id: SampleJobsSource,
    RemoteOKSource.source_id: RemoteOKSource,
    RSSSource.source_id: RSSSource,
    GitHubSource.source_id: GitHubSource,
    GmailSource.source_id: GmailSource,
}


def build_sources(source_ids: list[str] | None = None) -> list[Source]:
    ids = source_ids if source_ids is not None else settings.source_list
    return [_FACTORIES[i]() for i in ids if i in _FACTORIES]


def available_source_ids() -> list[str]:
    return sorted(_FACTORIES)


__all__ = [
    "CollectedItem",
    "RemoteOKSource",
    "GitHubSource",
    "GmailSource",
    "ParseError",
    "RSSSource",
    "RateLimitExceeded",
    "SampleJobsSource",
    "Source",
    "SourceError",
    "SourceUnavailable",
    "available_source_ids",
    "build_sources",
]
