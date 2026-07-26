"""5.10 Reporting Agent — human-readable output, evidence attached.

Seven report types. Every one of them carries `evidence_ids`, and none of them may state a
number that is not present in a trend, prediction or prediction result row. The LinkedIn
drafts follow the same rule: no hype, signal over noise, and a visible accuracy record
including the misses.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.base import Agent
from app.events.bus import bus
from app.events.types import EventName
from app.models.tables import LearningFeedback, Prediction, PredictionResult, Recommendation, Report, Trend
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
        if not snapshot["movers"]:
            return {"reports": 0, "reason": "no trend data to report"}

        builders = {
            "weekly_report": self._weekly,
            "monthly_report": self._monthly,
            "executive_summary": self._executive,
            "blog_draft": self._blog,
            "social_summary": self._social,
            "linkedin_article_draft": self._linkedin_article,
            "linkedin_post_draft": self._linkedin_post,
        }

        created: list[str] = []
        for report_type in report_types:
            builder = builders.get(report_type)
            if builder is None:
                continue
            title, subtitle, body = builder(snapshot)
            report = Report(
                report_type=report_type,
                title=title,
                subtitle=subtitle,
                body_markdown=body,
                payload=snapshot["payload"],
                evidence_ids=snapshot["evidence_ids"],
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

    def _weekly(self, snapshot: dict[str, Any]) -> tuple[str, str, str]:
        title = f"Weekly intelligence — {snapshot['latest_period']}"
        body = f"""# {title}

Window: {snapshot['first_period']} to {snapshot['latest_period']}.

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
        return title, "Evidence-backed movement in the configured sources", body

    def _monthly(self, snapshot: dict[str, Any]) -> tuple[str, str, str]:
        title = f"Monthly intelligence review — through {snapshot['latest_period']}"
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
        return title, "Thirty-day view with calibration", body

    def _executive(self, snapshot: dict[str, Any]) -> tuple[str, str, str]:
        risers = ", ".join(t.entity_name for t in snapshot["risers"][:3]) or "none"
        fallers = ", ".join(t.entity_name for t in snapshot["fallers"][:3]) or "none"
        title = f"Executive summary — {snapshot['latest_period']}"
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
        return title, "One page, evidence attached", body

    def _blog(self, snapshot: dict[str, Any]) -> tuple[str, str, str]:
        top = snapshot["risers"][0] if snapshot["risers"] else snapshot["movers"][0]
        title = f"What the job data actually says about {top.entity_name}"
        body = f"""# {title}

Every week the same claim goes around: some skill is about to change everything. Most of the
time nobody shows the count.

Here is the count.

{self._movement_table(snapshot)}

Over the window {snapshot['first_period']} to {snapshot['latest_period']}, mentions of
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
        return title, "Counting before concluding", body

    def _social(self, snapshot: dict[str, Any]) -> tuple[str, str, str]:
        top = snapshot["risers"][0] if snapshot["risers"] else snapshot["movers"][0]
        title = f"Social summary — {snapshot['latest_period']}"
        accuracy_note = (
            f"Accuracy on scored forecasts: {snapshot['accuracy']:.2f}."
            if snapshot["accuracy"] is not None
            else "No scored forecasts yet — treat as unproven."
        )
        body = (
            f"{top.entity_name} mentions: {top.value:.0f} this week ({top.delta:+.0f}).\n"
            f"Window: {snapshot['first_period']}–{snapshot['latest_period']}.\n"
            f"{accuracy_note}\n"
            f"Counts first, conclusions second."
        )
        return title, "", body

    def _linkedin_article(self, snapshot: dict[str, Any]) -> tuple[str, str, str]:
        top = snapshot["risers"][0] if snapshot["risers"] else snapshot["movers"][0]
        title = f"{top.entity_name} is moving. Here is the evidence, and here is what it is not."
        subtitle = f"Weekly read on {snapshot['latest_period']}, with the misses included"
        body = f"""# {title}

*{subtitle}*

I run a small intelligence system over job postings. It counts, it forecasts, and then it
grades its own forecasts. This is the {snapshot['latest_period']} read.

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
        return title, subtitle, body

    def _linkedin_post(self, snapshot: dict[str, Any]) -> tuple[str, str, str]:
        top = snapshot["risers"][0] if snapshot["risers"] else snapshot["movers"][0]
        accuracy = (
            f"Scored forecasts so far: {snapshot['scored_count']}, mean accuracy {snapshot['accuracy']:.2f}."
            if snapshot["accuracy"] is not None
            else "No forecast has expired yet, so there is no accuracy to show. Unproven."
        )
        body = f"""{top.entity_name} mentions moved {top.delta:+.0f} this week, to {top.value:.0f}.

Window: {snapshot['first_period']} to {snapshot['latest_period']}. Source: configured job feeds only.

{accuracy}

The number I care about is the second one. Anyone can publish a prediction. Publishing the
score is the harder part.

#CareerIntelligence #Agile #DataInformed #StrategicHonesty"""
        return f"Post draft — {snapshot['latest_period']}", "", body

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


def now() -> datetime:
    return datetime.now(UTC)
