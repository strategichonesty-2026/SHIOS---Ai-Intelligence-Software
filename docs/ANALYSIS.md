# Specification analysis

An honest reading of the SHIOS v1.0 handoff document: what it specified well, where it left
gaps, and what was decided in each case. Every decision here was made without asking, per the
brief; each one is reversible and the reasoning is recorded so a future maintainer can
disagree with evidence rather than guesswork.

---

## 1. What the specification got right

The document is unusually strong in three places, and the build leans on all three.

**Agent contracts (§5).** Ten agents with explicit inputs, outputs and errors. This is the
single most useful part of the spec: it made the Pydantic contract layer nearly mechanical to
derive, and it means agents can be replaced independently.

**Governance as code (§9).** Most specifications describe governance as policy. This one lists
rules that can be executed: two evidence ids minimum, confidence in 0.0–1.0, review within 90
days, expiration mandatory. Rules that can be executed can be tested, and rules that can be
tested actually hold.

**Truth Maintenance System (§10).** The chain `RawDocument → NormalizedDocument → Evidence →
Trend → Prediction → PredictionResult → LearningFeedback` is the spine of the system. It is
implemented literally, and a test asserts there are no dangling references anywhere in it.

## 2. Ambiguities found, and how they were resolved

### 2.1 "Trend" was never defined as a metric

§5.4 specifies the *shape* of a `TrendRecord` but not what is being counted.

**Decision.** The v1 metric is `job_postings_count`: the number of distinct collected documents
mentioning an entity, per ISO week. Weeks are the smallest unit that smooths posting noise
while still fitting several observations inside the 90-day governance window. The metric field
exists on every record, so adding `median_salary` or `github_star_velocity` later is additive
rather than a migration.

### 2.2 "Simple forecasts" was left open

**Decision.** `ols_linear_v1`: ordinary least squares over the weekly series, extrapolated to
the target period. With 8–12 observations a linear fit is the honest ceiling on what the data
supports, and every published number stays defensible in one sentence. ARIMA or a gradient
model would produce better-looking numbers and worse explanations.

### 2.3 Confidence was required but never specified

§5.5 says confidence must be evidence-based. It does not say how to compute it.

**Decision.** `confidence = (0.25 + 0.55·R²) × history_factor × volatility_factor × calibration`,
clamped to 0.05–0.95, where `history_factor` scales with observed periods (capped at 8) and
`volatility_factor` is `1 − coefficient_of_variation`. The calibration term is the learned
correction described in §2.6 below. All four terms are inspectable in
`agents/prediction.py::_confidence`.

### 2.4 The learning loop had no mechanism

§5.9 defines `LearningFeedback` fields but not what consumes them.

**Decision.** `confidence_calibration_delta = accuracy_score − claimed_confidence`, averaged per
`(metric, entity_type)` slice over the last 50 results, applied as a multiplier clamped to
±0.35 on the next forecast in that slice. It is deliberately legible: anyone can audit why
confidence moved. See `services/calibration.py`.

### 2.5 Cold start would have made the system silent for a month

A trend engine with no history has nothing honest to say, and a forecast published today
cannot be scored for weeks. Taken literally, a fresh install would show empty dashboards and an
empty accuracy record until enough real time had passed — which makes the system impossible to
evaluate, demo, or test.

**Decision, two parts.**

1. A deterministic `sample_jobs` source generates a reproducible 12-week posting history. It is
   seeded, labelled `synthetic: true` in every record, and disabled by removing it from
   `ENABLED_SOURCES`. It exists so the loop is demonstrable and assertable on run one.
2. The full loop publishes *backtested* forecasts alongside live ones, anchored at
   `latest − horizon − {2,3,4}` weeks. Their target periods already have observed actuals, so
   Reality Check and Learning have real material immediately. Without this the loop would only
   *look* closed for the first month.

### 2.6 The Knowledge Agent was permitted to be a stub

**Decision.** A stub that writes nothing is untestable, so the smallest useful implementation
was built instead: co-occurrence relationships between roles, skills and technologies, each
carrying its evidence. Nothing downstream reads from it, which is intentional — swapping in
Neo4j at v2 is a replacement, not a migration.

### 2.7 "Human approval for high-impact decisions" had no interface

**Decision.** `POST /api/v1/recommendations/{id}/decision` accepts `approved`, `rejected`,
`needs_review`, and writes a `ValidationResult` recording who decided what. Artefacts failing
validation are set to `needs_review` rather than deleted, because deleting the record destroys
the audit trail the system exists to keep.

## 3. Specification decisions overridden

Two, both documented rather than silent.

### 3.1 Async agents → synchronous SQLAlchemy

§13 lists "Python, Async, Event-driven". The workload is database-bound, not IO-concurrent, and
FastAPI already runs synchronous path operations in a threadpool. Async ORM sessions shared
between agents introduce event-loop-bound failure modes that buy nothing here. The event model
is preserved; the concurrency model is not. Reversible: the agents are pure functions over a
`Session`.

### 3.2 Neo4j deferred, pgvector kept but unused in v1

§13 marks Neo4j as optional for v2, which is followed. pgvector is wired in — the
`normalized_documents.embedding` column is a real vector column on PostgreSQL and JSON
elsewhere — but no agent populates it in v1, because no v1 decision needs semantic similarity.
The column and its IVFFlat index exist so that adding embeddings later is a backfill, not a
schema change.

## 4. Gaps the specification did not mention, and were filled

| Gap | Resolution |
|---|---|
| No audit of agent execution | `agent_runs` table: every run logs agent, version, duration, inputs, outputs, errors |
| No event durability | `event_log` table written on every publish; Redis is fan-out only and never load-bearing |
| No source failure semantics | Per-source isolation: `SourceUnavailable` / `RateLimitExceeded` / `ParseError`, each emitting `document.collection_failed` |
| No deduplication rule | Unique constraint on `(source, external_id)` plus a content hash; re-collection is a no-op |
| No authentication | Optional `x-api-key` on all routes except `/health`, so probes still work |
| No prediction immutability enforcement | Duplicate `(metric, entity, target_period, method)` is skipped rather than updated; a changed forecast is a new version |
| Reports could state unsourced numbers | Every report builder reads only from trend / prediction / result rows, and each carries `evidence_ids` |

## 5. Known limitations in v1

Stated plainly, because a system built on this premise should not hide them.

1. **Accuracy and confidence are not the same kind of number.** `accuracy_score` is a bounded
   relative-error measure; confidence is a claim about reliability. The calibration delta treats
   them as comparable, which is a useful heuristic and not a proper scoring rule. The current
   demo data shows the system running *underconfident* (delta ≈ +0.50) for exactly this reason.
   The v2 fix is interval forecasts scored on coverage rather than point accuracy.
2. **Posting volume is a proxy for demand.** It leads real hiring by weeks and overstates churn.
   Every report says so.
3. **Entity extraction is dictionary-based.** Precise and auditable, but blind to terms absent
   from `services/taxonomy.py`. A hosted LLM provider widens recall; it does not fix the blind
   spot in the counting.
4. **Linear forecasts cannot see inflections.** By construction they miss the turn, and the
   published accuracy figure includes those misses.
5. **Single-process orchestration.** Correct up to roughly 10⁵ documents per run; beyond that
   see the scaling path in [MAINTENANCE.md](MAINTENANCE.md).
