"""5.4 Trend Agent — statistics only, no model calls.

Metric: `job_postings_count` (documents mentioning an entity, per ISO week). Recomputed
idempotently: running twice over the same evidence produces the same rows, which is what
lets the reality check compare a forecast against a stable actual.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import Agent
from app.events.bus import bus
from app.events.types import EventName
from app.models.tables import Evidence, Trend
from app.services.periods import period_range, shift_period
from app.services.stats import direction_of, percent_change

METRIC = "job_postings_count"


class TrendAgent(Agent):
    name = "trend"
    supports_decision = "Which capabilities are gaining or losing demand, and how fast?"
    requires_evidence = "Evidence rows tied to normalized documents; no evidence, no trend."
    confidence_method = "None — trends are counts, not estimates. Sample size is reported instead."
    correctness_check = "Recomputation is idempotent; counts reconcile against the evidence table."
    success_metric = "Every entity with evidence has a gap-free weekly series."
    human_review = "none"

    def execute(self, session: Session, **kwargs: Any) -> dict[str, Any]:
        entity_types: list[str] = kwargs.get("entity_types") or ["skill", "technology", "role"]
        min_total = int(kwargs.get("min_total_evidence", 3))

        rows = session.execute(
            select(
                Evidence.entity_type,
                Evidence.entity_name,
                Evidence.period,
                Evidence.normalized_document_id,
                Evidence.id,
            ).where(Evidence.entity_type.in_(entity_types))
        ).all()
        if not rows:
            return {"trends": 0, "entities": 0, "periods": []}

        docs: dict[tuple[str, str, str], set[str]] = defaultdict(set)
        evidence_ids: dict[tuple[str, str, str], list[str]] = defaultdict(list)
        totals: dict[tuple[str, str], int] = defaultdict(int)
        all_periods: set[str] = set()

        for entity_type, entity_name, period, doc_id, evidence_id in rows:
            key = (entity_type, entity_name, period)
            docs[key].add(doc_id)
            if len(evidence_ids[key]) < 25:
                evidence_ids[key].append(evidence_id)
            totals[(entity_type, entity_name)] += 1
            all_periods.add(period)

        ordered_periods = period_range(min(all_periods), max(all_periods))
        existing = {
            (t.entity_type, t.entity_name, t.period): t
            for t in session.scalars(select(Trend).where(Trend.metric == METRIC))
        }

        written = 0
        entities = [key for key, total in totals.items() if total >= min_total]
        for entity_type, entity_name in entities:
            previous_value: float | None = None
            for period in ordered_periods:
                key = (entity_type, entity_name, period)
                value = float(len(docs.get(key, ())))
                delta = 0.0 if previous_value is None else value - previous_value
                delta_pct = 0.0 if previous_value is None else percent_change(value, previous_value)
                trend = existing.get(key)
                if trend is None:
                    trend = Trend(metric=METRIC, entity_type=entity_type, entity_name=entity_name, period=period)
                    session.add(trend)
                trend.value = value
                trend.delta = delta
                trend.delta_pct = round(delta_pct, 2)
                trend.direction = direction_of(delta)
                trend.sample_size = int(value)
                trend.evidence_ids = evidence_ids.get(key, [])
                trend.computed_at = datetime.now(UTC)
                previous_value = value
                written += 1

        session.flush()
        bus.publish(
            EventName.TREND_UPDATED,
            {"metric": METRIC, "entities": len(entities), "periods": len(ordered_periods)},
            session,
        )
        return {
            "trends": written,
            "entities": len(entities),
            "periods": ordered_periods,
            "latest_period": ordered_periods[-1] if ordered_periods else None,
            "next_period": shift_period(ordered_periods[-1], 1) if ordered_periods else None,
        }
