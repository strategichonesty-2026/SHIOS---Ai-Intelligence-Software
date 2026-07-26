# Development plan

## Milestone 1 — MVP  ✅ delivered

The specification scoped milestone 1 as Gmail integration, LinkedIn extraction, a job database,
a trend dashboard and basic recommendations. All of it is built, plus the parts of milestones 2
and 3 that were needed to make the loop verifiable rather than merely plausible.

| Deliverable | Status | Where |
|---|---|---|
| Source adapters (Gmail, RSS, GitHub, sample) | done | `app/sources/` |
| Job extraction and normalisation | done | `app/agents/extraction.py` |
| Job / company / skill / technology tables | done | `app/models/tables.py` |
| Weekly trend engine | done | `app/agents/trend.py` |
| Recommendations for five audiences | done | `app/agents/recommendation.py` |
| Trend dashboard | done | `frontend/app/trends` |
| Governance rules enforced at write time | done | `app/governance/rules.py` |
| Forecast engine (OLS, immutable, expiring) | done (M2 pulled forward) | `app/agents/prediction.py` |
| Reality check and learning loop | done (M3 pulled forward) | `app/agents/{reality_check,learning}.py` |
| Weekly / executive / LinkedIn reports | done (M2 pulled forward) | `app/agents/reporting.py` |
| Migrations, Docker, CI, 53 tests | done | `alembic/`, `docker-compose.yml`, `.github/` |

Milestones 2 and 3 were partly pulled forward for one reason: without the reality check, the
system cannot tell the truth about itself, and the whole premise collapses into a forecasting
toy. The remaining M2/M3 work below is real but incremental.

## Milestone 2 — Source breadth and reporting depth

**Goal:** stop relying on a single class of signal.

1. **Live source hardening** (1 week) — Gmail OAuth flow with token refresh; per-source rate
   limiters with exponential backoff; a `source_health` table surfacing consecutive failures on
   the dashboard.
2. **Indeed / Levels.fyi / Wellfound adapters** (1–2 weeks) — each behind the existing `Source`
   interface; salary becomes a second metric (`median_salary`) alongside posting counts.
3. **Scheduled report delivery** (3 days) — email and Slack delivery of the weekly report, gated
   on a human approval step for anything leaving the system.
4. **Source weighting** (1 week) — evidence gains a `weight` per source reliability; trends
   become weighted counts. The column already exists.

**Definition of done:** no single source contributes more than 60% of evidence in a period, and
the dashboard shows source mix per trend.

## Milestone 3 — Forecast quality

**Goal:** make confidence mean something precise.

1. **Interval forecasts** (1–2 weeks) — publish a prediction interval, not just a point. Score
   on interval coverage rather than point accuracy. This resolves the known limitation that
   accuracy and confidence are currently different kinds of number.
2. **Seasonality and holdout backtesting** (1 week) — week-of-year effects; a rolling-origin
   backtest harness reporting accuracy by horizon length.
3. **Method registry** (3 days) — `method` is already a column; add naive-drift and
   moving-average baselines and publish whichever wins the backtest per slice, with the losing
   methods still scored for comparison.
4. **Structural break detection** (1 week) — flag when a series breaks its own regime, since
   linear extrapolation is blind to exactly this.

**Definition of done:** interval coverage within 10 points of nominal, and calibration delta
inside ±0.10 for every slice with 20+ scored forecasts.

## Milestone 4 — Multi-domain and enterprise

**Goal:** prove domain independence rather than asserting it.

1. **Second domain end to end** (2 weeks) — technology intelligence as a first-class domain with
   its own taxonomy and metrics, sharing the entire engine unchanged. This is the real test of
   the domain-independence claim.
2. **Knowledge graph** (2 weeks) — replace `knowledge_records` with Neo4j; add capability
   pathing ("what sits between this role and that one"). Nothing downstream reads the current
   table, so this is a swap.
3. **Embeddings and semantic retrieval** (1 week) — populate `normalized_documents.embedding`,
   enable the IVFFlat index that the initial migration already creates, and add near-duplicate
   detection to cut reposting inflation.
4. **Multi-tenant workspaces** (2 weeks) — `users`, `dashboards` tables exist; add row-level
   scoping and per-workspace source configuration.

## Milestone 5 — Intelligence copilot

1. **Conversational query over the TMS** (2 weeks) — natural-language questions answered *only*
   from stored trends, forecasts and evidence, with citations. Refuses rather than speculates.
2. **Decision journal** (1 week) — record what a human decided against each recommendation, then
   score the recommendations themselves the way forecasts are scored.
3. **Scenario modelling** (2 weeks) — "what if this source disappears", "what if demand halves" —
   run against stored series, never invented.
4. **Agent split** (1 week, only if load requires it) — move collection and analysis to Redis-
   backed workers. The event bus already publishes to Redis; producers stay unchanged.

## Sequencing rationale

Breadth of evidence (M2) comes before forecast sophistication (M3) because a better model over a
narrow signal is a more confident wrong answer. Domain independence (M4) comes before the
copilot (M5) because a conversational layer over one domain teaches nothing about whether the
engine generalises.
