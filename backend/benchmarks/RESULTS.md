# Kryptos benchmark results

One dated entry per benchmark run, newest first within each section, every entry traceable
to a git commit + parameters + measured numbers (per `docs/metrics-benchmark-plan.md`).
Entries are filed automatically under the `<!-- … -->` markers by the benchmark that
produced them — don't remove the markers.

---

## Milestone A — WebSocket tick-to-client latency  (resume bullet 1)

`k6/ws_latency.js`: every VU holds an authenticated `/ws` connection and records
`Date.now() - price_tick.broadcast_at` per frame (`broadcast_at` is stamped in
`app/price_stream.py::handle_tick`). Sweep `-e VUS=` upward until p95 `ws_tick_latency_ms`
or the WS error rate breaches the script threshold; the last level that held is the
reported ceiling — that's bullet 1's "X+ concurrent" and "Y ms p95".

    COOKIE=$(python benchmarks/scripts/seed_bench_account.py)
    k6 run -e BASE_URL=http://127.0.0.1:8000 -e WS_URL=ws://127.0.0.1:8000/ws \
           -e COOKIE=$COOKIE -e VUS=200 -e DURATION=60s benchmarks/k6/ws_latency.js

`ws_tick_latency_ms` occasionally shows a small negative min — `broadcast_at` and the k6
`Date.now()` are both whole-millisecond wall clocks on the same host, so sub-ms deliveries
round to 0 or -1 ms. Immaterial to p95/p99.

<!-- MILESTONE-A-ENTRIES -->

### 2026-08-28 — 6b0d936 (local: Windows, uvicorn 1 worker, live Kraken WS feed)
- Each VU holds one authenticated `/ws` connection; latency = `Date.now() − price_tick.broadcast_at`.
- **200 concurrent clients — p95 16 ms, p99 18 ms tick-to-client, 0 errors, 39,422 ticks over 60 s** (all thresholds pass; bound p95<250 ms / p99<750 ms).
- 100 concurrent — p95 9 ms, 0 errors. 50 concurrent — p95 7 ms, 0 errors.
- Latency grows ~linearly with client count (the in-process fan-out is one sequential
  `send_json` loop per tick on a single event loop): 20→2 ms, 50→7 ms, 100→9 ms, 200→16 ms.
- Above ~250 VUs the **k6/Windows client** side falls over — sockets that stay connected
  are still served at p95 ~22 ms, but reconnects start failing (ephemeral-port / handle
  pressure from k6 opening thousands of short connections). 200 is the clean client
  ceiling on this machine, not a server limit.

### 2026-08-28 — prod (api.playkryptos.com, Render free tier, dev machine → us-west1)
- 15 concurrent `/ws` clients, 30 s: 0 errors, 1,155 ticks delivered (~20/s), all clients connected.
- `ws_tick_latency_ms` comes out **near zero / slightly negative** — `broadcast_at` is
  Render's wall clock and the k6 `Date.now()` is this machine's, and the two differ by
  more than the transit time, so cross-host this metric only confirms delivery is fast
  (single-digit ms once skew is removed), not an absolute number. The same-host local run
  above is the valid p95.

---

## Milestone B — idempotent position execution  (resume bullet 2)

PostgreSQL row locks (`SELECT … FOR UPDATE` on the user row, then the position row) plus
the `uq_positions_user_idempotency_key` and partial `uq_positions_one_open_per_pair`
unique constraints. `tests/test_positions_concurrency.py` asserts **zero invariant
violations** across duplicate-idempotency-key opens, tight free-cash races, and
user-close-vs-liquidation races (including one driven through the real
`price_stream.handle_tick` engine). `test_position_lifecycle_throughput_benchmark`
(`pytest -m benchmark`) times N concurrent open+close round trips and files the throughput
here.

    .venv/Scripts/python.exe -m pytest tests/test_positions_concurrency.py -q   # correctness
    .venv/Scripts/python.exe -m pytest -m benchmark -q                          # throughput

<!-- MILESTONE-B-ENTRIES -->

### 2026-08-28 — 6b0d936
- N concurrent open+close round trips (distinct accounts): 200
- Elapsed: 1.127s
- Throughput: 177.4 round trips/sec
- Invariant violations: 0 (cash_balance non-negative, exactly one terminal ledger entry per position, asserted after the batch)

### 2026-08-28 — 6b0d936
- N concurrent open+close round trips (distinct accounts): 200
- Elapsed: 1.257s
- Throughput: 159.1 round trips/sec
- Invariant violations: 0 (cash_balance non-negative, exactly one terminal ledger entry per position, asserted after the batch)

