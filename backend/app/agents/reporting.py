"""5.10 Reporting Agent — human-readable output, evidence attached.

Seven report types plus executive_brief. Every one of them carries `evidence_ids`, and none of
them may state a number that is not present in a trend, prediction or prediction result row. The
LinkedIn drafts follow the same rule: no hype, signal over noise, and a visible accuracy record
including the misses.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.base import Agent
from app.events.bus import bus
from app.events.types import EventName
from app.llm.providers import get_llm
from app.models.tables import (
    Evidence,
    Job,
    LearningFeedback,
    NormalizedDocument,
    Prediction,
    PredictionResult,
    RawDocument,
    Recommendation,
    Report,
    Trend,
)
from app.services.periods import week_label as _week_to_date_range
from app.services.stats import mean


REPORT_TYPES = [
    "weekly_report",
    "monthly_report",
    "executive_summary",
    "blog_draft",
    "social_summary",
    "linkedin_article_draft",
    "linkedin_post_draft",
]

_EVIDENCE_SUMMARY_REPORT_TYPES = {"blog_draft", "linkedin_article_draft", "executive_brief"}


class ReportingAgent(Agent):
    name = "reporting"
    supports_decision = "What does a human need to read to act on this week's intelligence?"
    requires_evidence = "Every figure traces to a trend, prediction or prediction result row."
    confidence_method = "Reports restate source confidence; they never assert their own."
    correctness_check = "Figures in the report reconcile against the API endpoints they came from."
    success_metric = "Zero unsourced numbers in published reports."
    human_review = "required before external publication"

    def execute(self, session: Session, **kwargs: Any) -> dict[str, Any]:
        report_types: list[str] = kwargs.get("report_types") or [
            "weekly_report",
            "executive_summary",
            "linkedin_article_draft",
            "linkedin_post_draft",
        ]
        top_n = int(kwargs.get("top_n", 5))

        snapshot = self._snapshot(session, top_n)

        builders = {
            "weekly_report": self._weekly,
            "monthly_report": self._monthly,
            "executive_summary": self._executive,
            "blog_draft": self._blog,
            "social_summary": self._social,
            "linkedin_article_draft": self._linkedin_article,
            "linkedin_post_draft": self._linkedin_post,
            "executive_brief": lambda snap: self._executive_brief(session, top_n),
        }

        created: list[str] = []
        for report_type in report_types:
            builder = builders.get(report_type)
            if builder is None:
                continue

            # Trend-dependent report types skip when there's no trend data.
            if report_type != "executive_brief" and not snapshot["movers"]:
                continue

            result = builder(snapshot)
            if result is None:
                continue

            title, subtitle, body, extra_payload, report_evidence_ids = result

            # Append evidence summary section for qualifying report types.
            if report_type in _EVIDENCE_SUMMARY_REPORT_TYPES:
                evidence_summary = self._evidence_summary(
                    session, report_evidence_ids, snapshot.get("predictions", [])
                )
                body = body + _render_evidence_summary(evidence_summary)
                extra_payload = {**extra_payload, "evidence_summary": evidence_summary}

            payload = {**snapshot["payload"], **extra_payload}

            report = Report(
                report_type=report_type,
                title=title,
                subtitle=subtitle,
                body_markdown=body,
                payload=payload,
                evidence_ids=report_evidence_ids,
                period_start=snapshot["first_period"],
                period_end=snapshot["latest_period"],
            )
            session.add(report)
            session.flush()
            created.append(report.id)
            bus.publish(
                EventName.REPORT_GENERATED,
                {"report_id": report.id, "report_type": report_type},
                session,
            )

        session.flush()
        return {"reports": len(created), "report_ids": created}

    # -- data ---------------------------------------------------------------

    def _snapshot(self, session: Session, top_n: int) -> dict[str, Any]:
        latest_period = session.scalar(select(func.max(Trend.period)))
        first_period = session.scalar(select(func.min(Trend.period)))
        latest_trends = list(
            session.scalars(select(Trend).where(Trend.period == latest_period).order_by(Trend.value.desc()))
        )
        movers = sorted(latest_trends, key=lambda t: abs(t.delta), reverse=True)[:top_n]
        risers = [t for t in sorted(latest_trends, key=lambda t: t.delta, reverse=True) if t.delta > 0][:top_n]
        fallers = [t for t in sorted(latest_trends, key=lambda t: t.delta) if t.delta < 0][:top_n]

        predictions = list(
            session.scalars(
                select(Prediction)
                .where(Prediction.status == "published")
                .order_by(Prediction.confidence.desc())
                .limit(top_n)
            )
        )
        recommendations = list(
            session.scalars(
                select(Recommendation).order_by(Recommendation.created_at.desc()).limit(top_n * 2)
            )
        )
        results = list(session.scalars(select(PredictionResult).limit(500)))
        feedback = list(session.scalars(select(LearningFeedback).limit(500)))

        accuracy = mean([r.accuracy_score for r in results]) if results else None
        calibration = mean([f.confidence_calibration_delta for f in feedback]) if feedback else None
        evidence_ids = [e for t in movers for e in (t.evidence_ids or [])][:40]

        return {
            "latest_period": latest_period or "",
            "first_period": first_period or "",
            "latest_period_fmt": _week_to_date_range(latest_period or ""),
            "first_period_fmt": _week_to_date_range(first_period or ""),
            "movers": movers,
            "risers": risers,
            "fallers": fallers,
            "predictions": predictions,
            "recommendations": recommendations,
            "accuracy": accuracy,
            "calibration": calibration,
            "scored_count": len(results),
            "evidence_ids": evidence_ids,
            "payload": {
                "latest_period": latest_period,
                "risers": [{"name": t.entity_name, "value": t.value, "delta": t.delta} for t in risers],
                "fallers": [{"name": t.entity_name, "value": t.value, "delta": t.delta} for t in fallers],
                "mean_accuracy": accuracy,
                "mean_calibration_delta": calibration,
                "scored_predictions": len(results),
            },
        }

    def _trends_for_entities(
        self,
        session: Session,
        entity_pairs: list[tuple[str, str]],
        latest_period: str,
    ) -> list[dict[str, Any]]:
        """Current Trend row (if any) for each (entity_type, entity_name) at the latest period.
        Entities with no Trend row are omitted — never zero-filled."""
        if not entity_pairs or not latest_period:
            return []
        rows = list(
            session.scalars(
                select(Trend).where(
                    Trend.period == latest_period,
                )
            )
        )
        pair_set = {(et, en) for et, en in entity_pairs}
        return [
            {
                "entity_type": t.entity_type,
                "entity_name": t.entity_name,
                "value": t.value,
                "delta": t.delta,
                "direction": t.direction,
            }
            for t in rows
            if (t.entity_type, t.entity_name) in pair_set
        ]

    def _evidence_summary(
        self,
        session: Session,
        evidence_ids: list[str],
        predictions: list[Any],
    ) -> dict[str, Any]:
        deduped = list(dict.fromkeys(evidence_ids))
        if not deduped:
            return {
                "jobs_analyzed": 0,
                "companies": 0,
                "github_projects": 0,
                "news_articles": 0,
                "research_papers": None,
                "distinct_sources": 0,
                "last_updated": None,
                "confidence": None,
                "not_collected": ["Research Papers", "SEC Filings", "Government Data"],
            }

        rows = list(
            session.execute(
                select(Evidence, NormalizedDocument)
                .join(NormalizedDocument, NormalizedDocument.id == Evidence.normalized_document_id)
                .where(Evidence.id.in_(deduped))
            ).all()
        )

        jobs_analyzed = sum(1 for _, nd in rows if nd.doc_type == "job")
        github_projects = sum(1 for _, nd in rows if nd.doc_type == "repo")
        news_articles = sum(1 for _, nd in rows if nd.doc_type == "article")

        # Companies via Job.company_id path
        norm_doc_ids_for_jobs = [nd.id for _, nd in rows if nd.doc_type == "job"]
        distinct_company_count = 0
        if norm_doc_ids_for_jobs:
            company_id_rows = list(
                session.scalars(
                    select(func.count(func.distinct(Job.company_id)))
                    .where(
                        Job.normalized_document_id.in_(norm_doc_ids_for_jobs),
                        Job.company_id.is_not(None),
                    )
                )
            )
            distinct_company_count = company_id_rows[0] if company_id_rows else 0

        distinct_sources = len({ev.source for ev, _ in rows})
        last_updated = max((nd.observed_at for _, nd in rows), default=None)

        # Confidence: mean of Prediction rows whose supporting_evidence_ids intersects evidence_ids
        evidence_set = set(deduped)
        matching_confidences = [
            p.confidence
            for p in predictions
            if set(p.supporting_evidence_ids or []) & evidence_set
        ]
        confidence = mean(matching_confidences) if matching_confidences else None

        return {
            "jobs_analyzed": jobs_analyzed,
            "companies": distinct_company_count,
            "github_projects": github_projects,
            "news_articles": news_articles,
            "research_papers": None,
            "distinct_sources": distinct_sources,
            "last_updated": last_updated.isoformat() if last_updated else None,
            "confidence": confidence,
            "not_collected": ["Research Papers", "SEC Filings", "Government Data"],
        }

    # -- shared fragments ---------------------------------------------------

    def _movement_table(self, snapshot: dict[str, Any]) -> str:
        lines = ["| Signal | Type | This week | Change | Direction |", "|---|---|---|---|---|"]
        for trend in snapshot["movers"]:
            lines.append(
                f"| {trend.entity_name} | {trend.entity_type} | {trend.value:.0f} | "
                f"{trend.delta:+.0f} ({trend.delta_pct:+.0f}%) | {trend.direction} |"
            )
        return "\n".join(lines)

    def _accuracy_line(self, snapshot: dict[str, Any]) -> str:
        if snapshot["accuracy"] is None:
            return (
                "**Track record:** no forecast has reached its expiration date yet, so there is "
                "no accuracy to report. Treat every forecast below as unproven."
            )
        calibration = snapshot["calibration"] or 0.0
        stance = (
            "the system has been overconfident and has lowered its own confidence accordingly"
            if calibration < -0.05
            else "the system has been underconfident"
            if calibration > 0.05
            else "confidence is tracking accuracy"
        )
        return (
            f"**Track record:** {snapshot['scored_count']} forecasts scored, mean accuracy "
            f"{snapshot['accuracy']:.2f}, calibration delta {calibration:+.2f} — {stance}."
        )

    def _forecast_lines(self, snapshot: dict[str, Any]) -> str:
        if not snapshot["predictions"]:
            return "_No forecast currently clears the governance rules._"
        return "\n".join(
            f"- {p.statement} Confidence {p.confidence:.2f}, review by {p.review_date.isoformat()}."
            for p in snapshot["predictions"]
        )

    # -- builders -----------------------------------------------------------
    # All builders now return (title, subtitle, body, extra_payload, evidence_ids) | None

    def _weekly(self, snapshot: dict[str, Any]) -> tuple[str, str, str, dict, list[str]]:
        title = f"Weekly intelligence — {snapshot['latest_period_fmt']}"
        body = f"""# {title}

