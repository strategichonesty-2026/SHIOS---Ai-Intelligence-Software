# Architecture

## 1. Shape of the system

One backend process, one database, one dashboard. Agents are modules, not services. This is a
deliberate reading of the specification's non-goals: no microservices, no distributed systems,
no premature scaling.

```
┌──────────────────────────────────────────────────────────┐
│  Next.js 14 dashboard  (server components, no client fetch)│
└───────────────────────────┬──────────────────────────────┘
                            │ HTTP, x-api-key
┌───────────────────────────▼──────────────────────────────┐
│  FastAPI  /api/v1                                         │
│  health · documents · trends · predictions ·              │
│  recommendations · reports · dashboard · runs             │
├──────────────────────────────────────────────────────────┤
│  Orchestrator            run_mvp_loop / run_full_loop      │
│  Event bus               in-process dispatch + event_log   │
├──────────────────────────────────────────────────────────┤
│  Agents (modules)                                          │
│  collector · extraction · knowledge · trend · prediction  │
│  recommendation · validator · reality_check · learning ·  │
│  reporting                                                 │
├──────────────────────────────────────────────────────────┤
│  Services      periods · stats · calibration · taxonomy    │
│  Governance    rules as executable code                    │
│  LLM           rule (default) | anthropic | openai | google│
├──────────────────────────────────────────────────────────┤
│  SQLAlchemy 2.0 ORM · Alembic                              │
│  PostgreSQL + pgvector   (SQLite for tests and local demo) │
│  Redis (optional fan-out only)                             │
└──────────────────────────────────────────────────────────┘
        ▲
        │ sources: sample_jobs · rss · github · gmail
```

## 2. The loop

`orchestrator/orchestrator.py` exposes two runners.

**MVP loop** — the spec's §4 minimum:

```
Collector → Extraction → Trend → Prediction → Recommendation → Validator
```

**Full loop** — the MVP loop plus:

```
… → Knowledge → Prediction(backtest ×3) → RealityCheck → Learning → Reporting
```

The backtest step is what closes the cycle on run one. Anchoring forecasts at
`latest − horizon − {2,3,4}` weeks means their target periods already have observed actuals, so
scoring and calibration have real material immediately rather than in a month's time.

## 3. Agent contracts

Every agent inherits `agents/base.Agent` and implements one method, `execute(session, **kwargs)
-> dict`. The base class wraps it with an `AgentRun` record capturing version, duration, inputs,
outputs and errors — the specification's requirement that agents log decisions with timestamp
and version, made structural rather than optional.

Each agent also answers the six governance questions from §16 as class attributes, exposed live
at `GET /api/v1/agents`:

| Agent | Supports which decision | Confidence method |
|---|---|---|
| `collector` | What entered the system, from where | n/a — collection is factual |
| `extraction` | What entities each document mentions | dictionary match is exact |
| `knowledge` | Which capabilities travel together | co-occurrence over entity frequency |
| `trend` | What is gaining or losing demand | none — counts, not estimates |
| `prediction` | Where demand is heading | R² × history × volatility × calibration |
| `recommendation` | What each audience should do | inherited, discounted 10% per step |
| `strategic_honesty_validator` | Is this safe to act on | binary validity + explicit unknowns |
| `reality_check` | Was the forecast right | n/a — measures rather than estimates |
| `learning` | How much to trust the next forecast | accuracy − claimed confidence |
| `reporting` | What a human needs to read | restates source confidence only |

## 4. Data contracts

`schemas/contracts.py` holds versioned Pydantic models — `RawDocumentV1`,
`NormalizedDocumentV1`, `TrendRecordV1`, `PredictionRecordV1`, `RecommendationRecordV1`,
`ValidationResultV1`, `PredictionResultV1`, `LearningFeedbackV1`, `ReportRecordV1`.

These are the only legal way data moves between agents. If a field is not in the contract, an
agent may not depend on it. Every persisted row carries `schema_version`, so a v2 contract can
coexist with v1 rows rather than requiring a big-bang migration.

Tests validate live database rows against the contracts, which catches drift between the ORM
and the published interface.

## 5. Truth Maintenance System

The chain is enforced by foreign keys where possible and by the validator where the reference
is a JSON id list.

```
RawDocument ──1:N──▶ NormalizedDocument ──1:N──▶ Evidence
                                                    │
                                          (counted per week)
                                                    ▼
                                                  Trend
                                                    │
                                              (OLS fit over)
                                                    ▼
                                               Prediction ──▶ Recommendation
                                                    │
                                        (compared to actual)
                                                    ▼
                                            PredictionResult
                                                    │
                                                    ▼
                                            LearningFeedback
                                                    │
                                      (calibrates next Prediction)
```

Invariants, each covered by a test:

