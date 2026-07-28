"""SHIOS Intelligence API."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import require_api_key
from app.api.routers import (
    dashboard,
    documents,
    health,
    intelligence,
    predictions,
    recommendations,
    reports,
    runs,
    trends,
)
from app.config import settings
from app.db import init_db

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("shios")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.database_url.startswith("sqlite"):
        # Alembic owns the Postgres schema; SQLite is the zero-setup demo path.
        init_db()
    from app.orchestrator.scheduler import start_scheduler, stop_scheduler

    start_scheduler()
    log.info("SHIOS %s ready (env=%s)", settings.app_version, settings.environment)
    yield
    stop_scheduler()


app = FastAPI(
    title="SHIOS Intelligence API",
    version=settings.app_version,
    description=(
        "Strategic Honesty Intelligence Operating System. Collects evidence, computes trends, "
        "publishes forecasts under governance rules, scores those forecasts against reality, "
        "and adjusts its own confidence from the result."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"
protected = [Depends(require_api_key)]

app.include_router(health.router, prefix=API_PREFIX)
app.include_router(documents.router, prefix=API_PREFIX, dependencies=protected)
app.include_router(dashboard.router, prefix=API_PREFIX, dependencies=protected)
app.include_router(predictions.router, prefix=API_PREFIX, dependencies=protected)
app.include_router(recommendations.router, prefix=API_PREFIX, dependencies=protected)
app.include_router(reports.router, prefix=API_PREFIX, dependencies=protected)
app.include_router(runs.router, prefix=API_PREFIX, dependencies=protected)
app.include_router(trends.router, prefix=API_PREFIX, dependencies=protected)
app.include_router(intelligence.router, prefix=API_PREFIX, dependencies=protected)


@app.get("/")
def root() -> dict:
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "api": API_PREFIX,
    }
