"""SHIOS v1 physical schema.

Every table carries a `schema_version` where the record is part of a published contract
(RawDocument.v1, TrendRecord.v1, ...). That is what makes contract evolution survivable.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import embedding_type
from app.models.base import Base, IdMixin, TimestampMixin, utcnow

# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------


class RawDocument(Base, IdMixin):
    __tablename__ = "raw_documents"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_raw_source_external"),
        Index("ix_raw_documents_collected_at", "collected_at"),
    )

    schema_version: Mapped[str] = mapped_column(String(16), default="v1")
    source: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str] = mapped_column(String(255))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    doc_metadata: Mapped[dict] = mapped_column(JSON, default=dict)

    normalized = relationship("NormalizedDocument", back_populates="raw", cascade="all, delete-orphan")


class NormalizedDocument(Base, IdMixin):
    __tablename__ = "normalized_documents"
    __table_args__ = (Index("ix_norm_doctype_created", "doc_type", "created_at"),)

    schema_version: Mapped[str] = mapped_column(String(16), default="v1")
    raw_document_id: Mapped[str] = mapped_column(
        ForeignKey("raw_documents.id", ondelete="CASCADE"), index=True
    )
    doc_type: Mapped[str] = mapped_column(String(32), index=True)  # job | article | repo | email
    title: Mapped[str] = mapped_column(String(512))
    body_text: Mapped[str] = mapped_column(Text)
    entities: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(64), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    embedding = mapped_column(embedding_type(), nullable=True)

    raw = relationship("RawDocument", back_populates="normalized")


# ---------------------------------------------------------------------------
# Domain entities
# ---------------------------------------------------------------------------


class Company(Base, IdMixin, TimestampMixin):
    __tablename__ = "companies"
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_metadata: Mapped[dict] = mapped_column(JSON, default=dict)


class Technology(Base, IdMixin, TimestampMixin):
    __tablename__ = "technologies"
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(64), default="general")


class Skill(Base, IdMixin, TimestampMixin):
    __tablename__ = "skills"
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(64), default="general")


class Job(Base, IdMixin, TimestampMixin):
    __tablename__ = "jobs"
    normalized_document_id: Mapped[str] = mapped_column(
        ForeignKey("normalized_documents.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    normalized_role: Mapped[str] = mapped_column(String(128), index=True, default="other")
    seniority: Mapped[str] = mapped_column(String(32), default="unknown")
    location: Mapped[str] = mapped_column(String(255), default="unknown")
    remote_type: Mapped[str] = mapped_column(String(32), default="unknown")
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    technologies: Mapped[list] = mapped_column(JSON, default=list)
    salary_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)


class KnowledgeRecord(Base, IdMixin, TimestampMixin):
    """Minimal subject-predicate-object store. Neo4j replaces this in v2 if it earns its keep."""

    __tablename__ = "knowledge_records"
    __table_args__ = (Index("ix_knowledge_spo", "subject", "predicate", "object"),)

    schema_version: Mapped[str] = mapped_column(String(16), default="v1")
    subject: Mapped[str] = mapped_column(String(255))
    predicate: Mapped[str] = mapped_column(String(64))
    object_: Mapped[str] = mapped_column("object", String(255))
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)


# ---------------------------------------------------------------------------
# Truth maintenance chain
# ---------------------------------------------------------------------------


class Evidence(Base, IdMixin, TimestampMixin):
    __tablename__ = "evidence"
    __table_args__ = (Index("ix_evidence_entity", "entity_type", "entity_name", "period"),)

    normalized_document_id: Mapped[str] = mapped_column(
        ForeignKey("normalized_documents.id", ondelete="CASCADE"), index=True
    )
    entity_type: Mapped[str] = mapped_column(String(32), index=True)  # skill | technology | role | company
    entity_name: Mapped[str] = mapped_column(String(128), index=True)
    period: Mapped[str] = mapped_column(String(16), index=True)
    snippet: Mapped[str] = mapped_column(Text, default="")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String(64), default="unknown")


class Trend(Base, IdMixin):
    __tablename__ = "trends"
    __table_args__ = (
        UniqueConstraint("metric", "entity_type", "entity_name", "period", name="uq_trend_slice"),
        Index("ix_trends_lookup", "metric", "entity_type", "entity_name", "period"),
    )

    schema_version: Mapped[str] = mapped_column(String(16), default="v1")
    metric: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    entity_name: Mapped[str] = mapped_column(String(128), index=True)
    period: Mapped[str] = mapped_column(String(16), index=True)  # ISO week: 2026-W30
    value: Mapped[float] = mapped_column(Float)
    delta: Mapped[float] = mapped_column(Float, default=0.0)
    delta_pct: Mapped[float] = mapped_column(Float, default=0.0)
    direction: Mapped[str] = mapped_column(String(8), default="flat")  # up | down | flat
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Prediction(Base, IdMixin):
    __tablename__ = "predictions"
    __table_args__ = (Index("ix_predictions_status_exp", "status", "expiration_date"),)

    schema_version: Mapped[str] = mapped_column(String(16), default="v1")
    statement: Mapped[str] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(String(32), default="career", index=True)
    metric: Mapped[str] = mapped_column(String(64), default="job_postings_count")
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    entity_name: Mapped[str] = mapped_column(String(128), index=True)
    horizon: Mapped[str] = mapped_column(String(32), default="4w")
    target_period: Mapped[str] = mapped_column(String(16), index=True)
    predicted_value: Mapped[float] = mapped_column(Float)
    lower_bound: Mapped[float | None] = mapped_column(Float, nullable=True)
    upper_bound: Mapped[float | None] = mapped_column(Float, nullable=True)
    interval_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_direction: Mapped[str] = mapped_column(String(8), default="flat")
    confidence: Mapped[float] = mapped_column(Float)
    supporting_evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    trend_ids: Mapped[list] = mapped_column(JSON, default=list)
    assumptions: Mapped[list] = mapped_column(JSON, default=list)
    risks: Mapped[list] = mapped_column(JSON, default=list)
    method: Mapped[str] = mapped_column(String(64), default="ols_interval_v1")
    review_date: Mapped[date] = mapped_column(Date)
    expiration_date: Mapped[date] = mapped_column(Date, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(24), default="published", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class PredictionResult(Base, IdMixin):
    __tablename__ = "prediction_results"
    schema_version: Mapped[str] = mapped_column(String(16), default="v1")
    prediction_id: Mapped[str] = mapped_column(
        ForeignKey("predictions.id", ondelete="CASCADE"), index=True, unique=True
    )
    reality_period: Mapped[str] = mapped_column(String(16))
    actual_value: Mapped[float] = mapped_column(Float)
    predicted_value: Mapped[float] = mapped_column(Float)
    accuracy_score: Mapped[float] = mapped_column(Float)
    deviation: Mapped[float] = mapped_column(Float)
    interval_covered: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    direction_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Recommendation(Base, IdMixin):
    __tablename__ = "recommendations"
    __table_args__ = (Index("ix_recs_audience_created", "audience_type", "created_at"),)

    schema_version: Mapped[str] = mapped_column(String(16), default="v1")
    audience_type: Mapped[str] = mapped_column(String(32), index=True)
    domain: Mapped[str] = mapped_column(String(32), default="career", index=True)
    recommendation_text: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text, default="")
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    trend_ids: Mapped[list] = mapped_column(JSON, default=list)
    prediction_id: Mapped[str | None] = mapped_column(
        ForeignKey("predictions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    confidence: Mapped[float] = mapped_column(Float)
    alternative_scenarios: Mapped[list] = mapped_column(JSON, default=list)
    risks: Mapped[list] = mapped_column(JSON, default=list)
    expected_outcomes: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ValidationResult(Base, IdMixin):
    __tablename__ = "validation_results"
    __table_args__ = (Index("ix_validation_target", "target_type", "target_id"),)

    schema_version: Mapped[str] = mapped_column(String(16), default="v1")
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(36))
    is_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    issues: Mapped[list] = mapped_column(JSON, default=list)
    missing_evidence: Mapped[list] = mapped_column(JSON, default=list)
    contradictory_evidence: Mapped[list] = mapped_column(JSON, default=list)
    unknowns_noted: Mapped[list] = mapped_column(JSON, default=list)
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class LearningFeedback(Base, IdMixin):
    __tablename__ = "learning_feedback"
    schema_version: Mapped[str] = mapped_column(String(16), default="v1")
    prediction_id: Mapped[str] = mapped_column(ForeignKey("predictions.id", ondelete="CASCADE"), index=True)
    prediction_result_id: Mapped[str] = mapped_column(String(36), index=True)
    metric: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    accuracy_score: Mapped[float] = mapped_column(Float)
    false_positive: Mapped[bool] = mapped_column(Boolean, default=False)
    false_negative: Mapped[bool] = mapped_column(Boolean, default=False)
    coverage_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    confidence_calibration_delta: Mapped[float] = mapped_column(Float, default=0.0)
    signal_quality_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Report(Base, IdMixin):
    __tablename__ = "reports"
    schema_version: Mapped[str] = mapped_column(String(16), default="v1")
    report_type: Mapped[str] = mapped_column(String(48), index=True)
    title: Mapped[str] = mapped_column(String(255))
    subtitle: Mapped[str] = mapped_column(String(255), default="")
    body_markdown: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    period_start: Mapped[str] = mapped_column(String(16), default="")
    period_end: Mapped[str] = mapped_column(String(16), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


# ---------------------------------------------------------------------------
# Platform
# ---------------------------------------------------------------------------


class User(Base, IdMixin, TimestampMixin):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    role: Mapped[str] = mapped_column(String(32), default="viewer")  # viewer | analyst | admin
    api_key_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Dashboard(Base, IdMixin, TimestampMixin):
    __tablename__ = "dashboards"
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(128))
    config: Mapped[dict] = mapped_column(JSON, default=dict)


class AgentRun(Base, IdMixin):
    """Governance rule: every agent logs every decision with timestamp + version."""

    __tablename__ = "agent_runs"
    agent: Mapped[str] = mapped_column(String(64), index=True)
    agent_version: Mapped[str] = mapped_column(String(16), default="1.0.0")
    status: Mapped[str] = mapped_column(String(16), default="running", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)
    outputs: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class EventLog(Base, IdMixin):
    __tablename__ = "event_log"
    name: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
