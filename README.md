# SHIOS — Strategic Honesty Intelligence Operating System

> **On macOS?** Read [docs/SETUP_MACOS.md](docs/SETUP_MACOS.md) before running anything.
> It covers the Python-version trap (`str | None` TypeError), the iCloud duplicate-file
> bug, and the exact virtualenv setup — skipping it is the single most common source of
> wasted time on this project.

**v1.0** — an AI-native intelligence loop that collects evidence, computes trends, publishes
forecasts under enforced governance rules, scores those forecasts against what actually
happened, and lowers its own confidence when it was wrong.

The organising idea is in the name. Any system can publish a prediction. This one publishes
the prediction, the evidence beneath it, the review date, and — later — the score. When it
does not know something, saying so is a first-class output rather than a failure mode.

```
Collect → Extract → Store → Trend → Predict → Recommend → Validate
                                                             ↓
                       Learn ← Compare ← Monitor reality ← Publish
```

---

## Quickstart (no services required)

```bash
cd backend
pip install -r requirements-dev.txt
python -m app.cli bootstrap          # creates SQLite schema, runs one full loop
uvicorn app.main:app --reload        # http://localhost:8000/docs
```

In a second terminal:

```bash
cd frontend
npm install
API_BASE_URL=http://localhost:8000/api/v1 npm run dev   # http://localhost:3000
```

`bootstrap` produces a complete, closed loop on the first run:

```json
{ "collected": 492, "normalized": 492, "evidence": 3244, "trends": 360,
  "predictions": 100, "recommendations": 25, "validations": 50,
  "prediction_results": 75, "learning_feedback": 75, "reports": 4, "errors": [] }
```

## Full stack (PostgreSQL + pgvector + Redis)

```bash
cp .env.example .env
docker compose up --build
```

| Service | URL |
|---|---|
| Dashboard | http://localhost:3000 |
| API + OpenAPI docs | http://localhost:8000/docs |
| PostgreSQL | localhost:5432 (`shios` / `shios`) |
| Redis | localhost:6379 |

## Make targets

```
make install    install backend dev dependencies
make bootstrap  create the schema and run one full loop (SQLite)
make run        run one full loop against the configured database
make api        serve the API with reload
make frontend   run the dashboard in dev mode
make test       run the test suite
make lint       ruff + mypy
make migrate    alembic upgrade head
make up / down  start / stop the docker stack
```

## Documentation

| Document | What it covers |
|---|---|
| [docs/ANALYSIS.md](docs/ANALYSIS.md) | Specification analysis, gaps found, decisions taken |
| [docs/SETUP_MACOS.md](docs/SETUP_MACOS.md) | macOS Python-version and iCloud-sync setup traps |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, data flow, contracts, governance, TMS |
| [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md) | What v1 delivered, and milestones 2–5 |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Docker, Railway, secrets, migrations, rollback |
| [docs/TESTING.md](docs/TESTING.md) | Test plan, cases, coverage, how to extend |
| [docs/MAINTENANCE.md](docs/MAINTENANCE.md) | Operations, tuning, scaling, known limitations |

## Repository layout

```
shios/
├── backend/                FastAPI service, agents, governance, migrations
│   ├── app/
│   │   ├── agents/         the ten agents from the specification
│   │   ├── api/            HTTP layer (routers, auth, pagination)
│   │   ├── events/         event names and the in-process bus
│   │   ├── governance/     rules as executable code
│   │   ├── llm/            provider abstraction (rule, Anthropic, OpenAI, Google)
│   │   ├── models/         SQLAlchemy schema
│   │   ├── orchestrator/   loop runners and scheduler
│   │   ├── schemas/        versioned Pydantic contracts
│   │   ├── services/       periods, statistics, calibration, taxonomy
│   │   └── sources/        RSS, GitHub, Gmail, deterministic sample source
│   ├── alembic/            migrations
│   └── tests/              53 tests, 87% statement coverage
├── frontend/               Next.js 14 dashboard (server components, no client fetching)
├── docs/                   architecture, deployment, testing, maintenance
├── .github/workflows/      CI: lint, migrate, test, build
└── docker-compose.yml
```

## Core API

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/health`, `/ready` | liveness and data readiness |
| `GET /api/v1/agents` | every agent's governance answers |
| `POST /api/v1/runs/pipeline` | run the `full` or `mvp` loop |
| `POST /api/v1/runs/agents/{name}` | run a single agent |
| `GET /api/v1/trends/latest`, `/trends/series/{type}/{name}` | trend data |
| `GET /api/v1/trends/{id}/evidence` | the documents behind a number |
| `GET /api/v1/predictions`, `/predictions/accuracy` | forecast register and track record |
| `GET /api/v1/recommendations` | audience-specific guidance |
| `POST /api/v1/recommendations/{id}/decision` | human approval step |
| `GET /api/v1/reports/{id}/export.md` | markdown export |
| `GET /api/v1/dashboard/*` | overview, career, technology, explorer, history |

Set `API_KEY` to require an `x-api-key` header on everything except `/health`.

## Design commitments

1. **No number without evidence.** A recommendation needs at least two evidence ids and a
   trend or forecast reference. Enforced in `governance/rules.py`, not by convention.
2. **No forecast without an expiry.** Review within 90 days, expiration after review, reality
   check afterward. Unenforceable forecasts are rejected at publication time.
3. **Statistics before models.** Trends are counts. Forecasts are ordinary least squares. The
   language model writes prose, never numbers.
4. **Runs offline by default.** `LLM_PROVIDER=rule` is deterministic and free, which is what
   makes the governance tests meaningful.
5. **Failures are isolated.** One dead source never stops the loop; it emits
   `document.collection_failed` and the run continues on the sources that worked.
# Last updated: Sun Jul 26 09:33:12 CDT 2026
