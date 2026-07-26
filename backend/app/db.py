"""Database engine and session handling.

Design decision: SQLAlchemy 2.0 *synchronous* ORM. FastAPI runs sync path operations in a
threadpool, which gives us the same throughput profile as async for a database-bound
workload with far fewer failure modes (no event-loop-bound sessions leaking between agents).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import JSON, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.types import TypeEngine

from app.config import settings


def _make_engine() -> Engine:
    kwargs: dict = {"echo": settings.db_echo, "future": True, "pool_pre_ping": True}
    if settings.database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        kwargs.pop("pool_pre_ping")
    return create_engine(settings.database_url, **kwargs)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):  # pragma: no cover - driver glue
    if "sqlite3" in type(dbapi_connection).__module__:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def embedding_type() -> TypeEngine:
    """pgvector column on PostgreSQL, JSON array everywhere else.

    Keeps the exact same ORM model usable in tests (SQLite) and production (Postgres).
    """
    try:
        from pgvector.sqlalchemy import Vector  # type: ignore

        return JSON().with_variant(Vector(settings.embedding_dim), "postgresql")
    except Exception:  # pragma: no cover - pgvector not installed locally
        return JSON()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope used by agents and scripts."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    """Create tables directly. Alembic owns production schema; this is for tests/demo."""
    from app.models import tables  # noqa: F401
    from app.models.base import Base

    Base.metadata.create_all(bind=engine)
