from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest

# Configure before any app module imports settings.
_tmpdir = tempfile.mkdtemp(prefix="shios-test-")
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{_tmpdir}/test.db"
os.environ["LLM_PROVIDER"] = "rule"
os.environ["ENABLED_SOURCES"] = "sample_jobs"
os.environ["REDIS_URL"] = ""
os.environ["API_KEY"] = ""
os.environ["SCHEDULER_ENABLED"] = "false"

from sqlalchemy.orm import Session  # noqa: E402

from app.db import SessionLocal, engine, init_db  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.sources.sample_jobs import SampleJobsSource  # noqa: E402


@pytest.fixture(scope="function")
def db() -> Iterator[Session]:
    Base.metadata.drop_all(bind=engine)
    init_db()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    finally:
        session.close()


@pytest.fixture
def sample_source() -> SampleJobsSource:
    return SampleJobsSource(weeks=10, seed=42)


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
