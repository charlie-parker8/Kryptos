# CLAUDE.md

Crypto paper-trading web app: real-time cryptocurrency market prices, fake money, no real trades ever execute.

## MVP scope
- Email/password auth with sessions
- Starting cash balance per account (configurable, not hardcoded)
- Market buy/sell orders, executed at current price
- Per-account holdings (symbol, quantity, avg cost)
- Live portfolio net worth: cash + current market value of holdings
- Live price updates pushed to clients over WebSocket
- Redis-backed leaderboard, ranked by net worth
- Bankruptcy handling: net worth at or below $0 triggers an account reset to the starting cash balance and clears holdings

## Tech stack
- **Backend**: Python, FastAPI (async), Pydantic for request/response and domain models
- **Database**: PostgreSQL — durable source of truth for users, cash balances, holdings, orders, and the transaction ledger
- **DB access**: SQLAlchemy (async) + asyncpg, Alembic for migrations
- **Cache / ephemeral state**: Redis — leaderboard sorted set and latest-price cache. Redis contains no authoritative account, order, cash, or holding state. The leaderboard can be rebuilt from PostgreSQL plus current provider prices; the price cache is repopulated from the provider. Use in-process WebSocket fan-out for the MVP. Add Redis Pub/Sub only if market-data ingestion or WebSocket delivery becomes a separate process.
- **Realtime transport**: WebSockets (FastAPI native) for price ticks and portfolio/order updates
- **Market data**: Kraken's public REST API (ticker/OHLC/trades, no auth required) and WebSocket v2 API (real-time ticker/trade/OHLC streaming) for spot pair prices, accessed through one adapter module so the provider can be swapped without touching business logic. Runtime uses real provider data; deterministic mock data is permitted only for automated tests and offline development. Kraken's terms on bulk redistribution of real-time feeds are not fully confirmed — re-verify before public launch; public deployment requires a provider whose terms permit redistribution to application users.
- **Frontend**: React + TypeScript
- **Testing**: pytest (backend), Playwright via the `webapp-testing` skill (frontend/e2e)

## Financial correctness invariants
Non-negotiable — changes to these definitions require your explicit approval before implementation:
1. Cash balance never goes negative.
2. A buy order cannot execute for more than the account's cash balance at execution time (`price * qty <= cash`).
3. A sell order cannot execute for more asset units than the account currently holds of that symbol.
4. All money math uses integer cents or `Decimal` — never floats.
5. Every state change (order + ledger entry + balance/holding update) commits as one atomic PostgreSQL transaction or not at all. Order execution must lock the affected account and holding rows, or provide equivalent database-level concurrency protection, so concurrent orders cannot double-spend cash or oversell holdings.
6. Orders execute against the price at execution time, never a client-supplied price.
7. Order processing is idempotent. Every submission has an idempotency key unique per account, enforced by a PostgreSQL unique constraint, so retries cannot double-execute.
8. Cash and holdings are authoritative only in PostgreSQL; net worth is derived server-side from those values plus the latest approved market prices. Redis may cache derived values (net worth, leaderboard, prices), but losing Redis can only cost freshness, never financial records.
9. Order quantity must be a positive amount, represented as `Decimal` with precision matching the traded pair (fractional quantities are allowed — e.g., 0.01 BTC).
10. No cash- or holdings-mutating action — order execution or a bankruptcy trigger — may use a price older than the configured maximum age; missing or stale prices block the action instead.
11. Crypto markets trade 24/7, so there is no market-hours gate. Market orders execute at any time, subject to invariant 10's staleness check. If the market-data provider reports a pair as not currently tradable (e.g., paused, cancel-only, post-only, or limit-only), orders on that pair are rejected until it reports tradable again.
12. A bankruptcy reset atomically clears active holdings and restores starting cash, but preserves order and ledger history. The reset itself is recorded in the ledger.

## Non-goals (MVP)
- Real money, real brokerage integration, or real order execution
- Margin, short selling, options, futures, leverage
- Multi-currency accounts
- KYC/AML or other regulatory compliance
- Native/mobile clients
- Backtesting, trading-strategy simulation, or trade-history analytics. (A read-only OHLC
  candlestick chart on the Trade page is in scope: recent history from a Redis-cached
  `GET /candles`, live bars from the Kraken WS `ohlc` feed fanned out over `/ws`, purely
  for display. It never gates, prices, or blocks an order, and Postgres stores no market data.)
- Multi-instance scaling, multi-region, or HA concerns

## Coding & testing expectations
- Type-annotate all Python; keep it mypy-clean where practical. TypeScript stays in strict mode.
- Add unit and integration tests alongside any change. Any code touching cash, orders, or holdings needs tests covering the invariants above, especially boundary cases: exact-balance buys, zero-unit sells, and concurrent or duplicate orders.
- Pure money-calculation unit tests may run without a database. Tests of transactions, locking, idempotency, database constraints, or concurrent orders must use a real PostgreSQL test database rather than mocked persistence.
- Before claiming a task done, actually run the relevant tests and confirm their output using the `verification-before-completion` skill; do not infer pass or fail.
- User-visible flows (buy, sell, leaderboard, bankruptcy reset) get a Playwright check via the `webapp-testing` skill when touched.

## Benchmark plan
`docs/metrics-benchmark-plan.md` tracks the metrics this project is meant to back with real numbers, and
the k6/pytest benchmarks needed to produce them honestly. Consult it when working on any of
its three milestones, and build the corresponding benchmark alongside the feature rather
than after the fact:
- WebSocket price fan-out / live portfolio valuation → Milestone A (`ws_latency.js`, the
  `broadcast_at` timestamp field)
- Market order execution, row-locking, idempotency → Milestone B (the pytest concurrency
  test already required above doubles as this milestone's benchmark)
- Redis price cache + leaderboard → Milestone C (`cache_effectiveness.py`,
  `leaderboard_latency.js`)

## Avoid premature abstraction
- No repository/service-layer scaffolding until 2-3 real call sites actually need it.
- No plugin system, strategy pattern, or generic "provider interface" beyond the one market-data adapter explicitly needed to isolate the external API.
- Don't build configurability the MVP doesn't need (multiple currencies, order types, auth providers).
- Three similar lines beat a shared abstraction guessed at in advance.
- If it isn't in MVP scope above, don't scaffold for it "to make it easier later."