Window: {snapshot['first_period_fmt']} to {snapshot['latest_period_fmt']}.

## What moved
{self._movement_table(snapshot)}

## What we expect next
{self._forecast_lines(snapshot)}

## What we recommend
{self._recommendation_lines(snapshot)}

## What we do not know
- Posting volume is a proxy for demand, and it lags actual hiring.
- Only the configured sources are represented. Everything else is absent, not zero.

{self._accuracy_line(snapshot)}
"""
        return title, "Evidence-backed movement in the configured sources", body, {}, snapshot["evidence_ids"]

    def _monthly(self, snapshot: dict[str, Any]) -> tuple[str, str, str, dict, list[str]]:
        title = f"Monthly intelligence review — through {snapshot['latest_period_fmt']}"
        body = f"""# {title}

## Movement over the observed window
{self._movement_table(snapshot)}

## Forecast register
{self._forecast_lines(snapshot)}

## Calibration
{self._accuracy_line(snapshot)}

## Method note
Trends are counts of documents mentioning an entity per ISO week. Forecasts use ordinary
least squares over that series. Nothing here is model-generated speculation.
"""
        return title, "Thirty-day view with calibration", body, {}, snapshot["evidence_ids"]

    def _executive(self, snapshot: dict[str, Any]) -> tuple[str, str, str, dict, list[str]]:
        risers = ", ".join(t.entity_name for t in snapshot["risers"][:3]) or "none"
        fallers = ", ".join(t.entity_name for t in snapshot["fallers"][:3]) or "none"
        title = f"Executive summary — {snapshot['latest_period_fmt']}"
        body = f"""# {title}

