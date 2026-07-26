from __future__ import annotations

from enum import StrEnum


class EventName(StrEnum):
    DOCUMENT_COLLECTED = "document.collected"
    DOCUMENT_COLLECTION_FAILED = "document.collection_failed"
    DOCUMENT_NORMALIZED = "document.normalized"
    KNOWLEDGE_UPDATED = "knowledge.updated"
    TREND_UPDATED = "trend.updated"
    PREDICTION_PUBLISHED = "prediction.published"
    PREDICTION_EVALUATED = "prediction.evaluated"
    RECOMMENDATION_CREATED = "recommendation.created"
    RECOMMENDATION_VALIDATED = "recommendation.validated"
    REPORT_GENERATED = "report.generated"
    LEARNING_RECORDED = "learning.recorded"
