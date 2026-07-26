"""5.3 Knowledge Agent (minimal v1).

The spec allows a stub here. A stub that writes nothing is untestable, so this is the
smallest useful implementation instead: co-occurrence relationships between roles, skills
and technologies, each carrying the evidence that produced it. It is a relational stand-in
for the v2 graph, and it is deliberately not on the critical path — nothing downstream reads
from it, so replacing it with Neo4j later is a swap, not a migration.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import Agent
from app.events.bus import bus
from app.events.types import EventName
from app.models.tables import Evidence, KnowledgeRecord, NormalizedDocument

MIN_COOCCURRENCE = 3


class KnowledgeAgent(Agent):
    name = "knowledge"
    supports_decision = "Which capabilities travel together in the market?"
    requires_evidence = "At least three co-occurring documents per relationship."
    confidence_method = "Co-occurrence count divided by the more frequent entity's document count."
    correctness_check = "Relationships are re-derived each run; stale pairs fall below threshold."
    success_metric = "Relationship set changes smoothly rather than churning between runs."
    human_review = "none"

    def execute(self, session: Session, **kwargs: Any) -> dict[str, Any]:
        limit_docs = int(kwargs.get("limit", 5000))
        rows = session.execute(
            select(Evidence.normalized_document_id, Evidence.entity_type, Evidence.entity_name)
            .join(NormalizedDocument, NormalizedDocument.id == Evidence.normalized_document_id)
            .limit(limit_docs * 20)
        ).all()

        by_doc: dict[str, list[tuple[str, str]]] = defaultdict(list)
        totals: dict[tuple[str, str], int] = defaultdict(int)
        for doc_id, entity_type, entity_name in rows:
            by_doc[doc_id].append((entity_type, entity_name))
            totals[(entity_type, entity_name)] += 1

        pair_docs: dict[tuple[tuple[str, str], tuple[str, str]], list[str]] = defaultdict(list)
        for doc_id, entities in by_doc.items():
            unique = sorted(set(entities))
            for i, left in enumerate(unique):
                for right in unique[i + 1 :]:
                    if left[0] == "role" or right[0] == "role":
                        pair_docs[(left, right)].append(doc_id)

        session.query(KnowledgeRecord).delete()
        session.flush()

        written = 0
        for (left, right), doc_ids in pair_docs.items():
            if len(doc_ids) < MIN_COOCCURRENCE:
                continue
            subject, obj = (left, right) if left[0] == "role" else (right, left)
            denominator = max(totals[subject], 1)
            session.add(
                KnowledgeRecord(
                    subject=f"{subject[0]}:{subject[1]}",
                    predicate="requires" if obj[0] in {"skill", "technology"} else "co_occurs_with",
                    object_=f"{obj[0]}:{obj[1]}",
                    confidence=round(min(1.0, len(doc_ids) / denominator), 4),
                    evidence_ids=doc_ids[:25],
                )
            )
            written += 1

        session.flush()
        bus.publish(EventName.KNOWLEDGE_UPDATED, {"records": written}, session)
        return {"knowledge_records": written}