**Rising:** {risers}
**Falling:** {fallers}

**Decision at hand:** where to place the next increment of hiring and training budget.

{self._accuracy_line(snapshot)}

## Three lines of evidence
{self._movement_table(snapshot)}

## Recommended action
{self._recommendation_lines(snapshot, audience="executive")}

## Caveat we will not bury
This reads posting volume from a narrow source set. It is a leading indicator with a lag, not
a hiring plan. Confidence figures are the system's own, and they are adjusted downward
automatically when past forecasts miss.
"""
        return title, "One page, evidence attached", body, {}, snapshot["evidence_ids"]

    def _blog(self, snapshot: dict[str, Any]) -> tuple[str, str, str, dict, list[str]]:
        top = snapshot["risers"][0] if snapshot["risers"] else snapshot["movers"][0]
        title = f"What the job data actually says about {top.entity_name}"
        body = f"""# {title}

Every week the same claim goes around: some skill is about to change everything. Most of the
time nobody shows the count.

Here is the count.

{self._movement_table(snapshot)}

Over the window {snapshot['first_period_fmt']} to {snapshot['latest_period_fmt']}, mentions of
**{top.entity_name}** moved {top.delta:+.0f} week over week, to {top.value:.0f}.

{self._accuracy_line(snapshot)}