### 2026-08-28 — 6b0d936
- N concurrent open+close round trips (distinct accounts): 1000
- Elapsed: 6.188s
- Throughput: 161.6 round trips/sec
- Invariant violations: 0 (cash_balance non-negative, exactly one terminal ledger entry per position, asserted after the batch)

### 2026-08-28 — 6b0d936
- N concurrent open+close round trips (distinct accounts): 500
- Elapsed: 3.147s
- Throughput: 158.9 round trips/sec
- Invariant violations: 0 (cash_balance non-negative, exactly one terminal ledger entry per position, asserted after the batch)

### 2026-08-28 — 6b0d936
- N concurrent open+close round trips (distinct accounts): 200
- Elapsed: 1.268s
- Throughput: 157.7 round trips/sec
- Invariant violations: 0 (cash_balance non-negative, exactly one terminal ledger entry per position, asserted after the batch)

### 2026-08-28 — 6b0d936
- N concurrent open+close round trips (distinct accounts): 200
- Elapsed: 1.229s
- Throughput: 162.7 round trips/sec
- Invariant violations: 0 (cash_balance non-negative, exactly one terminal ledger entry per position, asserted after the batch)

### 2026-08-28 — 6b0d936
- N concurrent open+close round trips (distinct accounts): 200
- Elapsed: 1.175s
- Throughput: 170.2 round trips/sec
- Invariant violations: 0 (cash_balance non-negative, exactly one terminal ledger entry per position, asserted after the batch)

### 2026-08-28 — 6b0d936
- N concurrent open+close round trips (distinct accounts): 200
- Elapsed: 1.209s
- Throughput: 165.4 round trips/sec
- Invariant violations: 0 (cash_balance non-negative, exactly one terminal ledger entry per position, asserted after the batch)

### 2026-08-28 — 6b0d936
- N concurrent open+close round trips (distinct accounts): 200
- Elapsed: 1.129s
- Throughput: 177.1 round trips/sec
- Invariant violations: 0 (cash_balance non-negative, exactly one terminal ledger entry per position, asserted after the batch)

### 2026-08-28 — 6b0d936
- N concurrent open+close round trips (distinct accounts): 200
- Elapsed: 1.045s
- Throughput: 191.3 round trips/sec
- Invariant violations: 0 (cash_balance non-negative, exactly one terminal ledger entry per position, asserted after the batch)

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

---

## Milestone C — Redis price cache + sorted-set leaderboard  (resume bullet 3)

### `scripts/cache_effectiveness.py` — Kraken Ticker calls saved by the price cache

Cached count varies run to run with how many of the concurrent viewers miss the cold cache
before the first fill lands (a real thundering herd on process start); it then settles to
~1 refetch per pair per TTL.

<!-- MILESTONE-C-PRICE-ENTRIES -->

### 2026-08-28 — 6b0d936
- Workload: 50 viewers × 3 pairs, 1 read/s for 20s (cache TTL 10s)
- Kraken calls without cache: 3000
- Kraken calls with cache: 231
- Reduction: 92.3%

### 2026-08-28 — 6b0d936
- Workload: 50 viewers × 3 pairs, 1 read/s for 20s (cache TTL 10s)
- Kraken calls without cache: 3000
- Kraken calls with cache: 154
- Reduction: 94.9%

### 2026-08-28 — 6b0d936
- Workload: 50 viewers × 3 pairs, 1 read/s for 20s (cache TTL 10s)
- Kraken calls without cache: 3000
- Kraken calls with cache: 72
- Reduction: 97.6%

### 2026-08-27 — d906a0f
- Workload: 50 viewers × 3 pairs, 1 read/s for 20s (cache TTL 10s)
- Kraken calls without cache: 2850
- Kraken calls with cache: 229
- Reduction: 92.0%

### `scripts/candle_cache_effectiveness.py` — Kraken OHLC calls saved by the candle cache

Same read-through model: a cold `:history` key is fetched once per (pair, interval), then
served from Redis until its TTL. The live WS `ohlc` stream keeps only `:forming` warm and
makes no REST calls.

<!-- MILESTONE-C-CANDLE-ENTRIES -->

### 2026-08-28 — 6b0d936
- Workload: 30 viewers over 12 (pair, interval) charts, 1 read/3s for 30s (history TTL 180s)
- Kraken OHLC calls without cache: 300
- Kraken OHLC calls with cache: 28
- Reduction: 90.7%
- Forming-candle WS broadcasts are coalesced to <=1/s per (pair, interval); the `:forming` Redis write on every trade is not rate-limited.

