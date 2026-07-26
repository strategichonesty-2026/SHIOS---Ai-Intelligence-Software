"""5.4 Trend Agent — statistics only, no model calls.

Two metrics are computed per ISO week:

  job_postings_count  — distinct documents mentioning an entity (always available).
  median_salary       — median of (salary_min + salary_max) / 2 across job rows that
                        carry salary data for an entity in that week. Only written when
                        at least one salary observation exists; never invented for weeks
                        with no data.

Both are recomputed idempotently: running twice over the same data produces identical
rows, which is what lets the reality check compare a forecast against a stable actual.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from statistics import median
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import Agent
from app.events.bus import bus
from app.events.types import EventName
from app.models.tables import Evidence, Job, Trend
from app.services.periods import period_range, shift_period, week_period
from app.services.stats import direction_of, percent_change

METRIC_COUNT = "job_postings_count"
METRIC_SALARY = "median_salary"


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

        # --- job_postings_count -------------------------------------------
        existing_count = {
            (t.entity_type, t.entity_name, t.period): t
            for t in session.scalars(select(Trend).where(Trend.metric == METRIC_COUNT))
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
                trend = existing_count.get(key)
                if trend is None:
                    trend = Trend(
                        metric=METRIC_COUNT,
                        entity_type=entity_type,
                        entity_name=entity_name,
                        period=period,
                    )
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

        # --- median_salary ------------------------------------------------
        salary_written = self._compute_salary_trends(
            session, entities, ordered_periods, docs, evidence_ids
        )
        written += salary_written

        session.flush()
        bus.publish(
            EventName.TREND_UPDATED,
            {
                "metric": METRIC_COUNT,
                "entities": len(entities),
                "periods": len(ordered_periods),
                "salary_trends": salary_written,
            },
            session,
        )
        return {
            "trends": written,
            "salary_trends": salary_written,
            "entities": len(entities),
            "periods": ordered_periods,
            "latest_period": ordered_periods[-1] if ordered_periods else None,
            "next_period": shift_period(ordered_periods[-1], 1) if ordered_periods else None,
        }

    # -- salary helpers ----------------------------------------------------

    def _compute_salary_trends(
        self,
        session: Session,
        entities: list[tuple[str, str]],
        ordered_periods: list[str],
        docs: dict[tuple[str, str, str], set[str]],
        evidence_ids: dict[tuple[str, str, str], list[str]],
    ) -> int:
        """Compute median_salary per (entity_type, entity_name, period).

        Only job documents with both salary_min and salary_max contribute.
        Weeks with no salary data produce no row — a missing row is honest;
        a zero or invented row is not.
        """
        # Build a map: normalized_document_id -> midpoint salary
        salary_rows = session.execute(
            select(
                Job.normalized_document_id,
                Job.salary_min,
                Job.salary_max,
                Job.posted_at,
            ).where(
                Job.salary_min.is_not(None),
                Job.salary_max.is_not(None),
            )
        ).all()

        # Map doc_id -> salary midpoint and period
        doc_salary: dict[str, tuple[float, str]] = {}
        for norm_doc_id, sal_min, sal_max, posted_at in salary_rows:
            midpoint = (float(sal_min) + float(sal_max)) / 2.0
            period = week_period(posted_at)
            doc_salary[norm_doc_id] = (midpoint, period)

        # For each (entity, period) collect salary midpoints from overlapping docs
        salary_by_key: dict[tuple[str, str, str], list[float]] = defaultdict(list)
        for (entity_type, entity_name, period), doc_ids in docs.items():
            if (entity_type, entity_name) not in {e for e in entities}:
                continue
            for doc_id in doc_ids:
                if doc_id in doc_salary:
                    midpoint, sal_period = doc_salary[doc_id]
                    # Use the evidence period, not the salary posting period,
                    # so salary and count series are aligned on the same axis.
                    salary_by_key[(entity_type, entity_name, period)].append(midpoint)

        existing_salary = {
            (t.entity_type, t.entity_name, t.period): t
            for t in session.scalars(select(Trend).where(Trend.metric == METRIC_SALARY))
        }

        written = 0
        for entity_type, entity_name in entities:
            previous_value: float | None = None
            for period in ordered_periods:
                key = (entity_type, entity_name, period)
                salaries = salary_by_key.get(key, [])
                if not salaries:
                    previous_value = None
                    continue  # no salary data this week — honest omission
                value = round(median(salaries), 2)
                delta = 0.0 if previous_value is None else value - previous_value
                delta_pct = 0.0 if previous_value is None else percent_change(value, previous_value)
                trend = existing_salary.get(key)
                if trend is None:
                    trend = Trend(
                        metric=METRIC_SALARY,
                        entity_type=entity_type,
                        entity_name=entity_name,
                        period=period,
                    )
                    session.add(trend)
                trend.value = value
                trend.delta = delta
                trend.delta_pct = round(delta_pct, 2)
                trend.direction = direction_of(delta)
                trend.sample_size = len(salaries)
                trend.evidence_ids = evidence_ids.get(key, [])
                trend.computed_at = datetime.now(UTC)
                previous_value = value
                written += 1
        return written
