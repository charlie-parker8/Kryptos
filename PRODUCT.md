# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The primary user is a retail crypto enthusiast who wants to practice trading — or
compete with friends — without risking real money. They arrive knowing roughly what
Bitcoin, Ethereum, and Solana are, want to see live prices move, place buy/sell orders,
and watch their net worth react. They are on a desktop or laptop browser; the session is
lean-forward and competitive (there is a leaderboard). Not a professional trader, but
comfortable with tickers, order tickets, and percent changes.

## Product Purpose

Kryptos is a crypto **paper-trading** web app: real-time market prices from Kraken, fake
money, and no real trades ever execute. Every account starts with a configurable cash
balance ($100,000 by default). Users place market buy/sell orders that fill at the live
price, hold positions, and track a live portfolio net worth (cash + market value of
holdings). A Redis-backed leaderboard ranks accounts by net worth. If net worth falls to
or below $0, the account resets to the starting balance and holdings clear.

Success = a user can open the app, understand their standing in one glance, place a trade
in a few seconds, and feel the market moving under their portfolio in real time.

## Positioning

A trading simulator that is honest about being a game: live provider prices and
server-authoritative financial correctness (atomic, idempotent, row-locked order
execution; integer/Decimal money math; no client-supplied prices) behind a fake-money
front end built for competition, not for pretending to be a brokerage. It is not a
charting platform, not a backtester, and not a real exchange.

## Operating Context

- Desktop/laptop browser. The dashboard is the home surface — the screen a user keeps
  open while prices move.
- Prices update several times per second over one authenticated WebSocket. The portfolio
  revalues live off those ticks.
- Market is 24/7; there is no market-hours gate. A price older than the configured
  maximum age (10s) is "stale" and is surfaced as such, and blocks cash/holdings-mutating
  actions.
- Trading universe is small and fixed: **BTC/USD, ETH/USD, SOL/USD** (USD-quoted only).
- Orders can be rejected in-band (insufficient funds/holdings, stale price, pair not
  tradable); the UI must treat a rejection as an ordinary result, not an error.

## Capabilities and Constraints

- **Auth:** email/password with server-set httponly session cookie (`kryptos_session`).
- **Trading:** market orders only. Buys fill at ask, sells at bid. Fractional quantities
  allowed (e.g. 0.01 BTC), up to 10 decimal places. Every submission carries an
  idempotency key unique per account.
- **Money:** all authoritative math is server-side in Decimal; the API serializes money
  as JSON strings. The client never does authoritative arithmetic and never sends a
  price.
- **Net worth:** always derived server-side from Postgres cash/holdings + latest approved
  prices. Redis only caches derived values; losing Redis costs freshness, never records.
- **Realtime:** server-push only over `/ws` — `price_tick` (broadcast) and
  `portfolio_update` (per-user). `price_tick` carries a `broadcast_at` unix-ms timestamp
  (latency benchmark marker — keep the message contract stable).
- **Not yet built (backend):** the leaderboard endpoint, the bankruptcy-reset trigger,
  and any endpoint exposing config/markets. The frontend shows these as clearly labeled
  "coming soon" placeholders until the backend lands.
- **Out of scope (MVP):** real money/brokerage, margin/short/options/futures/leverage,
  multi-currency, KYC/AML, native/mobile clients, historical charting or backtesting
  beyond current-price display, multi-instance/HA.

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
  `backend/app/portfolio.py`, `backend/app/routers/{auth,orders,portfolio}.py`,
  `backend/app/deps.py`.
- No real users, testimonials, screenshots, or usage data exist yet. Mock market data in
  the prototypes is labeled illustrative.

## Product Principles

1. **One glance to standing.** The dashboard answers "how am I doing?" before the user
   reads a single label — net worth and its direction lead.
2. **The market is alive.** Prices and portfolio value visibly move; staleness is shown,
   never hidden.
3. **Server is the source of truth.** The client displays and previews; it never computes
   money that matters or asserts a price.
4. **A rejection is an answer, not a failure.** Insufficient funds, stale price, and
   not-tradable are ordinary outcomes with clear next steps.
5. **Honest about the game.** Fake money, real prices, real competition — the design
   leans into the contest without faking the gravity of a real brokerage.

## Accessibility & Inclusion

Quality floor, not a special requirement: keyboard focus visible on every control, body
contrast ≥ 4.5:1 in both themes, `prefers-reduced-motion` respected (rolling numbers snap
to their value; the ticker stops), tabular numerals so money columns align and don't
jitter as digits change.
