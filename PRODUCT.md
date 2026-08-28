# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The primary user is a retail crypto enthusiast who wants to practice leveraged trading —
or compete with friends — without risking real money. They arrive knowing roughly what
Bitcoin, Ethereum, and Solana are, want to see live prices move, open long/short positions
with leverage, and watch their equity and unrealized P&L react. They are on a desktop or
laptop browser; the session is lean-forward and competitive (there is a leaderboard). Not
a professional trader, but comfortable with tickers, leverage, liquidation, and percent
changes.

## Product Purpose

Kryptos is a crypto **leveraged paper-trading** web app: real-time market prices from
Kraken, fake money, and no real trades ever execute. Every account starts with a
configurable cash balance ($10,000 by default). Users open **isolated-margin long or short
positions** by committing USD collateral at a leverage preset (2×/5×/10×); the server
marks, prices, and — when losses consume the collateral — liquidates them, all against the
live Kraken price. Users track live unrealized P&L, a per-position liquidation price, and
account equity. A Redis-backed leaderboard ranks accounts by equity. If account equity
falls to or below $0, the account resets to the starting balance and every open position
closes.

Success = a user can open the app, understand their standing in one glance, open a
position in a few seconds, and feel the market moving under their equity in real time.

## Positioning

A leveraged trading simulator that is honest about being a game: live provider prices and
server-authoritative financial correctness (atomic, idempotent, row-locked position
open/close; integer/Decimal money math; server-side marking and liquidation; no
client-supplied prices) behind a fake-money front end built for competition, not for
pretending to be a brokerage. It is not a charting platform, not a backtester, and not a
real exchange. No cross-margin, no funding rates, no partial closes, no hedged positions.

## Operating Context

- Desktop/laptop browser. The dashboard is the home surface — the screen a user keeps
  open while prices move.
- Prices update several times per second over one authenticated WebSocket. The portfolio
  revalues live off those ticks.
- Market is 24/7; there is no market-hours gate. A price older than the configured
  maximum age (10s) is "stale" and is surfaced as such, and blocks cash-mutating actions
  (open, user close, liquidation, bankruptcy re-valuation).
- Trading universe is small and fixed: **BTC/USD, ETH/USD, SOL/USD** (USD-quoted only).
- Opens can be rejected in-band (insufficient free cash, below min collateral, a position
  already open on the pair, stale price, pair not tradable); the UI treats a rejection as
  an ordinary result, not an error.
- A liquidation is not something the user asked for — it gets a transient toast; a full
  account wipeout gets the modal.

## Capabilities and Constraints

- **Auth:** email/password with server-set httponly session cookie (`kryptos_session`).
- **Trading:** isolated-margin long/short positions. One open position per (account, pair);
  no hedged positions. Leverage presets **2× / 5× / 10×**. Collateral committed in USD
  (≥ $10 min). Entry, mark, exit and liquidation all price off Kraken `last`. No trading
  fee in the MVP (the knob exists). No partial closes — a position closes whole.
- **Margin & liquidation:** `notional = collateral × leverage`; a position is liquidated
  when its equity (`collateral + unrealized P&L`) falls to `0.5% × notional`. The
  liquidation price is computed and stored at open; the per-tick engine force-closes any
  crossed position for every account, connected or not.
- **Money:** all authoritative math is server-side in Decimal; the API serializes money as
  JSON strings. The client never does authoritative arithmetic and never sends a price.
- **Equity:** always derived server-side as `free cash + Σ(open position collateral +
  unrealized P&L)`. Can go negative on a gap move. Redis only caches derived values;
  losing Redis costs freshness, never records.
- **Realtime:** server-push only over `/ws` — `price_tick` / `candle_update` (broadcast)
  and `account_update` / `position_update` / `bankruptcy_reset` (per-user). `price_tick`
  carries a `broadcast_at` unix-ms timestamp (latency benchmark marker — keep it stable).
- **Redis:** price cache, in-process WS fan-out (no Pub/Sub), an open-position index for
  the liquidation scan, and the equity leaderboard ZSET. All rebuildable from Postgres.
- **Out of scope (MVP):** real money/brokerage, options/futures, cross-margin, funding
  rates, partial closes, simultaneous hedged positions, multi-currency, KYC/AML,
  native/mobile clients, backtesting beyond current-price display, multi-instance/HA.

## Stack

Existing: Python/FastAPI + PostgreSQL + Redis backend (already built). Frontend (this
work): **Vite + React + TypeScript (strict) + TailwindCSS** — set in CLAUDE.md and
confirmed with the user, who also asked for a light/dark toggle on the shipped design and
an "animated" live-update feel (rolling numbers, directional flash, live ticker).

## Brand Commitments

- Name: **Kryptos**. No existing logo, wordmark, palette, or typography — visually
  greenfield.
- Voice (from CLAUDE.md's own register and the frontend-design guidance): plain, active,
  specific. Controls name their action; errors name the problem and the fix; empty states
  invite action. It is a game, so a little competitive edge in copy is welcome, but the
  numbers are never played for laughs.

## Evidence on Hand

- `CLAUDE.md` — the authoritative product/scope spec.
- `docs/metrics-benchmark-plan.md` — the three resume-bullet benchmarks this project
  backs with real load-test numbers; Milestone A is the WebSocket tick-to-client latency
  the frontend's realtime layer must not regress.
- Backend API contract verified in source: `backend/app/ws_messages.py`,
  `backend/app/account.py`, `backend/app/positions.py`, `backend/app/positions_math.py`,
  `backend/app/routers/{auth,positions,portfolio,leaderboard}.py`, `backend/app/deps.py`.
- The position / P&L / margin / liquidation / bankruptcy rules are specified in
  `docs/leverage-model.md`.
- No real users, testimonials, screenshots, or usage data exist yet. Mock market data in
  the prototypes is labeled illustrative.

## Product Principles

1. **One glance to standing.** The dashboard answers "how am I doing?" before the user
   reads a single label — account equity and its direction lead.
2. **The market is alive.** Prices, equity and unrealized P&L visibly move; staleness is
   shown, never hidden.
3. **Server is the source of truth.** The client displays and previews; it never computes
   money that matters, asserts a price, or decides a liquidation.
4. **A rejection is an answer, not a failure.** Insufficient free cash, stale price, and
   not-tradable are ordinary outcomes with clear next steps.
5. **Leverage cuts both ways, visibly.** The liquidation price and distance-to-liquidation
   are always on screen for an open position; a liquidation is announced, not silent.
6. **Honest about the game.** Fake money, real prices, real competition — the design leans
   into the contest without faking the gravity of a real brokerage.

## Accessibility & Inclusion

Quality floor, not a special requirement: keyboard focus visible on every control, body
contrast ≥ 4.5:1 in both themes, `prefers-reduced-motion` respected (rolling numbers snap
to their value; the ticker stops), tabular numerals so money columns align and don't
jitter as digits change.
