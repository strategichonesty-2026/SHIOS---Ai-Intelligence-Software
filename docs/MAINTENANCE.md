# Maintenance and scalability

## Routine operations

| Cadence | Task |
|---|---|
| Daily | Check `GET /api/v1/runs?limit=20` for failed agent runs |
| Weekly | Read the weekly report; confirm source mix has not collapsed onto one source |
| Weekly | Check `GET /api/v1/predictions/accuracy` — accuracy trend and calibration delta |
| Monthly | Review `services/taxonomy.py` against terms appearing in recent documents |
| Monthly | `VACUUM ANALYZE` on PostgreSQL; review slow queries |
| Quarterly | Re-read the governance thresholds in `config.py` against observed behaviour |

## Common changes

**Add a source.** Subclass `Source` in `app/sources/`, implement `collect()` and
`is_configured()`, register it in `app/sources/__init__.py::_FACTORIES`, add its id to
`ENABLED_SOURCES`. Raise `SourceUnavailable` / `RateLimitExceeded` / `ParseError` rather than
returning empty — the collector isolates and logs failures, and a silent empty return looks
like "no news" instead of "broken".

**Add vocabulary.** Edit the dictionaries in `app/services/taxonomy.py`. No migration needed;
the next extraction run picks up the terms. Historical documents are not re-extracted
automatically — run `python -m app.cli agent extraction --payload '{"limit": 100000}'` after
clearing `normalized_documents` if you need a full re-derivation.

**Add a metric.** `Trend.metric` already exists on every row. Add computation to
`TrendAgent.execute`, then pass `metric=` to the prediction agent. Nothing else changes.

**Change a governance threshold.** Edit `config.py` (`MIN_EVIDENCE_PER_RECOMMENDATION`,
`MAX_PREDICTION_REVIEW_DAYS`, `MIN_PERIODS_FOR_PREDICTION`). The tests in `test_governance.py`
encode the current values — update them deliberately, so a loosened rule is a visible commit
rather than a quiet drift.

**Swap the LLM provider.** Set `LLM_PROVIDER` and the matching key. Providers degrade to the
rule provider on error, so a bad key produces degraded prose, not an outage. Numbers are
unaffected either way.

## Tuning

**Confidence too low across the board.** Expected in v1: `accuracy_score` is a relative-error
measure and confidence is a reliability claim, so the calibration delta runs positive. Raise the
base term in `PredictionAgent._confidence` only if backtests justify it — or implement interval
forecasts (Milestone 3), which fixes the mismatch properly.

**Too many recommendations.** Lower `top_n` on the recommendation agent, or raise
`min_confidence` (default 0.15).

**Trends too noisy.** Raise `min_total_evidence` on the trend agent (default 3), or move to a
monthly period by switching `week_period` for `month_period` in the extraction agent.

## Scaling path

Current design is correct to roughly 10⁵ documents per run on a single process.

| Symptom | Action |
|---|---|
| Collection dominates run time | Move collection to a separate `python -m app.cli agent collector` cron; keep analysis on its own schedule |
| Extraction dominates | Batch the LLM calls, or shard by source across processes — extraction is embarrassingly parallel per document |
| Trend recomputation slow | Recompute only periods touched since the last run; the unique constraint on `(metric, entity_type, entity_name, period)` already makes this safe |
| API latency on dashboard | Add a materialised view for `dashboard/overview`; it is the only endpoint that aggregates across every table |
| One process is not enough | Subscribe workers to the Redis channel the bus already publishes to. Producers do not change — this is exactly why Redis is fan-out only |
| Table growth | Partition `evidence` and `event_log` by month; both are append-only and queried by recent period |

Indexes are already in place for the hot paths: `evidence(entity_type, entity_name, period)`,
`trends(metric, entity_type, entity_name, period)`, `predictions(status, expiration_date)`.

## Known limitations

Repeated from the analysis, because they should stay visible.

1. **Accuracy and confidence are different kinds of number.** The calibration delta treats them
   as comparable. It is a useful heuristic, not a proper scoring rule. Interval forecasts are the
   fix.
2. **Posting volume is a proxy for demand**, leading real hiring by weeks and overstating churn.
3. **Dictionary extraction is blind to unlisted terms.** Precise, auditable, and narrow.
4. **Linear forecasts cannot see inflections.** They will miss turns by construction; published
   accuracy includes those misses.
5. **The sample source is synthetic.** Every record it writes is labelled `synthetic: true`.
   Remove `sample_jobs` from `ENABLED_SOURCES` in any deployment where its data could be mistaken
   for real market signal.

## Failure modes and responses

| Symptom | Likely cause | Response |
|---|---|---|
| `collected: 0` across all sources | Network or credentials | Check `GET /api/v1/runs/events?name=document.collection_failed` |
| Predictions all `unverifiable` | Target periods have no trend rows | Confirm collection is still running; a gap in weeks breaks scoring |
| Recommendations stop appearing | Governance rejection | `rejected_by_governance` in the agent run output names the failing rule |
| Confidence collapses to the floor | Series became volatile, or calibration went sharply negative | Inspect `GET /api/v1/predictions/accuracy` per slice |
| Dashboard shows the empty state | API unreachable or `SHIOS_API_KEY` mismatch | The frontend fails soft by design; check `API_BASE_URL` from inside the container |
| Duplicate documents inflating counts | A source reposting under new external ids | Add near-duplicate detection via embeddings (Milestone 4) |
