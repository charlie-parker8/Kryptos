# Metrics + benchmark roadmap for Kryptos

## Context

The project is still at the Foundation phase (backend skeleton, `/health` endpoint,
Postgres/Redis wiring via `docker-compose.yml`, and a Kraken adapter — no auth, orders,
WebSocket fan-out, leaderboard, or frontend yet). The user wants to list this project on
their SWE resume and already drafted three metric-shaped bullets (concurrent
users/latency, idempotent order execution under concurrency, Redis caching/leaderboard).
Rather than inventing new themes, this plan keeps those three themes — they map well onto
real, honestly-measurable properties of this architecture — but tightens the wording and,
more importantly, defines *how* each number will actually be produced as the corresponding
feature gets built, so nothing on the resume is a guessed placeholder.

This is a roadmap only: nothing is implemented yet. Each benchmark gets built at the
milestone noted, once its feature exists.

Decisions already made with the user:
- **Load-generation tool: k6.** Used for anything that means "throw concurrent virtual
  users at a live endpoint and report latency/throughput percentiles" (WS ticks, leaderboard
  reads). Chosen over a custom asyncio script or Locust for its built-in percentile
  thresholds and mature WS support.
- **Benchmarks are committed, not throwaway.** They live in the repo under
  `backend/benchmarks/` alongside a dated results log, so every resume number is traceable
  to a script, a set of parameters, and a git commit — defensible if asked about in an
  interview.

## The 3 resume bullets to build toward (finalized wording)

1. "Built a real-time crypto paper-trading platform using FastAPI, React, and Kraken REST
   and WebSockets APIs, supporting X+ concurrent simulated users at p95 Y ms
   tick-to-client latency in k6 load tests."
2. "Engineered idempotent order execution with PostgreSQL row locks and unique
   constraints, sustaining Z orders per second across N+ concurrent and duplicate
   submissions with zero invariant violations."
3. "Implemented Redis price caching and a sorted-set leaderboard, cutting Kraken API calls
   by X% while serving live rankings for N accounts at Y ms p95 latency under sustained
   concurrent read workloads."

These are framed as self-generated local load-test results (normal and expected for a solo
portfolio project) — the results log below is what lets the numbers be defended, not just
asserted.

**Alignment check against the benchmarks below:**
- Bullet 1 ↔ Milestone A (`ws_latency.js`). One tightening from the user's draft: added
  "p95" explicitly — the k6 script finds max concurrency via a p95-latency threshold, so
  the bullet should name the percentile it's actually reporting (matches bullet 3's
  precision, and matches this plan's own original phrasing). Note this bullet deliberately
  claims WS tick delivery latency only, not portfolio-recalculation latency — that's more
  conservative than the earlier draft and matches exactly what `broadcast_at` measures.
- Bullet 2 ↔ Milestone B (extended pytest concurrency test). Direct match — orders/sec and
  zero-invariant-violations are exactly what that test is designed to produce.
- Bullet 3 ↔ Milestone C (`cache_effectiveness.py` + `leaderboard_latency.js`). Direct
  match for the % API-call reduction and p95 read latency. "Sustained concurrent read
  workloads" means `leaderboard_latency.js` must use a sustained-duration k6 scenario
  (e.g. `constant-vus` over a fixed duration), not a short burst — noted in Milestone C
  below.

## Benchmark systems to build, by milestone

### `backend/benchmarks/` layout (created when the first benchmark lands)
```
backend/benchmarks/
  k6/
    ws_latency.js
    leaderboard_latency.js
  scripts/
    cache_effectiveness.py
  RESULTS.md
```
`RESULTS.md` gets one dated entry per run: git commit hash, parameters (N clients/orders/
accounts), and the measured numbers. This is the traceability record behind bullets 1–3.

### Milestone A — after WebSocket price fan-out + live portfolio valuation ship
- Add a `broadcast_at` (unix ms) field to the outgoing price-tick WS message schema. This
  is the timestamp the latency measurement is computed against, and it's a small, honest
  addition (it also happens to support invariant 10's staleness checks).
- `backend/benchmarks/k6/ws_latency.js`: ramps virtual users opening WS connections and
  subscribing to price ticks; a custom k6 Trend metric records `recv_time - broadcast_at`
  per message. Use k6 `thresholds` to find the max concurrency the single-process server
  sustains before p95 latency or error rate breaches a chosen bound — that measured
  ceiling is bullet 1's "N+" and "Y ms".
- Feeds: **bullet 1**.

### Milestone B — after market buy/sell order execution + row-locking + idempotency ship
- CLAUDE.md already requires a pytest concurrency test covering exact-balance buys,
  zero-unit sells, and duplicate/concurrent orders, run against the real Postgres test DB
  (existing `backend/tests/conftest.py` fixtures + `kryptos_test` DB from
  `infra/postgres/init-test-db.sh`). No new test category — extend that required test to:
  - fire M concurrent submissions sharing one idempotency key and assert single execution;
  - fire concurrent buy/sell orders racing a tight cash/holdings balance and assert
    invariants 1–3 never break;
  - wrap the concurrent batch in `time.perf_counter()` to derive orders/sec.
- Append the throughput/violation-count result to `RESULTS.md` after each run.
- Optional: a k6 script against the HTTP order endpoint can add an HTTP-layer
  throughput/latency number, but the pytest/DB-level test stays the sole authority on
  "zero invariant violations" since it can assert actual ledger/balance/holdings state.
- Feeds: **bullet 2**.

### Milestone C — after Redis price cache + leaderboard ship
- `backend/benchmarks/scripts/cache_effectiveness.py`: runs a fixed simulated read
  workload against the Kraken adapter with caching disabled vs. enabled, counting outbound
  Kraken calls in each case, to derive the % reduction.
- `backend/benchmarks/scripts/candle_cache_effectiveness.py`: the same model for the
  Trade-page chart's `GET /candles` history cache — many open charts polling one
  pair+interval each, cached vs. uncached Kraken OHLC calls. The live `ohlc` WS stream only
  keeps `:forming` warm and makes no REST calls.
- `backend/benchmarks/k6/leaderboard_latency.js`: seeds N synthetic accounts into the
  Redis sorted set, then issues concurrent leaderboard-read requests, reporting p95/p99
  read latency. Uses a sustained-duration k6 scenario (`constant-vus` held for a fixed
  duration, not a short burst) so the result honestly backs "sustained concurrent read
  workloads."
- Feeds: **bullet 3**.

## Verification (once each milestone is actually implemented)
- `docker compose up` for local Postgres/Redis (already exists).
- Milestone B: `pytest` against the real `kryptos_test` DB, confirming zero invariant
  violations and printing throughput — this is also a normal CI-gating correctness test,
  not extra scope.
- Milestones A & C: `k6 run backend/benchmarks/k6/<script>.js` against the locally running
  FastAPI app, confirming a new dated entry is appended to
  `backend/benchmarks/RESULTS.md` with concrete numbers.
