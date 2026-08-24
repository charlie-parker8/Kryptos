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
