"""5.1 Collector Agent — pull raw information from configured sources."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import Agent
from app.events.bus import bus
from app.events.types import EventName
from app.models.tables import RawDocument
from app.sources import Source, SourceError, build_sources

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
                items = source.collect(limit=limit)
            except SourceError as exc:
                failures.append({"source": source.source_id, "error": f"{type(exc).__name__}: {exc}"})
                bus.publish(
                    EventName.DOCUMENT_COLLECTION_FAILED,
                    {"source": source.source_id, "error": str(exc)},
                    session,
                )
                continue
            except Exception as exc:  # unexpected: still isolated per source
                failures.append({"source": source.source_id, "error": f"{type(exc).__name__}: {exc}"})
                bus.publish(
                    EventName.DOCUMENT_COLLECTION_FAILED,
                    {"source": source.source_id, "error": str(exc)},
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
