"""5.2 Extraction Agent — unstructured text to structured, countable records.

Also writes the Evidence rows. Evidence is the hinge of the whole Truth Maintenance System:
a trend is nothing more than a count over evidence, and a prediction is nothing more than a
fit over trends. If evidence is not written here, nothing downstream can be published.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import Agent
from app.events.bus import bus
from app.events.types import EventName
from app.llm.providers import get_llm
from app.models.tables import Company, Evidence, Job, NormalizedDocument, RawDocument, Skill, Technology
from app.services import taxonomy
from app.services.periods import week_period

log = logging.getLogger("shios.agents.extraction")

MAX_SNIPPET = 280


class ExtractionAgent(Agent):
    name = "extraction"
    supports_decision = "What entities does each document actually mention?"
    requires_evidence = "One raw document per normalized document."
    confidence_method = "Dictionary match is exact; model-assisted fields are merged, never overwritten."
    correctness_check = "Spot-audit of snippets against source text via the evidence API."
    success_metric = "Extraction failure rate below 1% and non-empty entity rate above 80% for jobs."
    human_review = "none"

    def execute(self, session: Session, **kwargs: Any) -> dict[str, Any]:
        raw_ids: list[str] | None = kwargs.get("raw_document_ids")
        limit: int = int(kwargs.get("limit", 1000))

        query = select(RawDocument)
        if raw_ids:
            query = query.where(RawDocument.id.in_(raw_ids))
        else:
            done = select(NormalizedDocument.raw_document_id)
            query = query.where(RawDocument.id.not_in(done))
        raw_documents = list(session.scalars(query.limit(limit)))

        llm = get_llm()
        normalized_ids: list[str] = []
        evidence_count = 0
        failures: list[str] = []

        for raw in raw_documents:
            try:
                entities = llm.extract_entities(raw.content, raw.doc_metadata.get("doc_type", "other"))
            except Exception as exc:
                failures.append(f"{raw.id}: {exc}")
                continue

            doc_type = raw.doc_metadata.get("doc_type", "other")
            title = raw.doc_metadata.get("title") or raw.content.splitlines()[0][:200]
            observed_at = _observed_at(raw)

            normalized = NormalizedDocument(
                raw_document_id=raw.id,
                doc_type=doc_type if doc_type in {"job", "article", "repo", "email"} else "other",
                title=title,
                body_text=raw.content,
                entities=entities,
                source=raw.source,
                observed_at=observed_at,
                created_at=datetime.now(UTC),
            )
            session.add(normalized)
            session.flush()
            normalized_ids.append(normalized.id)

            self._upsert_reference_entities(session, entities)
            if normalized.doc_type == "job":
                self._write_job(session, normalized, raw, entities, observed_at)
            evidence_count += self._write_evidence(session, normalized, entities, observed_at)

            bus.publish(
                EventName.DOCUMENT_NORMALIZED,
                {"normalized_document_id": normalized.id, "doc_type": normalized.doc_type},
                session,
            )

        session.flush()
        return {
            "normalized": len(normalized_ids),
            "normalized_document_ids": normalized_ids,
            "evidence_written": evidence_count,
            "failures": failures,
        }

    # -- helpers ------------------------------------------------------------

    def _upsert_reference_entities(self, session: Session, entities: dict[str, Any]) -> None:
        for name in entities.get("skills", []):
            if not session.scalar(select(Skill).where(Skill.name == name)):
                session.add(Skill(name=name))
        for name in entities.get("technologies", []):
            if not session.scalar(select(Technology).where(Technology.name == name)):
                session.add(Technology(name=name))
        session.flush()

    def _write_job(
        self,
        session: Session,
        normalized: NormalizedDocument,
        raw: RawDocument,
        entities: dict[str, Any],
        observed_at: datetime,
    ) -> None:
        company_name = raw.doc_metadata.get("company")
        company_id = None
        if company_name:
            company = session.scalar(select(Company).where(Company.name == company_name))
            if company is None:
                company = Company(name=company_name)
                session.add(company)
                session.flush()
            company_id = company.id

        session.add(
            Job(
                normalized_document_id=normalized.id,
                company_id=company_id,
                title=normalized.title,
                normalized_role=taxonomy.normalize_role(normalized.title) or "other",
                seniority=entities.get("seniority", "unknown"),
                location=raw.doc_metadata.get("location", "unknown"),
                remote_type=entities.get("remote_type", raw.doc_metadata.get("remote_type", "unknown")),
                posted_at=observed_at,
                skills=entities.get("skills", []),
                technologies=entities.get("technologies", []),
                salary_min=entities.get("salary_min"),
                salary_max=entities.get("salary_max"),
            )
        )
        session.flush()

    def _write_evidence(
        self,
        session: Session,
        normalized: NormalizedDocument,
        entities: dict[str, Any],
        observed_at: datetime,
    ) -> int:
        period = week_period(observed_at)
        pairs: list[tuple[str, str]] = []
        pairs += [("skill", name) for name in entities.get("skills", [])]
        pairs += [("technology", name) for name in entities.get("technologies", [])]
        pairs += [("role", name) for name in entities.get("roles", [])]
        role_from_title = taxonomy.normalize_role(normalized.title)
        if role_from_title != "other" and ("role", role_from_title) not in pairs:
            pairs.append(("role", role_from_title))

        written = 0
        for entity_type, entity_name in pairs:
            session.add(
                Evidence(
                    normalized_document_id=normalized.id,
                    entity_type=entity_type,
                    entity_name=entity_name,
                    period=period,
                    snippet=_snippet(normalized.body_text, entity_name),
                    source=normalized.source,
                )
            )
            written += 1
        session.flush()
        return written


def _observed_at(raw: RawDocument) -> datetime:
    stamp = raw.doc_metadata.get("observed_at")
    if stamp:
        try:
            return datetime.fromisoformat(stamp)
        except ValueError:
            pass
    collected = raw.collected_at
    return collected if collected.tzinfo else collected.replace(tzinfo=UTC)


def _snippet(text: str, term: str) -> str:
    lowered = text.lower()
    index = lowered.find(term.lower())
    if index == -1:
        return text[:MAX_SNIPPET].strip()
    start = max(0, index - MAX_SNIPPET // 2)
    return text[start : start + MAX_SNIPPET].strip()
