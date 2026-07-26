"""Lightweight event bus.

Three things happen on publish:
  1. the event is written to `event_log` (audit / replay),
  2. in-process subscribers are invoked synchronously (this is the orchestration path),
  3. if REDIS_URL is configured, the event is also published to Redis pub/sub so that
     external workers or a future v2 microservice split can consume the same stream.

Redis is *fan-out only*. The system never depends on it for correctness.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.events.types import EventName
from app.models.tables import EventLog

log = logging.getLogger("shios.events")

Handler = Callable[[str, dict[str, Any]], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._redis = None
        self._redis_checked = False

    # -- subscription -------------------------------------------------------
    def subscribe(self, name: EventName | str, handler: Handler) -> None:
        self._handlers[str(name)].append(handler)

    def clear(self) -> None:
        self._handlers.clear()

    # -- publication --------------------------------------------------------
    def publish(self, name: EventName | str, payload: dict[str, Any], session: Session | None = None) -> None:
        name = str(name)
        if session is not None:
            session.add(EventLog(name=name, payload=payload))
            session.flush()
        self._to_redis(name, payload)
        for handler in list(self._handlers.get(name, [])):
            try:
                handler(name, payload)
            except Exception as exc:  # a bad subscriber must not break the producer
                log.exception("event handler failed name=%s error=%s", name, exc)

    # -- redis --------------------------------------------------------------
    def _client(self):
        if self._redis_checked:
            return self._redis
        self._redis_checked = True
        if not settings.redis_url:
            return None
        try:
            import redis  # type: ignore

            self._redis = redis.Redis.from_url(settings.redis_url, socket_timeout=2)
            self._redis.ping()
        except Exception as exc:  # pragma: no cover - infra dependent
            log.warning("redis unavailable, continuing in-process only: %s", exc)
            self._redis = None
        return self._redis

    def _to_redis(self, name: str, payload: dict[str, Any]) -> None:
        client = self._client()
        if client is None:
            return
        try:  # pragma: no cover - infra dependent
            client.publish(settings.event_channel, json.dumps({"event": name, "payload": payload}))
        except Exception as exc:
            log.warning("redis publish failed: %s", exc)


bus = EventBus()