### 2026-08-28 — 6b0d936
- Workload: 30 viewers over 12 (pair, interval) charts, 1 read/3s for 30s (history TTL 180s)
- Kraken OHLC calls without cache: 300
- Kraken OHLC calls with cache: 28
- Reduction: 90.7%
- Forming-candle WS broadcasts are coalesced to <=1/s per (pair, interval); the `:forming` Redis write on every trade is not rate-limited.

### 2026-08-28 — 6b0d936
- Workload: 30 viewers over 12 (pair, interval) charts, 1 read/3s for 30s (history TTL 180s)
- Kraken OHLC calls without cache: 300
- Kraken OHLC calls with cache: 28
- Reduction: 90.7%
- Forming-candle WS broadcasts are coalesced to <=1/s per (pair, interval); the `:forming` Redis write on every trade is not rate-limited.

### 2026-08-27 — 0ac11ab
- Workload: 30 viewers over 12 (pair, interval) charts, 1 read/3s for 30s (history TTL 180s)
- Kraken OHLC calls without cache: 300
- Kraken OHLC calls with cache: 29
- Reduction: 90.3%
- Forming-candle WS broadcasts are coalesced to <=1/s per (pair, interval); the `:forming` Redis write on every trade is not rate-limited.

### `k6/leaderboard_latency.js` — GET /leaderboard p95/p99 under sustained concurrent reads

`constant-vus` held for a fixed duration (not a burst). Seed N accounts first so the
ranking is over a realistic board:

    COOKIE=$(python benchmarks/scripts/seed_bench_account.py --accounts 10000)
    k6 run -e BASE_URL=http://127.0.0.1:8000 -e COOKIE=$COOKIE -e VUS=15 benchmarks/k6/leaderboard_latency.js
    python benchmarks/scripts/seed_bench_account.py --clear

Use `127.0.0.1`, not `localhost` — Windows resolves `localhost` via a ~200 ms IPv6-first
path that swamps the measurement on a fresh connection.

<!-- MILESTONE-C-LEADERBOARD-ENTRIES -->

### 2026-08-28 — 6b0d936 (local: Windows, uvicorn 1 worker, no uvloop)
- Board: 10,000 ranked accounts seeded into `leaderboard:equity` (real ZSET + Postgres rows)
- `GET /leaderboard?limit=100`, `constant-vus`, 60 s sustained
- **15 concurrent readers — p95 135 ms, p99 178 ms, 175 req/s, 10,508 reads, 0 errors** (all thresholds pass)
- 10 concurrent readers — p95 95 ms, p99 132 ms, 157 req/s, 0 errors
- 5 concurrent readers — p95 39 ms, 181 req/s
- Ceiling: p95 crosses the 150 ms bound between 15 and 20 concurrent readers
  (VUS=20 → p95 230 ms; VUS=50 → p95 528 ms). Throughput is flat at ~170 req/s from
  VUS=5 up — the single dev worker serialises request handling on the Windows event loop
  (production runs Linux + uvloop). Single-request latency is ~15–25 ms.
- Read path is O(page): `ZREVRANGE` + `HMGET prev_ranks <page+viewer>` (not `HGETALL`) +
  `ZREVRANK`/`ZSCORE` + one indexed Postgres username lookup. The `HGETALL`→`HMGET` change
  (commit pending) cut p95 at 50 VUs from ~5 s to ~0.5 s.

### 2026-08-28 — prod (api.playkryptos.com, Render free tier: Linux/uvloop, ~0.1 vCPU)
- Board: 2 real accounts only (can't seed synthetic accounts into the live DB)
- `GET /leaderboard?limit=100`, 10 concurrent readers, 30 s, from a dev machine → us-west1
- p95 1.11 s, p99 1.54 s, median 394 ms, **min 117 ms** (≈ the round-trip floor), 18 req/s, 0 errors
- The free instance is hard CPU-capped (~0.1 vCPU shared), so this measures the free tier's
  throttle, not the read path — the min (117 ms ≈ one transcontinental RTT + minimal work)
  is the honest read-path figure on the real stack.

---

## Archive — pre-pivot spot system (superseded)

Runs from the spot buy/sell **order** system that the leveraged-position pivot (commit
`d9937cf`) replaced. Kept for provenance only — they measure code that no longer exists
(note the `orders/sec` and `holdings` wording). The current Milestone B numbers are above.

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
