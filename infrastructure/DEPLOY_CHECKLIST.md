# SHIOS Production Deployment Checklist

## Option A — Railway (recommended, fastest)

Railway detects the Dockerfiles automatically. Two services from one repo.

### Prerequisites
- Railway account at https://railway.app
- GitHub repo connected to Railway
- Python 3 on your Mac (to generate the API key)

### Step 1 — Generate a strong API key (do this first)
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```
Save this value — you'll use it in both services.

### Step 2 — Create a new Railway project
1. https://railway.app → New Project → Deploy from GitHub repo
2. Select `SHIOS---Ai-Intelligence-Software`
3. When asked which folder: choose `backend`

### Step 3 — Add PostgreSQL (pgvector)
In your Railway project:
1. New Service → Database → Add PostgreSQL
2. Railway sets `DATABASE_URL` automatically on the backend service
3. Connect the Postgres service to the backend service

> **Important:** The standard Railway Postgres image does not include pgvector.
> After the database is created, open the Railway Postgres shell and run:
> ```sql
> CREATE EXTENSION IF NOT EXISTS vector;
> ```
> Or use the pgvector image: in Railway Postgres settings, change the image to
> `pgvector/pgvector:pg16`.

### Step 4 — Add Redis
1. New Service → Database → Add Redis
2. Railway sets `REDIS_URL` automatically

### Step 5 — Set backend environment variables
In the backend service → Variables tab, add:

```
ENVIRONMENT=production
LOG_LEVEL=INFO
API_KEY=<your generated key from Step 1>
CORS_ORIGINS=https://<your-frontend-domain>.up.railway.app
LLM_PROVIDER=rule
ENABLED_SOURCES=sample_jobs,rss,github
RSS_FEEDS=https://hnrss.org/frontpage
GITHUB_TOPICS=agile,project-management,llm
BOOTSTRAP_ON_START=true
SCHEDULER_ENABLED=true
COLLECT_INTERVAL_MINUTES=360
ANALYZE_INTERVAL_MINUTES=720
MIN_EVIDENCE_PER_RECOMMENDATION=2
MAX_PREDICTION_REVIEW_DAYS=90
MIN_PERIODS_FOR_PREDICTION=3
```

Leave blank for now (add later when needed):
```
ANTHROPIC_API_KEY=
GITHUB_TOKEN=
GMAIL_CREDENTIALS_JSON=
```

### Step 6 — Deploy the frontend
1. In the same Railway project → New Service → GitHub repo
2. Select the same repo, root directory: `frontend`
3. Set variables:

```
NEXT_PUBLIC_API_BASE_URL=https://<your-backend-domain>.up.railway.app/api/v1
API_BASE_URL=https://<your-backend-domain>.up.railway.app/api/v1
SHIOS_API_KEY=<same API_KEY as backend>
PORT=3000
```

### Step 7 — Verify deployment
```bash
# Replace with your actual Railway backend URL
BACKEND=https://your-backend.up.railway.app

# Health check
curl $BACKEND/api/v1/health

# Confirm data was collected
curl -H "x-api-key: YOUR_API_KEY" $BACKEND/api/v1/ready

# Check predictions exist
curl -H "x-api-key: YOUR_API_KEY" $BACKEND/api/v1/predictions?limit=3
```

Expected health response:
```json
{
  "status": "ok",
  "database": "up",
  "environment": "production",
  "source_health": { "sample_jobs": { "status": "healthy" } }
}
```

### Step 8 — Update CORS after frontend is live
Once you know the frontend URL, update `CORS_ORIGINS` on the backend to match exactly.

---

## Option B — Docker Compose on a VPS (DigitalOcean, Hetzner, etc.)

Cheapest option if you have a $6/month droplet.

```bash
# On the server
git clone https://github.com/strategichonesty-2026/SHIOS---Ai-Intelligence-Software.git shios
cd shios
cp .env.example .env
nano .env   # fill in API_KEY, set ENVIRONMENT=production, CORS_ORIGINS
docker compose up --build -d
docker compose logs -f backend
```

For HTTPS, put Caddy or nginx in front:
```bash
# Caddy example (simplest)
apt install caddy
# /etc/caddy/Caddyfile:
# your-domain.com {
#   reverse_proxy localhost:3000
# }
# api.your-domain.com {
#   reverse_proxy localhost:8000
# }
```

---

## Option C — Render

Same as Railway but different UI:
1. New Web Service → Connect GitHub repo
2. Root directory: `backend`, Runtime: Docker
3. Add environment variables from Step 5 above
4. Add a Render PostgreSQL database (standard plan has pgvector)
5. Repeat for frontend with root directory: `frontend`

---

## Post-deployment operations

### Run a manual intelligence loop
```bash
curl -X POST \
  -H "x-api-key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"mode": "full"}' \
  https://your-backend.up.railway.app/api/v1/runs/pipeline
```

### Check agent run history
```bash
curl -H "x-api-key: YOUR_API_KEY" \
  https://your-backend.up.railway.app/api/v1/runs?limit=10
```

### Check forecast accuracy
```bash
curl -H "x-api-key: YOUR_API_KEY" \
  https://your-backend.up.railway.app/api/v1/predictions/accuracy
```

### Reset and re-bootstrap (careful — destroys all data)
```bash
# Railway: open backend shell
python -m app.cli reset --yes
python -m app.cli bootstrap
```

---

## Environment variable reference

| Variable | Required | Default | Notes |
|---|---|---|---|
| `DATABASE_URL` | ✅ | — | Set by Railway/Render automatically |
| `API_KEY` | ✅ | — | Generate with `secrets.token_hex(32)` |
| `CORS_ORIGINS` | ✅ | — | Your frontend URL, no trailing slash |
| `ENVIRONMENT` | ✅ | development | Set to `production` |
| `REDIS_URL` | ⚠️ | — | Optional but recommended; events still work without it |
| `LLM_PROVIDER` | — | rule | `rule` needs no key; `anthropic` needs `ANTHROPIC_API_KEY` |
| `ENABLED_SOURCES` | — | sample_jobs | Add `rss,github` for real signals |
| `BOOTSTRAP_ON_START` | — | false | Set `true` for first deploy only |
| `SCHEDULER_ENABLED` | — | false | Set `true` on exactly ONE instance |
| `GITHUB_TOKEN` | — | — | Raises GitHub rate limit from 10→30 req/min |
| `ANTHROPIC_API_KEY` | — | — | Only needed if `LLM_PROVIDER=anthropic` |

---

## Security checklist before going live

- [ ] `API_KEY` is set to a strong random value (32+ hex chars)
- [ ] `ENVIRONMENT=production`
- [ ] `CORS_ORIGINS` is set to your exact frontend URL
- [ ] `BOOTSTRAP_ON_START` is `false` after first deploy
- [ ] `SCHEDULER_ENABLED=true` on exactly one backend instance
- [ ] Database password is not the default `shios/shios`
- [ ] No real credentials in the GitHub repo (check with `git log`)
- [ ] Frontend `SHIOS_API_KEY` matches backend `API_KEY`
