"""Agent base.

Spec section 16 requires every agent to answer six governance questions. Those answers are
not documentation that drifts — they are class attributes, exposed at
`GET /api/v1/agents`, so the running system can always state what each agent is for.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.tables import AgentRun

log = logging.getLogger("shios.agents")


class Agent(ABC):
    name: str = "agent"
    version: str = "1.0.0"

    # --- governance specification (section 16) ---
    supports_decision: str = ""
    requires_evidence: str = ""
    confidence_method: str = ""
    correctness_check: str = ""
    success_metric: str = ""
    human_review: str = "none"

    @abstractmethod
    def execute(self, session: Session, **kwargs: Any) -> dict[str, Any]:
        """Do the work. Return a JSON-serialisable summary of what was produced."""

    def run(self, session: Session, **kwargs: Any) -> dict[str, Any]:
        run = AgentRun(
            agent=self.name,
            agent_version=self.version,
            status="running",
            inputs={k: _safe(v) for k, v in kwargs.items()},
        )
        session.add(run)
        session.flush()
        started = time.perf_counter()
        try:
            outputs = self.execute(session, **kwargs)
            run.status = "success"
            run.outputs = outputs
            return outputs
        except Exception as exc:
            run.status = "failed"
            run.error = f"{type(exc).__name__}: {exc}"
            log.exception("agent failed name=%s", self.name)
            raise
        finally:
            run.finished_at = datetime.now(UTC)
            run.duration_ms = int((time.perf_counter() - started) * 1000)
            session.flush()

    @classmethod
    def governance(cls) -> dict[str, str]:
        return {
            "agent": cls.name,
            "version": cls.version,
            "supports_decision": cls.supports_decision,
            "requires_evidence": cls.requires_evidence,
            "confidence_method": cls.confidence_method,
            "correctness_check": cls.correctness_check,
            "success_metric": cls.success_metric,
            "human_review": cls.human_review,
        }


def _safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value][:50]
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in list(value.items())[:50]}
    return str(value)[:500]
