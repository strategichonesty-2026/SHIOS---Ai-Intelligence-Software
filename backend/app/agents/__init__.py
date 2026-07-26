"""Agent registry.

Agents are modules in one process, not microservices (spec section 17). The registry exists
so the orchestrator and the API can enumerate them without importing each one by hand.
"""

from __future__ import annotations

from app.agents.base import Agent
from app.agents.collector import CollectorAgent
from app.agents.extraction import ExtractionAgent
from app.agents.knowledge import KnowledgeAgent
from app.agents.learning import LearningAgent
from app.agents.prediction import PredictionAgent
from app.agents.reality_check import RealityCheckAgent
from app.agents.recommendation import RecommendationAgent
from app.agents.reporting import ReportingAgent
from app.agents.trend import TrendAgent
from app.agents.validator import StrategicHonestyValidator

AGENT_CLASSES: list[type[Agent]] = [
    CollectorAgent,
    ExtractionAgent,
    KnowledgeAgent,
    TrendAgent,
    PredictionAgent,
    RecommendationAgent,
    StrategicHonestyValidator,
    RealityCheckAgent,
    LearningAgent,
    ReportingAgent,
]

AGENTS: dict[str, type[Agent]] = {cls.name: cls for cls in AGENT_CLASSES}


def get_agent(name: str) -> Agent:
    if name not in AGENTS:
        raise KeyError(f"unknown agent: {name}")
    return AGENTS[name]()


def governance_catalog() -> list[dict[str, str]]:
    return [cls.governance() for cls in AGENT_CLASSES]


__all__ = [
    "AGENTS",
    "AGENT_CLASSES",
    "Agent",
    "CollectorAgent",
    "ExtractionAgent",
    "KnowledgeAgent",
    "LearningAgent",
    "PredictionAgent",
    "RealityCheckAgent",
    "RecommendationAgent",
    "ReportingAgent",
    "StrategicHonestyValidator",
    "TrendAgent",
    "get_agent",
    "governance_catalog",
]
