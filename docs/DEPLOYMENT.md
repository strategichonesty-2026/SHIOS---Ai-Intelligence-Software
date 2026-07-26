# Deployment

## 1. Local demo — zero infrastructure

```bash
cd backend
pip install -r requirements-dev.txt
python -m app.cli bootstrap
uvicorn app.main:app --reload
```

SQLite, deterministic sample source, rule-based LLM. No network calls, no keys, no services.
Use this to evaluate the system before provisioning anything.

## 2. Docker Compose — the reference deployment

```bash
cp .env.example .env
# set API_KEY to a strong random value; leave LLM_PROVIDER=rule unless you have a key
docker compose up --build
```

Four services: `postgres` (pgvector/pgvector:pg16), `redis`, `backend`, `frontend`. The backend
entrypoint runs `alembic upgrade head` before serving, and runs one bootstrap loop when
`BOOTSTRAP_ON_START=true`.

Both application images run as non-root (uid 10001). The backend image carries a `HEALTHCHECK`
hitting `/api/v1/health`; compose gates the backend on Postgres and Redis health checks.

```bash
docker compose logs -f backend
docker compose exec backend python -m app.cli status
docker compose exec backend python -m app.cli run --mode full
docker compose down            # add -v to drop the database volume
```

## 3. Railway / Render / Fly

The backend is a single stateless process plus a database; any container platform works.

**Backend service**
- Build: `./backend/Dockerfile`
- Start: `/app/entrypoint.sh` (migrates, then serves on `$PORT`)
- Health check path: `/api/v1/health`
- Attach a PostgreSQL 16 instance with the `vector` extension available

**Frontend service**
- Build: `./frontend/Dockerfile`, build arg `NEXT_PUBLIC_API_BASE_URL=https://api.example.com/api/v1`
- Runtime env: `API_BASE_URL` (internal URL), `SHIOS_API_KEY`

**Required environment**

```
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/shios
REDIS_URL=redis://host:6379/0          # optional
API_KEY=<32+ random bytes>
CORS_ORIGINS=https://dashboard.example.com
ENVIRONMENT=production
SCHEDULER_ENABLED=true
COLLECT_INTERVAL_MINUTES=360
ANALYZE_INTERVAL_MINUTES=720
```

Run the scheduler on exactly one instance. `SCHEDULER_ENABLED=true` on several replicas will
run the loop concurrently; collection is idempotent so this is not corrupting, but it wastes
source rate limits. Either pin the scheduler to a single worker or run it as a separate
`python -m app.cli run` cron job with the API replicas set to `SCHEDULER_ENABLED=false`.

## 4. Migrations

```bash
alembic upgrade head                              # apply
alembic revision --autogenerate -m "description"  # create after model changes
alembic downgrade -1                              # roll back one
alembic current                                   # what is applied
```

The initial migration creates the `vector` extension and types
`normalized_documents.embedding` as `vector(384)` with an IVFFlat cosine index — but only on
PostgreSQL. On SQLite the same migration runs with a JSON column, which is how CI verifies
migrations without a database service.

**Always run migrations against a scratch PostgreSQL instance before a production deploy.** The
PostgreSQL branch is not exercised by the SQLite CI job.

## 5. Secrets

| Variable | Notes |
|---|---|
| `API_KEY` | Required in production. Without it every endpoint is public. |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY` | Only needed if `LLM_PROVIDER` is not `rule` |
| `GITHUB_TOKEN` | Raises the GitHub search rate limit from 10 to 30 requests/minute |
| `GMAIL_CREDENTIALS_JSON` | OAuth user credentials JSON, read-only Gmail scope |
| `DATABASE_URL` | Contains the password — inject as a platform secret, never in the image |

Never bake secrets into images. `.env` is git-ignored; `.env.example` documents the shape only.

## 6. Cutover checklist

1. `alembic upgrade head` against the production database (from a maintenance task, not a replica).
2. `GET /api/v1/health` returns `{"status":"ok","database":"up"}`.
3. `POST /api/v1/runs/pipeline {"mode":"full"}` once, manually, and read the returned counts.
4. `GET /api/v1/ready` shows non-zero trends.
5. Confirm `x-api-key` is enforced: an unauthenticated `GET /api/v1/trends/latest` must return 401.
6. Enable the scheduler on one instance only.
7. Confirm the dashboard renders live figures rather than the empty state.

## 7. Rollback

The backend is stateless, so rolling back the image is safe and immediate. Data rollback needs
more care:

- Migrations are additive in v1; `alembic downgrade -1` drops tables and is destructive. Take a
  database snapshot before any migration in production.
- Published predictions are immutable by design. If a bad forecast batch ships, set
  `status='needs_review'` on the affected rows rather than deleting them — deleting destroys the
  audit trail, and the reality check will otherwise score forecasts that were never intended to
  stand.

## 8. Observability

- Structured logs on stdout at `LOG_LEVEL`.
- `GET /api/v1/runs` — every agent execution with duration, status and error.
- `GET /api/v1/runs/events` — the durable event log.
- `GET /api/v1/predictions/accuracy` — the metric that matters most: if mean accuracy falls or
  the calibration delta drifts, the system is degrading regardless of what uptime says.

Recommended alerts: agent runs with `status='failed'` in the last hour; zero documents collected
in 24 hours; mean accuracy dropping more than 0.15 week over week.
