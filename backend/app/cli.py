"""SHIOS command line.

    python -m app.cli bootstrap     create schema and run one full loop
    python -m app.cli run --mode full
    python -m app.cli agent trend
    python -m app.cli status
    python -m app.cli reset --yes
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from sqlalchemy import func, select

from app.config import settings
from app.db import engine, init_db, session_scope
from app.models.base import Base
from app.models.tables import (
    Evidence,
    LearningFeedback,
    NormalizedDocument,
    Prediction,
    PredictionResult,
    RawDocument,
    Recommendation,
    Report,
    Trend,
)
from app.orchestrator.orchestrator import run_agent, run_full_loop, run_mvp_loop

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger("shios.cli")


def cmd_bootstrap(args: argparse.Namespace) -> int:
    init_db()
    with session_scope() as session:
        result = run_full_loop(session, limit=args.limit, horizon_weeks=args.horizon)
    print(json.dumps(result.model_dump(), indent=2))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    runner = run_full_loop if args.mode == "full" else run_mvp_loop
    with session_scope() as session:
        result = runner(session, limit=args.limit, horizon_weeks=args.horizon)
    print(json.dumps(result.model_dump(), indent=2))
    return 0


def cmd_agent(args: argparse.Namespace) -> int:
    payload = json.loads(args.payload) if args.payload else {}
    with session_scope() as session:
        output = run_agent(session, args.name, **payload)
    print(json.dumps(output, indent=2, default=str))
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    with session_scope() as session:
        counts = {
            model.__tablename__: session.scalar(select(func.count()).select_from(model)) or 0
            for model in (
                RawDocument,
                NormalizedDocument,
                Evidence,
                Trend,
                Prediction,
                PredictionResult,
                Recommendation,
                LearningFeedback,
                Report,
            )
        }
        latest = session.scalar(select(func.max(Trend.period)))
    print(json.dumps({"database": settings.database_url, "latest_period": latest, "counts": counts}, indent=2))
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    if not args.yes:
        print("Refusing to drop data without --yes.")
        return 1
    Base.metadata.drop_all(bind=engine)
    init_db()
    print("Schema reset.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shios")
    sub = parser.add_subparsers(dest="command", required=True)

    bootstrap = sub.add_parser("bootstrap", help="create schema and run one full loop")
    bootstrap.add_argument("--limit", type=int, default=500)
    bootstrap.add_argument("--horizon", type=int, default=4)
    bootstrap.set_defaults(func=cmd_bootstrap)

    run = sub.add_parser("run", help="run the intelligence loop")
    run.add_argument("--mode", choices=["full", "mvp"], default="full")
    run.add_argument("--limit", type=int, default=500)
    run.add_argument("--horizon", type=int, default=4)
    run.set_defaults(func=cmd_run)

    agent = sub.add_parser("agent", help="run a single agent")
    agent.add_argument("name")
    agent.add_argument("--payload", default="")
    agent.set_defaults(func=cmd_agent)

    status = sub.add_parser("status", help="print row counts")
    status.set_defaults(func=cmd_status)

    reset = sub.add_parser("reset", help="drop and recreate the schema")
    reset.add_argument("--yes", action="store_true")
    reset.set_defaults(func=cmd_reset)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
