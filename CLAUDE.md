# CLAUDE.md

Crypto **leveraged** paper-trading web app: real-time cryptocurrency market prices, fake money, no real trades ever execute. Users open isolated-margin long/short positions with leverage; the server marks, prices, and liquidates them. See `docs/leverage-model.md` for the full position / P&L / margin / liquidation / bankruptcy rules.

## MVP scope
- Email/password auth with sessions
- Starting cash balance per account, configurable, not hardcoded (**$10,000** default)
- Isolated-margin **long/short positions**: user picks pair, side, USD collateral, and a leverage preset (2×/5×/10×); the position opens at the live price
- One open position per (account, pair); no simultaneous hedged positions; no partial closes
- Live per-position unrealized P&L, stored liquidation price, and account equity (free cash + Σ open-position collateral + unrealized P&L)
- Full position closing (user-initiated) and automatic liquidation when a position's equity falls to the maintenance margin
- Live price updates pushed to clients over WebSocket
- Redis-backed leaderboard, ranked by **account equity**
- Bankruptcy handling: account equity at or below the configured floor ($0 default) closes every open position, restores starting cash, and preserves history
- Read-only OHLC candlestick chart on the Trade page (unchanged from before — display only)

## Tech stack
- **Backend**: Python, FastAPI (async), Pydantic for request/response and domain models
- **Database**: PostgreSQL — durable source of truth for users, cash balances, positions, and the ledger. One fresh initial Alembic migration (`0001_initial`); there is no prior spot schema to migrate from.
- **DB access**: SQLAlchemy (async) + asyncpg, Alembic for migrations
- **Cache / ephemeral state**: Redis — the equity leaderboard sorted set, the latest-price cache, and an **open-position index** (`positions:open:{pair}` sets) that seeds the per-tick liquidation scan. Redis contains no authoritative account, position, cash, or ledger state; everything in it rebuilds from PostgreSQL plus current provider prices. In-process WebSocket fan-out (no Redis Pub/Sub) for the MVP — add Pub/Sub only if market-data ingestion or WebSocket delivery becomes a separate process.
- **Realtime transport**: WebSockets (FastAPI native) — `price_tick` / `candle_update` broadcast, `account_update` / `position_update` / `bankruptcy_reset` per-user.
- **Market data**: Kraken's public REST API (Ticker/AssetPairs/OHLC, no auth) and WebSocket v2 API (ticker/OHLC streaming) for spot pair prices, through one adapter module so the provider can be swapped without touching business logic. Entry, mark, exit and liquidation all price off Kraken `last` (there is no bid/ask spread in this model). Runtime uses real provider data; deterministic mock data is permitted only for automated tests and offline development. Kraken's terms on bulk redistribution are not fully confirmed — re-verify before public launch.
- **Frontend**: React + TypeScript (strict)
- **Testing**: pytest (backend), Playwright via the `webapp-testing` skill (frontend/e2e)

## Financial correctness invariants
Non-negotiable — changes to these definitions require your explicit approval before implementation:
1. Free cash (`users.cash_balance`) never goes negative.
2. Opening a position cannot commit more collateral (plus fee) than the account's free cash at execution time.
3. A position closes exactly once. The `open → closed | liquidated` status transition happens under a `SELECT … FOR UPDATE` on the position row; there are no partial closes.
4. All money math uses integer cents or `Decimal` — never floats.
5. Every state change (position row + ledger entry + cash update + Redis index op) commits as one atomic PostgreSQL transaction or not at all. Open and close lock the affected user row and position row, so concurrent opens can't double-spend cash and a user close can't race the liquidation engine.
6. Positions open, close, mark, and liquidate against the server's price at execution time (Kraken `last`), never a client-supplied price. Collateral, side and leverage are client-supplied and validated.
7. Opening a position is idempotent: every open carries an idempotency key unique per account, enforced by a PostgreSQL unique constraint, so retries can't double-open. Closing and liquidation are made idempotent by the invariant-3 status transition under lock (a retry re-reads the terminal row and returns it) rather than a second key.
8. Cash and positions are authoritative only in PostgreSQL; account equity is derived server-side as free cash + Σ(open position collateral + unrealized P&L at the latest approved price). Equity **can be negative** between ticks (a gap move past a liquidation price). Redis may cache derived values (equity, leaderboard, prices) and the open-position index, but losing Redis can only cost freshness, never records.
9. Collateral is a positive `Decimal` (≥ the configured minimum, ≤ 2 dp). Position size is `Decimal`, `notional / entry_price` rounded down to the pair's precision so realized notional never exceeds `collateral × leverage`.
10. No cash-mutating action — opening, a user close, an automatic liquidation, or a bankruptcy re-valuation — may use a price older than the configured maximum age; missing or stale prices block the action (a liquidation, which is driven by a fresh tick, simply cannot fire while the price stream is stale).
11. Crypto markets trade 24/7, so there is no market-hours gate. Opens are rejected while the provider reports the pair not tradable (paused, cancel-only, post-only, limit-only). Closing a position does **not** require the pair to be tradable — only a fresh price — so a user (and the liquidator) can always reduce risk.
12. A bankruptcy reset atomically closes every open position at its fresh mark (recording each on its row with `close_reason = 'bankruptcy'`), restores starting cash, and writes one `bankruptcy_reset` ledger entry. Position and prior ledger history are preserved.

