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

### 2026-08-27 — 0ac11ab
- N concurrent orders: 200
- Elapsed: 2.379s
- Throughput: 84.1 orders/sec
- Invariant violations: 0 (cash_balance and holdings asserted non-negative after the batch)

### 2026-08-27 — 0ac11ab
- N concurrent orders: 200
- Elapsed: 2.728s
- Throughput: 73.3 orders/sec
- Invariant violations: 0 (cash_balance and holdings asserted non-negative after the batch)

### 2026-08-27 — 0ac11ab
- N concurrent orders: 200
- Elapsed: 2.096s
- Throughput: 95.4 orders/sec
- Invariant violations: 0 (cash_balance and holdings asserted non-negative after the batch)

### 2026-08-27 — 0ac11ab
- N concurrent orders: 200
- Elapsed: 1.884s
- Throughput: 106.2 orders/sec
- Invariant violations: 0 (cash_balance and holdings asserted non-negative after the batch)

### `candle_cache_effectiveness.py` — Kraken OHLC calls saved by the candle history cache

Same read-through model as the price cache: a cold `:history` key is fetched once per
(pair, interval), then served from Redis until its (short) TTL. The live WS stream keeps
only `:forming` warm and makes no REST calls.

### 2026-08-27 — 0ac11ab
- Workload: 30 viewers over 12 (pair, interval) charts, 1 read/3s for 30s (history TTL 180s)
- Kraken OHLC calls without cache: 300
- Kraken OHLC calls with cache: 29
- Reduction: 90.3%
- Forming-candle WS broadcasts are coalesced to <=1/s per (pair, interval); the `:forming` Redis write on every trade is not rate-limited.

### 2026-08-27 — 0ac11ab
- N concurrent orders: 200
- Elapsed: 1.975s
- Throughput: 101.2 orders/sec
- Invariant violations: 0 (cash_balance and holdings asserted non-negative after the batch)

### 2026-08-27 — 0ac11ab
- N concurrent orders: 200
- Elapsed: 1.907s
- Throughput: 104.9 orders/sec
- Invariant violations: 0 (cash_balance and holdings asserted non-negative after the batch)

### 2026-08-27 — 956550b
- N concurrent orders: 200
- Elapsed: 1.972s
- Throughput: 101.4 orders/sec
- Invariant violations: 0 (cash_balance and holdings asserted non-negative after the batch)

### 2026-08-28 — 012b8c1
- N concurrent orders: 200
- Elapsed: 2.013s
- Throughput: 99.4 orders/sec
- Invariant violations: 0 (cash_balance and holdings asserted non-negative after the batch)

### 2026-08-28 — 1162689
- N concurrent open+close round trips (distinct accounts): 200
- Elapsed: 1.051s
- Throughput: 190.3 round trips/sec
- Invariant violations: 0 (cash_balance non-negative, exactly one terminal ledger entry per position, asserted after the batch)

### 2026-08-28 — 1162689
- N concurrent open+close round trips (distinct accounts): 200
- Elapsed: 1.149s
- Throughput: 174.1 round trips/sec
- Invariant violations: 0 (cash_balance non-negative, exactly one terminal ledger entry per position, asserted after the batch)

### 2026-08-28 — 1162689
- N concurrent open+close round trips (distinct accounts): 200
- Elapsed: 1.102s
- Throughput: 181.5 round trips/sec
- Invariant violations: 0 (cash_balance non-negative, exactly one terminal ledger entry per position, asserted after the batch)

### 2026-08-28 — 1162689
- N concurrent open+close round trips (distinct accounts): 200
- Elapsed: 1.147s
- Throughput: 174.4 round trips/sec
- Invariant violations: 0 (cash_balance non-negative, exactly one terminal ledger entry per position, asserted after the batch)
