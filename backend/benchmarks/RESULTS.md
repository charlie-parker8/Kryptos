# Kryptos benchmark results

Dated entries, one per benchmark run, each traceable to a git commit, parameters, and
measured numbers, per docs/metrics-benchmark-plan.md.

## Milestone B — idempotent order execution (PostgreSQL row locks + unique constraints)

### 2026-08-24 — f6cd4d9
- N concurrent orders: 200
- Elapsed: 2.168s
- Throughput: 92.2 orders/sec
- Invariant violations: 0 (cash_balance and holdings asserted non-negative after the batch)

### 2026-08-24 — f6cd4d9
- N concurrent orders: 200
- Elapsed: 2.179s
- Throughput: 91.8 orders/sec
- Invariant violations: 0 (cash_balance and holdings asserted non-negative after the batch)

### 2026-08-24 — f6cd4d9
- N concurrent orders: 200
- Elapsed: 2.192s
- Throughput: 91.2 orders/sec
- Invariant violations: 0 (cash_balance and holdings asserted non-negative after the batch)

## Milestone C — Redis price cache + sorted-set leaderboard

### `cache_effectiveness.py` — Kraken calls saved by the price cache

The cached count varies run to run with how many of the 50 concurrent viewers miss the
cold cache before the first fill lands (a real thundering-herd on process start); it then
settles to ~1 refetch per pair per TTL. Reduction has held between 92% and 98% across runs.

### 2026-08-27 — d906a0f
- Workload: 50 viewers × 3 pairs, 1 read/s for 20s (cache TTL 10s)
- Kraken calls without cache: 2850
- Kraken calls with cache: 229
- Reduction: 92.0%

### `leaderboard_latency.js` — GET /leaderboard p95/p99 under sustained concurrent reads

_Pending: needs k6 (`k6 run backend/benchmarks/k6/leaderboard_latency.js` against the
running app). Script committed; no run recorded in this environment yet._