- Every `Prediction.trend_ids` resolves to live `Trend` rows.
- Every `Prediction.supporting_evidence_ids` resolves to live `Evidence` rows.
- Every `Recommendation` references at least one trend or a prediction, plus ≥2 evidence ids.
- Every `PredictionResult` references a real `Prediction`.
- Every `LearningFeedback` references both a `Prediction` and a `PredictionResult`.

`StrategicHonestyValidator` re-checks these on every pass and records dangling references as
`missing_evidence` on a `ValidationResult` rather than failing silently.

## 6. Governance as code

`governance/rules.py` is a set of pure functions returning a `GovernanceReport` of findings,
each `hard` or `soft`.

| Rule | Severity | Where enforced |
|---|---|---|
| `MIN_EVIDENCE` (≥2 for recommendations) | hard | recommendation agent, validator |
| `CONFIDENCE_RANGE` (0.0–1.0) | hard | prediction and recommendation agents |
| `REVIEW_WINDOW` (≤90 days) | hard | prediction agent |
| `EXPIRATION_REQUIRED` / `EXPIRATION_ORDER` | hard | prediction agent |
| `TRACEABILITY` (trend or prediction reference) | hard | recommendation agent |
| `DANGLING_REFERENCE` | hard | validator |
| `SUBSTANCE` (text long enough to act on) | hard | recommendation agent |
| `SAMPLE_SIZE` (<3 periods) | soft | prediction agent → surfaced as a risk |
| `CONFIDENCE_FLOOR` | soft | prediction agent |
| `CONTRADICTORY_EVIDENCE` | soft | validator |

`enforce()` raises `GovernanceError` on any hard failure, so a non-compliant artefact cannot be
written. Soft findings are attached to the artefact as risks or issues — the system is allowed
to publish something provisional, but not to publish it quietly.

## 7. Event model

```
document.collected          document.collection_failed
document.normalized         knowledge.updated
trend.updated               prediction.published
prediction.evaluated        recommendation.created
recommendation.validated    report.generated
learning.recorded
```

`events/bus.py` does three things on publish: writes to `event_log` (audit and replay), invokes
in-process subscribers synchronously, and — if `REDIS_URL` is set — publishes to Redis pub/sub.

Redis is fan-out only. A failed Redis publish logs a warning and the loop continues. Correctness
never depends on it, which is what allows a future v2 to split agents into workers without
rewriting the producers.

## 8. Storage

Nineteen tables. Highlights:

- `raw_documents` — unique on `(source, external_id)`, plus a SHA-256 content hash
- `normalized_documents` — extracted entities as JSON, `embedding` as `vector(384)` on
  PostgreSQL and JSON elsewhere
- `evidence` — the hinge of the TMS, indexed on `(entity_type, entity_name, period)`
- `trends` — unique on `(metric, entity_type, entity_name, period)`, so recomputation is idempotent
- `predictions` — immutable after publication; a revised forecast is a new row
- `agent_runs`, `event_log` — the audit surface

The `embedding_type()` helper in `db.py` returns a pgvector column on PostgreSQL and JSON
elsewhere via `with_variant`, which is what lets the identical ORM model run under SQLite in CI
and PostgreSQL in production.

## 9. Model abstraction

Three operations, defined in `llm/base.py`: `extract_entities`, `summarize`,
`generate_recommendation`. Anything an agent wants from a model must fit one of them, which
keeps prompts short and providers swappable.

`RuleBasedProvider` is the default and is not a stub — it is a fully deterministic
implementation covering all three operations. That property is what makes the governance tests
meaningful: an assertion about a recommendation is stable across runs. Hosted providers
(Anthropic, OpenAI, Google) improve wording and recall, and degrade back to the rule provider on
any error, with the degradation logged.

Numbers never come from a model. Trends are counts; forecasts are OLS. The model writes prose
around figures that were computed elsewhere.

## 10. Frontend

Next.js 14 App Router, all pages as React Server Components. Consequences:

- The browser never holds an API key; `SHIOS_API_KEY` stays server-side.
- No client-side data fetching library, no loading spinners, no hydration waterfall.
- Charts are hand-drawn inline SVG (`Sparkline`), avoiding a charting dependency entirely.

Visual direction: an instrument panel rather than a marketing page. Cool graphite paper, a
single evidence-teal for anything the system can prove, amber for anything provisional, rose
reserved for governance failures. Space Grotesk for display, Inter for body, JetBrains Mono for
every number.

The signature element is the **evidence ledger** — a hairline strip of ticks, one per evidence
record behind a claim, with the exact count beside it. It appears on every trend, forecast and
recommendation, and it encodes the one thing the interface most needs to communicate: how much
the system actually has to stand on. Where the count is zero, it says "no evidence" in the
failure colour.
