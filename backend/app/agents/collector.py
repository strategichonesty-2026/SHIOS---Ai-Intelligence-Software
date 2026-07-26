"""5.1 Collector Agent — pull raw information from configured sources."""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import Agent
from app.config import settings
from app.events.bus import bus
from app.events.types import EventName
from app.models.tables import RawDocument
from app.sources import Source, SourceError, build_sources
from app.sources.base import RateLimitExceeded

log = logging.getLogger("shios.agents.collector")


class CollectorAgent(Agent):
    name = "collector"
    supports_decision = "What information has entered the system, and from where?"
    requires_evidence = "None — this agent produces the evidence base."
    confidence_method = "Not applicable; collection is factual."
    correctness_check = "Duplicate rate and collection failure rate per source."
    success_metric = "Documents collected per source per run with zero unlogged failures."
    human_review = "none"

    def execute(self, session: Session, **kwargs: Any) -> dict[str, Any]:
        source_ids: list[str] | None = kwargs.get("source_ids")
        limit: int = int(kwargs.get("limit", 500))
        sources: list[Source] = kwargs.get("sources") or build_sources(source_ids)

        created: list[str] = []
        per_source: dict[str, int] = {}
        skipped_duplicates = 0
        failures: list[dict[str, str]] = []

        for source in sources:
            if not source.is_configured():
                log.info("source not configured, skipping id=%s", source.source_id)
                per_source[source.source_id] = 0
                continue
            try:
                items = _collect_with_retry(source, limit)
            except SourceError as exc:
                retry_count = getattr(exc, "retry_count", 0)
                failures.append({
                    "source": source.source_id,
                    "error": f"{type(exc).__name__}: {exc}",
                    "retry_count": retry_count,
                })
                bus.publish(
                    EventName.DOCUMENT_COLLECTION_FAILED,
                    {"source": source.source_id, "error": str(exc), "retry_count": retry_count},
                    session,
                )
                continue
            except Exception as exc:  # unexpected: still isolated per source
                retry_count = getattr(exc, "retry_count", 0)
                failures.append({
                    "source": source.source_id,
                    "error": f"{type(exc).__name__}: {exc}",
                    "retry_count": retry_count,
                })
                bus.publish(
                    EventName.DOCUMENT_COLLECTION_FAILED,
                    {"source": source.source_id, "error": str(exc), "retry_count": retry_count},
                    session,
                )
                continue

            existing = set(
                session.scalars(
                    select(RawDocument.external_id).where(RawDocument.source == source.source_id)
                ).all()
            )
            count = 0
            for item in items:
                if item.external_id in existing:
                    skipped_duplicates += 1
                    continue
                existing.add(item.external_id)
                metadata = dict(item.metadata)
                metadata.setdefault("doc_type", item.doc_type or source.doc_type)
                metadata["observed_at"] = item.observed_at.isoformat()
                document = RawDocument(
                    source=source.source_id,
                    external_id=item.external_id,
                    collected_at=item.observed_at,
                    content=item.content,
                    content_hash=item.content_hash,
                    doc_metadata=metadata,
                )
                session.add(document)
                session.flush()
                created.append(document.id)
                count += 1
            per_source[source.source_id] = count

        session.flush()
        for document_id in created:
            bus.publish(EventName.DOCUMENT_COLLECTED, {"raw_document_id": document_id}, session)

        return {
            "collected": len(created),
            "raw_document_ids": created,
            "per_source": per_source,
            "skipped_duplicates": skipped_duplicates,
            "failures": failures,
        }


def _collect_with_retry(source: Source, limit: int) -> list:
    """Wrap source.collect() with exponential backoff retry.

    RateLimitExceeded is never retried. All other failures are retried up to
    settings.source_max_retries times with exponential backoff. The retry
    count is attached to the final SourceUnavailable so the collector can
    include it in the event payload.
    """
    max_retries = settings.source_max_retries
    backoff = settings.source_backoff_seconds
    last_exc: Exception = SourceError("unknown")

    for attempt in range(max_retries + 1):
        try:
            return source.collect(limit=limit)
        except RateLimitExceeded:
            raise  # never retry rate limits
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries:
                wait = backoff * (2 ** attempt)
                log.warning(
                    "source=%s attempt=%d/%d failed, retrying in %.1fs: %s",
                    source.source_id, attempt + 1, max_retries, wait, exc,
                )
                time.sleep(wait)
            else:
                log.error("source=%s exhausted %d retries: %s", source.source_id, max_retries, exc)

    from app.sources.base import SourceUnavailable
    err = SourceUnavailable(str(last_exc))
    err.retry_count = max_retries  # type: ignore[attr-defined]
    raise err
