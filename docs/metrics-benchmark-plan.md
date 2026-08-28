# Metrics + benchmark roadmap for Kryptos

> **Status (2026-08-28): complete.** All three features shipped and the app is live at
> `https://app.playkryptos.com`. Every benchmark below has been built and run; the measured
> numbers are in **[Results](#results)** and in `backend/benchmarks/RESULTS.md` (dated,
> commit-tagged). The three resume bullets with `X/Y/Z/N` filled in are in
> [Filled-in bullets](#filled-in-bullets).

## Context

_(Original framing, kept for provenance.)_ The project was at the Foundation phase when
this plan was written (backend skeleton, `/health`, Postgres/Redis wiring, a Kraken
adapter — no auth, positions, WebSocket fan-out, leaderboard, or frontend). The user wants
to list this project on their SWE resume and drafted three metric-shaped bullets
(concurrent users/latency, idempotent execution under concurrency, Redis
caching/leaderboard). This plan keeps those three themes — they map onto real,
honestly-measurable properties of the architecture — tightens the wording, and defines
*how* each number is produced, so nothing on the resume is a guessed placeholder.

Decisions made with the user:
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
2. "Engineered idempotent leveraged-position execution with PostgreSQL row locks and unique
   constraints, sustaining Z positions per second across N+ concurrent opens, duplicate
   submissions, and close-vs-liquidation races with zero invariant violations."
3. "Implemented Redis price caching and a sorted-set leaderboard, cutting Kraken API calls
   by X% while serving live rankings for N accounts at Y ms p95 latency under sustained
   concurrent read workloads."

These are framed as self-generated local load-test results (normal and expected for a solo
portfolio project) — `backend/benchmarks/RESULTS.md` is what lets the numbers be defended,
not just asserted.

<a id="filled-in-bullets"></a>
### Filled-in bullets (measured 2026-08-28, commit `6b0d936` + the leaderboard `HGETALL→HMGET` change)

1. "Built a real-time crypto paper-trading platform with FastAPI, React, and Kraken's REST
   and WebSocket APIs, sustaining **200+ concurrent WebSocket clients at 16 ms p95
   tick-to-client latency** (39k ticks / 60 s, zero drops) in k6 load tests."
2. "Engineered idempotent leveraged-position execution with PostgreSQL row locks and unique
   constraints, sustaining **~170 open→close position round-trips/sec across 1,000
   concurrent lifecycles**, 10-way duplicate-idempotency-key opens, and
   close-vs-liquidation races (real per-tick engine) with **zero invariant violations**."
3. "Implemented Redis price caching and a sorted-set leaderboard — **~92% fewer Kraken API
   calls** (91–98% across runs; 90.7% for the OHLC chart cache) and a **10,000-account
   ranking served at 95–135 ms p95** read latency under sustained concurrent load, reads
   O(page) not O(accounts)."

Caveats worth keeping honest: latency/throughput ceilings are from a single-worker dev
server on Windows (no uvloop) — production is Linux + uvloop; the WS ceiling of 200 is
where the *k6/Windows client* tops out, not the server; the leaderboard p95 is at 15
concurrent readers (the single dev worker serialises past that).

**Alignment check against the benchmarks below:**
- Bullet 1 ↔ Milestone A (`ws_latency.js`). One tightening from the user's draft: added
  "p95" explicitly — the k6 script finds max concurrency via a p95-latency threshold, so
  the bullet should name the percentile it's actually reporting (matches bullet 3's
  precision, and matches this plan's own original phrasing). Note this bullet deliberately
  claims WS tick delivery latency only, not portfolio-recalculation latency — that's more
  conservative than the earlier draft and matches exactly what `broadcast_at` measures.
- Bullet 2 ↔ Milestone B (pytest concurrency test). Direct match — positions/sec and
  zero-invariant-violations are exactly what that test is designed to produce.
- Bullet 3 ↔ Milestone C (`cache_effectiveness.py` + `leaderboard_latency.js`). Direct
  match for the % API-call reduction and p95 read latency. "Sustained concurrent read
  workloads" means `leaderboard_latency.js` must use a sustained-duration k6 scenario
  (e.g. `constant-vus` over a fixed duration), not a short burst — noted in Milestone C
  below.

## Benchmark systems, by milestone

_How each number is produced. All of this is now built and run — see
[Results](#results)._

### `backend/benchmarks/` layout
```
backend/benchmarks/
  k6/
    ws_latency.js                  # Milestone A
    leaderboard_latency.js         # Milestone C
  scripts/
    cache_effectiveness.py         # Milestone C — price cache
    candle_cache_effectiveness.py  # Milestone C — OHLC chart cache
    seed_bench_account.py          # cookie + N synthetic leaderboard accounts for the k6 scripts
  RESULTS.md
```
`RESULTS.md` gets one dated entry per run under a fixed per-milestone `<!-- … -->` marker
(the pytest/script appenders file themselves there): git commit hash, parameters, measured
numbers. This is the traceability record behind bullets 1–3. Milestone B's throughput
entry is appended by `test_position_lifecycle_throughput_benchmark`.

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

### Milestone B — after leveraged position open/close + row-locking + idempotency ship
- CLAUDE.md requires a pytest concurrency test covering exact-free-cash opens,
  one-per-pair rejection, duplicate/concurrent opens, and the user-close-vs-liquidation
  race, run against the real Postgres test DB (`backend/tests/conftest.py` fixtures +
  `kryptos_test` DB from `infra/postgres/init-test-db.sh`). See
  `backend/tests/test_positions_concurrency.py`. It should:
  - fire M concurrent opens sharing one idempotency key and assert a single position;
  - fire concurrent opens racing a tight free-cash balance and assert invariants 1–2 hold;
  - fire a user close and a liquidation at the same position and assert exactly one
    terminal transition, one ledger entry, and consistent cash (invariant 3/7);
  - wrap a batch of N open+close round trips in `time.perf_counter()` to derive positions/sec.
- Append the throughput/violation-count result to `RESULTS.md` after each run.
- Optional: a k6 script against `POST /positions` can add an HTTP-layer throughput number,
  but the pytest/DB-level test stays the sole authority on "zero invariant violations"
  since it can assert actual ledger/cash/position state.
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

<a id="results"></a>
## Results (measured 2026-08-28)

Full run-by-run detail with parameters and commit hashes is in
`backend/benchmarks/RESULTS.md`. Summary:

| Milestone | Metric | Result |
|---|---|---|
| A — WS tick-to-client latency | p95 / p99 tick latency, max clean concurrency | **16 ms / 18 ms at 200 concurrent clients** (0 drops, 39,422 ticks / 60 s). Scales ~linearly: 50→7 ms, 100→9 ms, 200→16 ms. 200 is the k6/Windows client ceiling, not the server. |
| B — idempotent position execution | round-trips/sec, invariant violations | **~170 open→close round-trips/sec** (162–191 across runs at N=200; 159/s at N=500; 162/s at N=1000). **0 invariant violations** at every N. `test_positions_concurrency.py` (6 tests incl. a real-tick close-vs-liquidation race) all green. |
| C — price cache | % Kraken Ticker calls saved | **92.3 / 94.9 / 97.6%** (fresh runs) — "92–98%", cite **92%**. |
| C — candle cache | % Kraken OHLC calls saved | **90.7%** (×3, stable). |
| C — leaderboard | p95 / p99 read latency at N accounts | **10,000 accounts: p95 135 ms / p99 178 ms at 15 concurrent readers** (175 req/s, 0 errors, 60 s); p95 95 ms at 10. p95 crosses the 150 ms bound between 15 and 20 readers — the single Windows dev worker serialises past that (throughput flat at ~170 req/s from 5 VUs up). Prod (Render free, ~0.1 vCPU) is CPU-throttled: min 117 ms ≈ the RTT floor. |

**Code change made while benchmarking:** `app/leaderboard.py::get_board` fetched *all*
previous ranks (`HGETALL`, O(total accounts)) to render the `move` column for ~100 rows.
Changed to `HMGET` of just the page + viewer keys — p95 at 50 concurrent readers dropped
from ~5 s to ~0.5 s. Covered by the existing `test_leaderboard.py` (10 tests green).

## Verification
- `docker compose up -d` for local Postgres/Redis.
- Milestone B: `pytest tests/test_positions_concurrency.py` (correctness, 0 violations) and
  `pytest -m benchmark` (throughput → `RESULTS.md`), against the real `kryptos_test` DB.
- Milestones A & C: start the app (`uvicorn app.main:app --host 127.0.0.1 --port 8000`),
  `python benchmarks/scripts/seed_bench_account.py [--accounts N]` for the cookie/seed, then
  `k6 run -e BASE_URL=http://127.0.0.1:8000 -e COOKIE=$COOKIE benchmarks/k6/<script>.js`.
  Use `127.0.0.1`, not `localhost` (Windows IPv6-first resolution adds ~200 ms per fresh
  connection). Cache scripts: `python benchmarks/scripts/cache_effectiveness.py`.
- Numbers are Windows single-worker (no uvloop); production is Linux + uvloop.
