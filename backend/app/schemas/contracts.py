"""Versioned agent contracts.

These Pydantic models are the *only* legal way data moves between agents. If a field is not
here, an agent may not rely on it. Bump the `schema_version` literal to evolve a contract.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EntityType = Literal["skill", "technology", "role", "company"]
AudienceType = Literal["individual", "manager", "executive", "investor", "student"]
Direction = Literal["up", "down", "flat"]


class Contract(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")


# --- 5.1 Collector ---------------------------------------------------------


class RawDocumentV1(Contract):
    schema_version: Literal["v1"] = "v1"
    id: str
    source: str
    external_id: str
    collected_at: datetime
    content: str
    doc_metadata: dict[str, Any] = Field(default_factory=dict)


# --- 5.2 Extraction --------------------------------------------------------


class ExtractedEntities(Contract):
    skills: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    companies: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    seniority: str = "unknown"
    remote_type: str = "unknown"
    salary_min: float | None = None
    salary_max: float | None = None


class NormalizedDocumentV1(Contract):
    schema_version: Literal["v1"] = "v1"
    id: str
    raw_document_id: str
    doc_type: Literal["job", "article", "repo", "email", "other"]
    title: str
    body_text: str
    entities: ExtractedEntities
    source: str
    observed_at: datetime
    created_at: datetime


# --- 5.3 Knowledge ---------------------------------------------------------


class KnowledgeRecordV1(Contract):
    schema_version: Literal["v1"] = "v1"
    id: str
    subject: str
    predicate: str
    object: str
    confidence: float
    evidence_ids: list[str] = Field(default_factory=list)


# --- 5.4 Trend -------------------------------------------------------------


class TrendRecordV1(Contract):
    schema_version: Literal["v1"] = "v1"
    id: str
    metric: str
    entity_type: EntityType
    entity_name: str
    period: str
    value: float
    delta: float = 0.0
    delta_pct: float = 0.0
    direction: Direction = "flat"
    sample_size: int = 0
    evidence_ids: list[str] = Field(default_factory=list)
    computed_at: datetime


# --- 5.5 Prediction --------------------------------------------------------


class PredictionRecordV1(Contract):
    schema_version: Literal["v1"] = "v1"
    id: str
    statement: str
    domain: str
    metric: str
    entity_type: EntityType
    entity_name: str
    horizon: str
    target_period: str
    predicted_value: float
    lower_bound: float | None = None
    upper_bound: float | None = None
    interval_confidence: float | None = None
    predicted_direction: Direction
    confidence: float
    supporting_evidence_ids: list[str]
    trend_ids: list[str]
    assumptions: list[str]
    risks: list[str]
    method: str
    review_date: date
    expiration_date: date
    version: int
    status: str
    created_at: datetime

    @field_validator("confidence")
    @classmethod
    def _confidence_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("confidence must be within 0.0-1.0")
        return v

    @model_validator(mode="after")
    def _interval_is_ordered(self) -> PredictionRecordV1:
        if self.lower_bound is not None and self.upper_bound is not None:
            if self.lower_bound > self.upper_bound:
                raise ValueError("lower_bound must not exceed upper_bound")
        if self.interval_confidence is not None and not 0.0 < self.interval_confidence < 1.0:
            raise ValueError("interval_confidence must be strictly between 0.0 and 1.0")
        return self


# --- 5.6 Recommendation ----------------------------------------------------


class RecommendationRecordV1(Contract):
    schema_version: Literal["v1"] = "v1"
    id: str
    audience_type: AudienceType
    domain: str
    recommendation_text: str
    rationale: str = ""
    evidence_ids: list[str]
    trend_ids: list[str] = Field(default_factory=list)
    prediction_id: str | None = None
    confidence: float
    alternative_scenarios: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    expected_outcomes: list[str] = Field(default_factory=list)
    status: str = "draft"
    created_at: datetime


# --- 5.7 Strategic Honesty Validator ---------------------------------------


class ValidationResultV1(Contract):
    schema_version: Literal["v1"] = "v1"
    id: str
    target_type: Literal["prediction", "recommendation", "report"]
    target_id: str
    is_valid: bool
    issues: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    contradictory_evidence: list[str] = Field(default_factory=list)
    unknowns_noted: list[str] = Field(default_factory=list)
    validated_at: datetime


# --- 5.8 Reality Check -----------------------------------------------------


class PredictionResultV1(Contract):
    schema_version: Literal["v1"] = "v1"
    id: str
    prediction_id: str
    reality_period: str
    actual_value: float
    predicted_value: float
    accuracy_score: float
    deviation: float
    interval_covered: bool | None = None
    direction_correct: bool
    notes: str
    evaluated_at: datetime


# --- 5.9 Learning ----------------------------------------------------------


class LearningFeedbackV1(Contract):
    schema_version: Literal["v1"] = "v1"
    id: str
    prediction_id: str
    prediction_result_id: str
    metric: str
    entity_type: str
    accuracy_score: float
    false_positive: bool
    false_negative: bool
    coverage_correct: bool | None = None
    confidence_calibration_delta: float
    signal_quality_notes: str
    created_at: datetime


# --- 5.10 Reporting --------------------------------------------------------

ReportType = Literal[
    "weekly_report",
    "monthly_report",
    "executive_summary",
    "blog_draft",
    "social_summary",
    "linkedin_article_draft",
    "linkedin_post_draft",
    "executive_brief",
]


class ReportRecordV1(Contract):
    schema_version: Literal["v1"] = "v1"
    id: str
    report_type: ReportType
    title: str
    subtitle: str = ""
    body_markdown: str
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    period_start: str = ""
    period_end: str = ""
    created_at: datetime


# --- Operational -----------------------------------------------------------


class AgentRunV1(Contract):
    id: str
    agent: str
    agent_version: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int = 0
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class PipelineResult(Contract):
    """Return value of a full MVP loop execution."""

    collected: int = 0
    normalized: int = 0
    evidence: int = 0
    trends: int = 0
    predictions: int = 0
    recommendations: int = 0
    validations: int = 0
    prediction_results: int = 0
    learning_feedback: int = 0
    reports: int = 0
    errors: list[str] = Field(default_factory=list)