That last line matters more than the forecast. A system that publishes predictions without
publishing its misses is marketing, not intelligence.

## What I would do with this
{self._recommendation_lines(snapshot, audience="individual")}

## What this does not tell you
It does not tell you who got hired. It does not cover sources we have not configured. And it
does not know your situation — only the market's.
"""
        return title, "Counting before concluding", body, {}, snapshot["evidence_ids"]

    def _social(self, snapshot: dict[str, Any]) -> tuple[str, str, str, dict, list[str]]:
        top = snapshot["risers"][0] if snapshot["risers"] else snapshot["movers"][0]
        title = f"Social summary — {snapshot['latest_period_fmt']}"
        accuracy_note = (
            f"Accuracy on scored forecasts: {snapshot['accuracy']:.2f}."
            if snapshot["accuracy"] is not None
            else "No scored forecasts yet — treat as unproven."
        )
        body = (
            f"{top.entity_name} mentions: {top.value:.0f} this week ({top.delta:+.0f}).\n"
            f"Window: {snapshot['first_period_fmt']}–{snapshot['latest_period_fmt']}.\n"
            f"{accuracy_note}\n"
            f"Counts first, conclusions second."
        )
        return title, "", body, {}, snapshot["evidence_ids"]

    def _linkedin_article(self, snapshot: dict[str, Any]) -> tuple[str, str, str, dict, list[str]]:
        top = snapshot["risers"][0] if snapshot["risers"] else snapshot["movers"][0]
        title = f"{top.entity_name} is moving. Here is the evidence, and here is what it is not."
        subtitle = f"Weekly read on {snapshot['latest_period_fmt']}, with the misses included"
        body = f"""# {title}

