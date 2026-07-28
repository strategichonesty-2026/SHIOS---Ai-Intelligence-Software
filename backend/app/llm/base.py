"""Model abstraction (spec section 12).

Three operations, no more. Anything an agent wants from a model has to fit one of these,
which keeps prompts short, testable, and swappable across providers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def extract_entities(self, text: str, doc_type: str) -> dict[str, Any]:
        """Return a dict shaped like schemas.contracts.ExtractedEntities."""

    @abstractmethod
    def summarize(self, text: str, max_words: int = 120, style: str = "neutral") -> str:
        """Return a plain-language summary."""

    @abstractmethod
    def generate_recommendation(self, context: dict[str, Any], audience: str) -> dict[str, Any]:
        """Return {recommendation_text, rationale, risks[], alternative_scenarios[], expected_outcomes[]}."""

    @abstractmethod
    def analyze_story(self, text: str, context: dict[str, Any]) -> dict[str, Any]:
        """Return {executive_summary, why_it_matters, business_impact,
        technology_impact, strategic_recommendation}."""


class LLMError(RuntimeError):
    pass
