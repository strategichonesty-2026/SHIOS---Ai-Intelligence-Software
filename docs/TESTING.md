# Testing

```bash
cd backend
pytest -q                                   # 53 tests, ~80 seconds
pytest -q --cov=app --cov-report=term-missing
pytest tests/test_pipeline.py -q            # the loop itself
```

Current state: **53 passing, 87% statement coverage.** CI fails the build below 80%.

## Strategy

The system's premise is that it tells the truth about itself. The test suite is organised
around that claim, in four layers.

| Layer | File | What it protects |
|---|---|---|
| Deterministic maths | `test_periods_and_stats.py` | Period arithmetic and statistics — everything numeric the system publishes |
| Governance rules | `test_governance.py` | That the rules reject what they claim to reject |
| Agent behaviour | `test_agents.py` | Contracts, failure isolation, and refusal-to-publish behaviour |
| End-to-end loop | `test_pipeline.py` | That the loop actually closes |
| HTTP surface | `test_api.py` | Response shapes, traceability, auth, 404s |

Tests run against SQLite with `LLM_PROVIDER=rule`, so the whole suite is deterministic, offline,
and free. That is not a convenience — a non-deterministic provider would make every assertion
about a recommendation flaky, and the governance tests would become decorative.

## Test cases that matter most

**The loop closes.** `test_full_loop_closes_the_learning_cycle` asserts that a single run
produces forecasts, scores them against observed actuals, and writes one learning record per
score. If the backtest anchoring breaks, this fails.

**Confidence actually moves.** `test_learning_feedback_moves_confidence_on_a_second_pass`
asserts the calibration multiplier diverges from 1.0 after scoring. A learning loop that records
feedback but never applies it would pass every other test in the suite.

**No dangling references.** `test_truth_maintenance_chain_has_no_dangling_references` walks every
`Prediction`, `PredictionResult` and `Recommendation` and checks that every referenced id
resolves to a live row.

**Governance cannot be bypassed.** `test_recommendation_agent_refuses_without_evidence` strips the
evidence from a prediction, runs the agent, and asserts zero recommendations were written and the
rejection was reported.

**Idempotency.** `test_collection_is_idempotent` and `test_trend_recomputation_is_stable` assert
that a second run collects nothing new and recomputes identical trend values. Without this,
reality checks would score against a moving target.

**Honest failure.** `test_reality_check_marks_unverifiable_rather_than_scoring_a_guess` points a
prediction at an entity with no actuals and asserts it is marked `unverifiable` rather than
scored. Scoring a missing value is how accuracy metrics get quietly inflated.

**Failure isolation.** `test_failing_source_is_isolated_and_logged` runs a broken source
alongside a healthy one and asserts the healthy one still delivers, with
`document.collection_failed` emitted.

**Determinism.** `test_sample_source_is_deterministic` asserts identical ids and content hashes
across two runs of the seeded source.

## Coverage by area

| Module | Coverage |
|---|---|
| `agents/reality_check.py` | 100% |
| `services/calibration.py` | 100% |
| `agents/base.py`, `agents/knowledge.py`, `agents/trend.py` | 98% |
| `agents/recommendation.py` | 96% |
| `agents/learning.py`, `agents/validator.py` | 95% |
| `agents/extraction.py`, `governance/rules.py` | 93% |
| `agents/prediction.py` | 91% |
| `agents/collector.py` | 89% |
| `agents/reporting.py` | 86% |
| **Total** | **87%** |

Uncovered lines are concentrated in live-network paths (Gmail OAuth, hosted LLM providers,
Redis) that are deliberately not exercised in CI. They are isolated behind interfaces and fail
soft by design.

## What is not tested, and why

- **Live external sources.** RSS, GitHub and Gmail calls are not hit in CI. They are covered by
  interface tests with stub sources; hitting them would make the suite non-deterministic and
  rate-limited.
- **Hosted LLM providers.** Same reason. The fallback path to the rule provider is the tested
  behaviour.
- **Frontend rendering.** Type-checked and built in CI (`npm run build` with `tsc`). Adding
  Playwright smoke tests against the docker stack is the obvious next step.
- **PostgreSQL-specific behaviour.** Migrations are verified against SQLite in CI. Before any
  production deploy, run `alembic upgrade head` against a scratch PostgreSQL instance — the
  pgvector branch of the initial migration only executes there.

## Adding a test

Fixtures live in `tests/conftest.py`: `db` (clean schema per test), `client` (FastAPI
`TestClient`), `sample_source`. API tests should use the `seeded` fixture pattern in
`test_api.py`, which runs a full loop and commits so the API's own session can see the data.