*{subtitle}*

I run a small intelligence system over job postings. It counts, it forecasts, and then it
grades its own forecasts. This is the {snapshot['latest_period_fmt']} read.

## The movement
{self._movement_table(snapshot)}

## The forecast
{self._forecast_lines(snapshot)}

## The grade
{self._accuracy_line(snapshot)}

## What I would actually do
{self._recommendation_lines(snapshot, audience="individual")}

## What I will not claim
I cannot see hiring outcomes, only postings. I cannot see sources I have not connected. And a
four-week linear forecast cannot see an inflection coming — by construction, it will miss the
turn. Those limits are in the system's own records, not just this post.

**Recommended images:** the movement table as a simple bar chart; the accuracy record over time.

**Call to action:** if you track a signal that contradicts this, I would rather see it than not.
"""
        return title, subtitle, body, {}, snapshot["evidence_ids"]

    def _linkedin_post(self, snapshot: dict[str, Any]) -> tuple[str, str, str, dict, list[str]]:
        top = snapshot["risers"][0] if snapshot["risers"] else snapshot["movers"][0]
        accuracy = (
            f"Scored forecasts so far: {snapshot['scored_count']}, mean accuracy {snapshot['accuracy']:.2f}."
            if snapshot["accuracy"] is not None
            else "No forecast has expired yet, so there is no accuracy to show. Unproven."
        )
        body = f"""{top.entity_name} mentions moved {top.delta:+.0f} this week, to {top.value:.0f}.

Window: {snapshot['first_period_fmt']} to {snapshot['latest_period_fmt']}. Source: configured job feeds only.

{accuracy}

The number I care about is the second one. Anyone can publish a prediction. Publishing the
score is the harder part.

