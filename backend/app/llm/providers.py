"""Provider implementations.

`RuleBasedProvider` is the default and is not a stub: it is a fully deterministic
implementation that lets the whole intelligence loop run with zero external dependencies,
zero cost, and reproducible output. That property is what makes the governance tests
meaningful — an assertion about a recommendation is stable across runs.

Hosted providers are used when LLM_PROVIDER is set. They degrade to the rule provider on
any error rather than failing the pipeline, and every degradation is logged.
"""

from __future__ import annotations

import json
import logging
import textwrap
from typing import Any

import httpx

from app.config import settings
from app.llm.base import LLMProvider
from app.services import taxonomy

log = logging.getLogger("shios.llm")

_AUDIENCE_VERB = {
    "individual": "Build",
    "manager": "Plan for",
    "executive": "Fund",
    "investor": "Watch",
    "student": "Prioritise",
}


class RuleBasedProvider(LLMProvider):
    name = "rule"

    def extract_entities(self, text: str, doc_type: str) -> dict[str, Any]:
        salary_min, salary_max = taxonomy.find_salary(text)
        return {
            "skills": taxonomy.find_skills(text),
            "technologies": taxonomy.find_technologies(text),
            "roles": taxonomy.find_roles(text),
            "companies": [],
            "locations": [],
            "seniority": taxonomy.find_seniority(text),
            "remote_type": taxonomy.find_remote_type(text),
            "salary_min": salary_min,
            "salary_max": salary_max,
        }

    def summarize(self, text: str, max_words: int = 120, style: str = "neutral") -> str:
        words = " ".join(text.split())
        if not words:
            return ""
        clipped = " ".join(words.split(" ")[:max_words])
        return clipped + ("…" if len(words.split(" ")) > max_words else "")

    def generate_recommendation(self, context: dict[str, Any], audience: str) -> dict[str, Any]:
        entity = context.get("entity_name", "this signal")
        entity_type = context.get("entity_type", "skill")
        direction = context.get("direction", "flat")
        delta_pct = float(context.get("delta_pct", 0.0))
        periods = int(context.get("periods_observed", 0))
        horizon = context.get("horizon", "4w")
        verb = _AUDIENCE_VERB.get(audience, "Consider")

        # Fix: only mention % change if it's meaningful; flat is flat not "rising 0%"
        if direction == "up" and abs(delta_pct) > 0:
            trend_phrase = f"up {abs(delta_pct):.0f}% over the last {periods} weeks"
        elif direction == "down" and abs(delta_pct) > 0:
            trend_phrase = f"down {abs(delta_pct):.0f}% over the last {periods} weeks"
        else:
            trend_phrase = f"holding steady over the last {periods} weeks"

        text = (
            f"{verb} skills in {entity}. "
            f"Job postings mentioning {entity} are {trend_phrase}, "
            f"and the next {horizon} forecast points the same way."
        )
        rationale = (
            f"Based on {periods} weeks of job posting data for {entity}. "
            f"The system tracks mentions per week and fits a straight-line forecast — "
            f"no guesswork, just counts. This recommendation carries the forecast's own "
            f"confidence level, not a separate claim."
        )
        risks = [
            "Job postings lag actual hiring by a few weeks — the market may have already shifted.",
            "This data comes from a limited set of sources. A big job board we don't read could tell a different story.",
        ]
        if periods < 4:
            risks.append("We've only tracked this signal for a short time — treat it as early indication, not a firm trend.")
        alternatives = [
            f"If demand for {entity} levels off, the skills you build will still transfer to related areas.",
            "If the trend reverses at the next review date, revisit before investing further.",
        ]
        outcomes = {
            "individual": [f"A credible, evidenced reason to prioritise {entity} in your next quarter."],
            "manager": [f"Team coverage for {entity} without waiting for an emergency."],
            "executive": [f"Budget aligned to a measured demand signal, not a hunch."],
            "investor": [f"An earlier read on which vendors are positioned around {entity}."],
            "student": [f"Coursework and projects aimed at {entity} while demand is moving in your favour."],
        }.get(audience, [f"A more informed decision about {entity}."])

        return {
            "recommendation_text": text,
            "rationale": rationale,
            "risks": risks,
            "alternative_scenarios": alternatives,
            "expected_outcomes": outcomes,
        }

    def analyze_story(self, text: str, context: dict[str, Any]) -> dict[str, Any]:
        """Deterministic, template-based story analysis. Numbers come only from context['related_trends']."""
        title = context.get("title", "this article")
        related_trends = context.get("related_trends", [])

        # Honesty requirement: state that analysis is templated, not model-generated.
        honesty_note = (
            "[Note: analysis fields are templated by the rule-based provider, not model-generated.]"
        )

        if related_trends:
            trend = related_trends[0]
            trend_summary = (
                f"{trend['entity_name']} ({trend['entity_type']}) is trending {trend['direction']} "
                f"with a value of {trend['value']} and a delta of {trend['delta']:+}."
            )
            business_impact = (
                f"Based on observed trend data, {trend['entity_name']} shows a {trend['direction']} "
                f"direction ({trend['delta']:+} change). Budget and hiring decisions tied to this "
                f"signal should be reviewed at the next planning cycle."
            )
            technology_impact = (
                f"Technology adoption signals for {trend['entity_name']} indicate a {trend['direction']} "
                f"trajectory. Teams evaluating tooling in this area should factor this movement into "
                f"roadmap decisions."
            )
        else:
            trend_summary = "No trend data is available for the entities in this story yet."
            business_impact = (
                "No trend data is available for the entities in this story yet. "
                "Business impact cannot be quantified from available signal."
            )
            technology_impact = (
                "No trend data is available for the entities in this story yet. "
                "Technology impact assessment is deferred until trend data is collected."
            )

        return {
            "executive_summary": (
                f"{honesty_note} This article covers '{title}'. {trend_summary}"
            ),
            "why_it_matters": (
                f"This story touches signals the intelligence system is actively tracking. "
                f"{trend_summary}"
            ),
            "business_impact": business_impact,
            "technology_impact": technology_impact,
            "strategic_recommendation": (
                f"Monitor the entities mentioned in this article against the trend register. "
                f"No directional claim is made beyond what the trend data supports. {honesty_note}"
            ),
        }


