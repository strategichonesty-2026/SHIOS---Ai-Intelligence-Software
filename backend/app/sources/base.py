from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


class SourceError(RuntimeError):
    """Base for source failures."""


class SourceUnavailable(SourceError):
    pass


class RateLimitExceeded(SourceError):
    pass


class ParseError(SourceError):
    pass


@dataclass
class CollectedItem:
    external_id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    observed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    doc_type: str = "other"

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


class Source(ABC):
    """A source knows how to produce raw items. It never touches the database."""

    source_id: str = "base"
    doc_type: str = "other"

    @abstractmethod
    def collect(self, limit: int = 100) -> list[CollectedItem]:
        ...

    def is_configured(self) -> bool:
        return True