#CareerIntelligence #Agile #DataInformed #StrategicHonesty"""
        return (
            f"Post draft — {snapshot['latest_period_fmt']}",
            "",
            body,
            {},
            snapshot["evidence_ids"],
        )

    def _executive_brief(
        self,
        session: Session,
        top_n: int,
    ) -> tuple[str, str, str, dict, list[str]] | None:
        articles = list(
            session.scalars(
                select(NormalizedDocument)
                .where(NormalizedDocument.doc_type == "article")
                .order_by(NormalizedDocument.observed_at.desc(), NormalizedDocument.id.desc())
                .limit(top_n)
            )
        )
        if not articles:
            return None

        latest_period = session.scalar(select(func.max(Trend.period))) or ""
        llm = get_llm()

        # Batch-fetch evidence for all article document ids.
        article_ids = [a.id for a in articles]
        all_evidence = list(
            session.scalars(
                select(Evidence).where(Evidence.normalized_document_id.in_(article_ids))
            )
        )
        evidence_by_doc: dict[str, list[Any]] = {}
        for ev in all_evidence:
            evidence_by_doc.setdefault(ev.normalized_document_id, []).append(ev)

        # Batch-fetch trends for all entity pairs across all articles.
        all_entity_pairs: list[tuple[str, str]] = [
            (ev.entity_type, ev.entity_name) for ev in all_evidence
        ]
        all_trends = self._trends_for_entities(session, all_entity_pairs, latest_period)
        trends_by_pair: dict[tuple[str, str], dict] = {
            (t["entity_type"], t["entity_name"]): t for t in all_trends
        }

        stories: list[dict[str, Any]] = []
        all_report_evidence_ids: list[str] = []

        for normalized in articles:
            reading_time_minutes = math.ceil(len(normalized.body_text.split()) / 220) or 1
            doc_evidence = evidence_by_doc.get(normalized.id, [])

            related_entities = [
                {"entity_type": ev.entity_type, "entity_name": ev.entity_name}
                for ev in doc_evidence
            ]
            related_trends = [
                trends_by_pair[pair]
                for ev in doc_evidence
                if (pair := (ev.entity_type, ev.entity_name)) in trends_by_pair
            ]

            raw_doc_obj = session.scalar(
                select(RawDocument).where(RawDocument.id == normalized.raw_document_id)
            )
            original_url = (
                raw_doc_obj.doc_metadata.get("link") if raw_doc_obj else None
            )

            context = {
                "title": normalized.title,
                "related_entities": related_entities,
                "related_trends": related_trends,
            }
            analysis = llm.analyze_story(normalized.body_text, context)

            stories.append(
                {
                    "document_id": normalized.id,
                    "title": normalized.title,
                    "source": normalized.source,
                    "published_at": normalized.observed_at.isoformat(),
                    "original_url": original_url,
                    "reading_time_minutes": reading_time_minutes,
                    "related_entities": related_entities,
                    "related_trends": related_trends,
                    "executive_summary": analysis["executive_summary"],
                    "why_it_matters": analysis["why_it_matters"],
                    "business_impact": analysis["business_impact"],
                    "technology_impact": analysis["technology_impact"],
                    "strategic_recommendation": analysis["strategic_recommendation"],
                }
            )
            all_report_evidence_ids.extend(ev.id for ev in doc_evidence)

        # Deduplicate while preserving order.
        report_evidence_ids = list(dict.fromkeys(all_report_evidence_ids))

        # Build body markdown.
        body_parts = ["# Executive Daily Brief\n"]
        for story in stories:
            url_line = (
                f"[Read article]({story['original_url']})"
                if story["original_url"]
                else "Source not linked"
            )
            body_parts.append(
                f"## {story['title']}\n\n"
                f"**Source:** {story['source']} · {story['published_at'][:10]} · "
                f"Reading time: {story['reading_time_minutes']} min · {url_line}\n\n"
                f"**Summary:** {story['executive_summary']}\n\n"
                f"**Why it matters:** {story['why_it_matters']}\n\n"
                f"**Business impact:** {story['business_impact']}\n\n"
                f"**Technology impact:** {story['technology_impact']}\n\n"
                f"**Strategic recommendation:** {story['strategic_recommendation']}\n"
            )

        body = "\n".join(body_parts)
        title = "Executive Daily Brief"
        subtitle = f"{len(stories)} article{'s' if len(stories) != 1 else ''} analysed"

        return title, subtitle, body, {"stories": stories}, report_evidence_ids

    def _recommendation_lines(self, snapshot: dict[str, Any], audience: str | None = None) -> str:
        recommendations = snapshot["recommendations"]
        if audience:
            recommendations = [r for r in recommendations if r.audience_type == audience] or recommendations
        if not recommendations:
            return "_No recommendation currently satisfies the two-evidence rule._"
        return "\n".join(
            f"- **{r.audience_type}:** {r.recommendation_text} (confidence {r.confidence:.2f})"
            for r in recommendations[:4]
        )


def _render_evidence_summary(evidence_summary: dict[str, Any]) -> str:
    conf = evidence_summary.get("confidence")
    confidence_str = f"{conf:.2f}" if conf is not None else "not available — no linked forecast"
    last_updated = evidence_summary.get("last_updated") or "unknown"
    return (
        f"\n## Evidence Summary\n"
        f"- Jobs analyzed: {evidence_summary['jobs_analyzed']}\n"
        f"- Companies: {evidence_summary['companies']}\n"
        f"- GitHub projects: {evidence_summary['github_projects']}\n"
        f"- News articles: {evidence_summary['news_articles']}\n"
        f"- Research papers: not collected\n"
        f"- Distinct sources: {evidence_summary['distinct_sources']}\n"
        f"- Last updated: {last_updated}\n"
        f"- Confidence: {confidence_str}\n"
    )


def now() -> datetime:
    return datetime.now(UTC)