class _HostedProvider(LLMProvider):
    """Shared plumbing for hosted providers with rule-based fallback."""

    def __init__(self) -> None:
        self._fallback = RuleBasedProvider()

    def _complete(self, system: str, user: str) -> str:  # pragma: no cover - network
        raise NotImplementedError

    def _json_call(self, system: str, user: str, fallback: dict[str, Any]) -> dict[str, Any]:
        try:  # pragma: no cover - network
            raw = self._complete(system, user).strip()
            raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else fallback
        except Exception as exc:
            log.warning("%s call failed, using rule provider: %s", self.name, exc)
            return fallback

    def extract_entities(self, text: str, doc_type: str) -> dict[str, Any]:
        fallback = self._fallback.extract_entities(text, doc_type)
        system = (
            "Extract structured entities from the document. Respond with JSON only, no prose, "
            "with keys: skills, technologies, roles, companies, locations, seniority, "
            "remote_type, salary_min, salary_max. Use lowercase canonical names."
        )
        merged = self._json_call(system, textwrap.shorten(text, 6000), fallback)
        for key, value in fallback.items():
            if key not in merged or merged[key] in (None, [], ""):
                merged[key] = value
        return merged

    def summarize(self, text: str, max_words: int = 120, style: str = "neutral") -> str:
        system = (
            f"Summarise in at most {max_words} words, {style} tone. State only what the text "
            "supports. If the text is insufficient, say so plainly."
        )
        try:  # pragma: no cover - network
            return self._complete(system, textwrap.shorten(text, 8000)).strip()
        except Exception as exc:
            log.warning("%s summarize failed: %s", self.name, exc)
            return self._fallback.summarize(text, max_words, style)

    def generate_recommendation(self, context: dict[str, Any], audience: str) -> dict[str, Any]:
        fallback = self._fallback.generate_recommendation(context, audience)
        system = (
            "You write evidence-bound recommendations. Never assert beyond the supplied evidence. "
            "Respond with JSON only, keys: recommendation_text, rationale, risks (array), "
            "alternative_scenarios (array), expected_outcomes (array). No hype. Signal over noise."
        )
        user = f"Audience: {audience}\nEvidence context: {json.dumps(context, default=str)}"
        return self._json_call(system, user, fallback)

    def analyze_story(self, text: str, context: dict[str, Any]) -> dict[str, Any]:
        fallback = self._fallback.analyze_story(text, context)
        system = (
            "You analyse news articles for an intelligence system. Never invent numbers or trends. "
            "Use only what the supplied context provides. "
            "Respond with JSON only, no prose, no markdown fences. Keys: "
            "executive_summary, why_it_matters, business_impact, technology_impact, "
            "strategic_recommendation."
        )
        user = (
            f"Article text (truncated): {textwrap.shorten(text, 4000)}\n"
            f"Context: {json.dumps(context, default=str)}"
        )
        return self._json_call(system, user, fallback)


class AnthropicProvider(_HostedProvider):
    name = "anthropic"

    def _complete(self, system: str, user: str) -> str:  # pragma: no cover - network
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key or "",
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": settings.llm_model,
                "max_tokens": 1500,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=settings.llm_timeout_seconds,
        )
        response.raise_for_status()
        blocks = response.json().get("content", [])
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")


class OpenAIProvider(_HostedProvider):
    name = "openai"

    def _complete(self, system: str, user: str) -> str:  # pragma: no cover - network
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key or ''}"},
            json={
                "model": settings.llm_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=settings.llm_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


class GoogleProvider(_HostedProvider):
    name = "google"

    def _complete(self, system: str, user: str) -> str:  # pragma: no cover - network
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.llm_model}:generateContent?key={settings.google_api_key or ''}"
        )
        response = httpx.post(
            url,
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"parts": [{"text": user}]}],
            },
            timeout=settings.llm_timeout_seconds,
        )
        response.raise_for_status()
        parts = response.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)


_REGISTRY: dict[str, type[LLMProvider]] = {
    "rule": RuleBasedProvider,
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "google": GoogleProvider,
}

_instance: LLMProvider | None = None


def get_llm() -> LLMProvider:
    global _instance
    if _instance is None:
        provider_cls = _REGISTRY.get(settings.llm_provider, RuleBasedProvider)
        _instance = provider_cls()
        log.info("llm provider active: %s", _instance.name)
    return _instance


def set_llm(provider: LLMProvider | None) -> None:
    """Test seam."""
    global _instance
    _instance = provider
