"""5.6 Recommendation Agent.

Hard rule from the spec: minimum two evidence ids. That is enforced in
`governance.rules.evaluate_recommendation`, not here — so the rule cannot be bypassed by a
future agent that forgets to check.

Recommendation text is produced through the LLM abstraction. With the default rule provider
this is fully deterministic; with a hosted provider the wording improves but the numbers,
evidence and confidence still come from the trend and prediction records.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import Agent
from app.events.bus import bus
from app.events.types import EventName
from app.governance.rules import GovernanceError, enforce, evaluate_recommendation
from app.llm.providers import get_llm
from app.models.tables import Prediction, Recommendation, Trend
from app.services.stats import clamp

log = logging.getLogger("shios.agents.recommendation")

AUDIENCES = ["individual", "manager", "executive", "investor", "student"]


class RecommendationAgent(Agent):
    name = "recommendation"
    supports_decision = "What should each audience actually do about a movement in demand?"
    requires_evidence = "At least two evidence ids plus a trend or prediction reference."
    confidence_method = "Inherited from the source prediction, discounted 10% per abstraction step."
    correctness_check = "Strategic Honesty Validator runs on every recommendation before release."
    success_metric = "Zero recommendations published without traceable evidence."
    human_review = "required before any recommendation is sent to an external audience"

    def execute(self, session: Session, **kwargs: Any) -> dict[str, Any]:
        audiences: list[str] = kwargs.get("audiences") or AUDIENCES
        top_n: int = int(kwargs.get("top_n", 5))
        prediction_ids: list[str] | None = kwargs.get("prediction_ids")
        min_confidence: float = float(kwargs.get("min_confidence", 0.15))

        query = select(Prediction).where(Prediction.status == "published")
        if prediction_ids:
            query = query.where(Prediction.id.in_(prediction_ids))
        predictions = list(session.scalars(query.order_by(Prediction.created_at.desc()).limit(200)))
        if not predictions:
            return {"recommendations": 0, "reason": "no published predictions"}

        # Rank by movement magnitude then confidence: act on what is both big and trustworthy.
        latest: dict[tuple[str, str], Prediction] = {}
        for prediction in predictions:
            key = (prediction.entity_type, prediction.entity_name)
            current = latest.get(key)
            if current is None or prediction.target_period > current.target_period:
                latest[key] = prediction

        ranked = sorted(
            latest.values(),
            key=lambda p: (abs(p.predicted_value) * p.confidence),
            reverse=True,
        )

        llm = get_llm()
        created: list[str] = []
        rejected: list[str] = []
        used = 0

        for prediction in ranked:
            if used >= top_n:
                break
            if prediction.confidence < min_confidence:
                continue
            trends = list(session.scalars(select(Trend).where(Trend.id.in_(prediction.trend_ids or []))))
            trends.sort(key=lambda t: t.period)
            if not trends:
                continue
            used += 1

            latest_trend = trends[-1]
            context = {
                "entity_name": prediction.entity_name,
                "entity_type": prediction.entity_type,
                "metric": prediction.metric,
                "direction": prediction.predicted_direction,
                "delta_pct": latest_trend.delta_pct,
                "periods_observed": len(trends),
                "horizon": prediction.horizon,
                "predicted_value": prediction.predicted_value,
                "latest_value": latest_trend.value,
                "confidence": prediction.confidence,
                "target_period": prediction.target_period,
            }

            for audience in audiences:
                drafted = llm.generate_recommendation(context, audience)
                confidence = clamp(prediction.confidence * 0.9, 0.01, 0.95)
                evidence_ids = list(prediction.supporting_evidence_ids or [])
                text = drafted.get("recommendation_text", "").strip()

                report = evaluate_recommendation(
                    confidence=confidence,
                    evidence_ids=evidence_ids,
                    trend_ids=[t.id for t in trends],
                    prediction_id=prediction.id,
                    text=text,
                )
                try:
                    enforce(report, f"recommendation for {audience}/{prediction.entity_name}")
                except GovernanceError as exc:
                    rejected.append(str(exc))
                    continue

                recommendation = Recommendation(
                    audience_type=audience,
                    domain=prediction.domain,
                    recommendation_text=text,
                    rationale=drafted.get("rationale", ""),
                    evidence_ids=evidence_ids,
                    trend_ids=[t.id for t in trends],
                    prediction_id=prediction.id,
                    confidence=round(confidence, 4),
                    alternative_scenarios=drafted.get("alternative_scenarios", []),
                    risks=drafted.get("risks", []),
                    expected_outcomes=drafted.get("expected_outcomes", []),
                    status="draft",
                )
                session.add(recommendation)
                session.flush()
                created.append(recommendation.id)
                bus.publish(
                    EventName.RECOMMENDATION_CREATED,
                    {"recommendation_id": recommendation.id, "audience": audience},
                    session,
                )

        session.flush()
        return {
            "recommendations": len(created),
            "recommendation_ids": created,
            "rejected_by_governance": rejected,
        }