## Position / margin / liquidation rules
Full spec in `docs/leverage-model.md`. In brief: `notional = collateral × leverage`;
`size = round_down(notional / entry_price)`; a long's P&L is `size × (mark − entry)`, a
short's is `size × (entry − mark)`; maintenance margin is `0.5% × notional`; the stored
liquidation price is `entry × (1 + mmr − 1/L)` for a long, `entry × (1 − mmr + 1/L)` for a
short. No trading fee in the MVP (`KRYPTOS_TAKER_FEE_BPS = 0`, knob retained). Config:
`KRYPTOS_LEVERAGE_PRESETS`, `KRYPTOS_MAINTENANCE_MARGIN_RATE`, `KRYPTOS_MIN_COLLATERAL`,
`KRYPTOS_BANKRUPTCY_EQUITY_FLOOR`, `KRYPTOS_STARTING_CASH_BALANCE`.

## Non-goals (MVP)
- Real money, real brokerage integration, or real order execution
- Options, futures, cross-margin, funding rates, partial closes, simultaneous hedged positions
- Limit / stop / take-profit orders, adjusting a position's collateral or leverage after open
- Multi-currency accounts
- KYC/AML or other regulatory compliance
- Native/mobile clients
- Backtesting, strategy simulation, or trade-history analytics. (The read-only OHLC
  candlestick chart on the Trade page stays in scope: recent history from a Redis-cached
  `GET /candles`, live bars from the Kraken WS `ohlc` feed fanned out over `/ws`, purely
  for display. It never gates, prices, or blocks a position, and Postgres stores no market data.)
- Multi-instance scaling, multi-region, or HA concerns
- Backward-compatible / transitional migrations for the old spot system — production is a clean first deployment

## Coding & testing expectations
- Type-annotate all Python; keep `mypy app` clean. TypeScript stays in strict mode (`npm run typecheck` clean).
- Add unit and integration tests alongside any change. Any code touching cash, positions, or liquidation needs tests covering the invariants above, especially boundary cases: exact-free-cash opens, one-per-pair rejection, concurrent/duplicate opens, and user-close-vs-liquidation races.
- Pure money-calculation unit tests may run without a database (`test_positions_math.py`). Tests of transactions, locking, idempotency, database constraints, concurrent opens, or the liquidation engine must use a real PostgreSQL test database rather than mocked persistence.
- Before claiming a task done, actually run the relevant tests and confirm their output using the `verification-before-completion` skill; do not infer pass or fail.
- User-visible flows (open long, open short, close, liquidation, leaderboard, bankruptcy reset) get a Playwright check via the `webapp-testing` skill when touched.

## Benchmark plan
`docs/metrics-benchmark-plan.md` tracks the metrics this project backs with real numbers.
Build the corresponding benchmark alongside the feature:
- WebSocket price fan-out / live equity valuation → Milestone A (`k6/ws_latency.js`, the `broadcast_at` field)
- Position open/close, row-locking, idempotency, and the close-vs-liquidation race → Milestone B (the pytest concurrency test doubles as this milestone's benchmark)
- Redis price cache + equity leaderboard → Milestone C (`scripts/cache_effectiveness.py`, `k6/leaderboard_latency.js`)

## Avoid premature abstraction
- No repository/service-layer scaffolding until 2-3 real call sites actually need it.
- No plugin system, strategy pattern, or generic "provider interface" beyond the one market-data adapter.
- Don't build configurability the MVP doesn't need (more order types, more collateral currencies, auth providers).
- Three similar lines beat a shared abstraction guessed at in advance.
- If it isn't in MVP scope above, don't scaffold for it "to make it easier later."
