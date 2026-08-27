# Kryptos frontend

Vite + React + TypeScript (strict) + TailwindCSS v4.

## Direction

The **trading-desk** identity: a dimmed trading room — deep slate ink, terminal amber,
muted sage/brick for up/down, 1px rules, no glow. Signatures are the **split-flap
net-worth board** and a **ticker tape welded to the bottom edge**. Light mode is a bright
trading floor / printed ledger; the flap board and the tape stay dark in both modes
because they are physical objects. Toggle in the top bar; the choice persists
(`localStorage`, versioned) and otherwise follows the OS setting. IBM Plex Sans + Mono.

Screens: **Auth** (`/login`, `/register` — the latter takes a unique username, the
leaderboard's display name), **Dashboard** (`/`), **Trade** (`/trade`), and **Leaderboard**
(`/leaderboard`). The app runs on the real backend behind a Vite dev proxy — cookie auth,
`GET /portfolio` for first paint, `POST/GET /orders`, `GET /leaderboard` (polled), and the
`/ws` stream for live prices + portfolio revaluation + the `bankruptcy_reset` moment. Add
`?mock` to run on the deterministic mock feed with the auth gate bypassed (no backend
needed); `?bankrupt` previews the bankruptcy-reset modal.

## Run

```
npm install
npm run dev        # http://localhost:5173  (proxies /auth /orders /portfolio /ws → :8000)
npm run build      # tsc -b && vite build
npm run typecheck  # tsc -b
npm run lint       # oxlint
```

The backend must be running for the real app: from the repo root
`docker compose up -d`, then in `backend/` `alembic upgrade head` and
`uv run uvicorn app.main:app --port 8000`.

Add `?mock` to run on the mock feed with no backend and no login; `?frozen` also holds the
feed on one deterministic frame (for screenshots).

## Layout

```
src/
  main.tsx             fonts + SWRConfig + router
  routes.tsx           /login /register public; /  /trade  /leaderboard behind <RequireAuth>
  theme.ts             light/dark state (data-theme on <html>, no-flash script in index.html)
  app/                 RequireAuth (route gate), RealtimeConnector (opens the feed once authed)
  core/                data + behaviour, provider-agnostic
    api/                fetch wrapper (ApiError) + REST DTOs
    auth/               useSession (SWR on /auth/me), login/register/logout
    realtime/           RealtimeSource seam, wire types, wsSource (/ws), mock feed, mode flags
    state/              zustand stores (rAF-coalesced) + narrow selector hooks
    hooks/              usePortfolio (seed), useOrders (blotter), useLeaderboard (polled)
    lib/                money / format / staleness / direction helpers
    primitives/         AnimatedNumber, Marquee, StaleBadge, LiveDot, Delta, DirGlyph, Modal
    useDashboardData.ts
  auth/                AuthLayout, LoginScreen, RegisterScreen, AuthField
  dashboard/           AppShell, Dashboard, MarketLadder, Positions, TapeTicker, AccountSummary,
                       AccountMenu, SplitFlapNumber, ThemeToggle, BankruptcyModal
  trade/               TradeScreen, OrderTicket, OrderBlotter
  leaderboard/         LeaderboardScreen (+ placeholderData for ?mock)
  styles/
    index.css           Tailwind @theme mapping + base + browser-surface + reduced-motion
    theme.css           the --k-* palette (light + dark) + component styles (flap, tape, ledger)
```

## Realtime + REST wiring

`core/realtime/` is built to the real `/ws` contract: `createWebSocketSource()` implements
the same `RealtimeSource` interface as the mock, so `RealtimeConnector` picks one and
`connectRealtime` feeds the zustand stores unchanged. REST goes through `core/api/client.ts`
(same-origin — the httponly `kryptos_session` cookie rides along); SWR caches `/auth/me`,
`/portfolio` (first paint), `/orders` (blotter), and `/leaderboard` (polled every 5s).
`POST /orders` returns **201 even on rejection** — the ticket branches on `status` in the
body; a `503` is retried with the same `Idempotency-Key`. A `bankruptcy_reset` WS message
(net worth hit $0, account reset) raises a modal from `BankruptcyModal`; a restored
`portfolio_update` follows it.
