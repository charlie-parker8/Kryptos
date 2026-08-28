# Kryptos frontend

Vite + React + TypeScript (strict) + TailwindCSS v4.

## Direction

The **trading-desk** identity: a dimmed trading room — deep slate ink, terminal amber,
muted sage/brick for up/down, 1px rules, no glow. Signatures are the **split-flap
equity board** and a **ticker tape welded to the bottom edge**. Light mode is a bright
trading floor / printed ledger; the ticker tape stays dark in both modes, and the
split-flap board re-skins to cream ledger tiles. Toggle in the top bar; the choice persists
(`localStorage`, versioned) and otherwise follows the OS setting. IBM Plex Sans + Mono.

Screens: **Auth** (`/login`, `/register` — the latter takes a unique username, the
leaderboard's display name), **Dashboard** (`/`), **Trade** (`/trade`), **Leaderboard**
(`/leaderboard`), and the standalone **legal** pages (`/terms`, `/privacy`). The app runs
on the real backend behind a Vite dev proxy — cookie auth,
`GET /portfolio` for the first account snapshot, `POST /positions` /
`POST /positions/{id}/close` / `GET /positions`, `GET /leaderboard` (polled), and the
`/ws` stream for live prices + `account_update` revaluation + `position_update` (the
liquidation toast) + the `bankruptcy_reset` moment. Add `?mock` to run on the deterministic
mock feed with the auth gate bypassed (no backend needed); `?bankrupt` previews the
bankruptcy-reset modal.

## Run

```
npm install
npm run dev        # http://localhost:5173  (proxies /auth /positions /portfolio /candles /leaderboard /ws → :8000)
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
  routes.tsx           /login /register /terms /privacy public; /  /trade  /leaderboard behind <RequireAuth>
  theme.ts             light/dark state (data-theme on <html>, no-flash script in index.html)
  app/                 RequireAuth (route gate), RealtimeConnector (opens the feed once authed)
  core/                data + behaviour, provider-agnostic
    api/                fetch wrapper (ApiError) + REST DTOs
    auth/               useSession (SWR on /auth/me), login/register/logout
    realtime/           RealtimeSource seam, wire types, wsSource (/ws), mock feed, mode flags
    state/              zustand stores (rAF-coalesced) + narrow selector hooks
    hooks/              useAccount (seed), usePositions (blotter), useLeaderboard (polled)
    lib/                money / format / staleness / direction helpers
    primitives/         AnimatedNumber, Marquee, StaleBadge, LiveDot, Delta, DirGlyph, Modal
    useDashboardData.ts
  auth/                AuthLayout, LoginScreen, RegisterScreen, AuthField
  dashboard/           AppShell, Dashboard, MarketLadder, Positions, OpenPositions, TapeTicker,
                       AccountSummary, AccountMenu, SplitFlapNumber, ThemeToggle,
                       BankruptcyModal, LiquidationToast
  trade/               TradeScreen, PositionTicket, PositionBlotter
  leaderboard/         LeaderboardScreen (+ placeholderData for ?mock)
  legal/               LegalPage shell + TermsScreen, PrivacyScreen (standalone, no app chrome)
  styles/
    index.css           Tailwind @theme mapping + base + browser-surface + reduced-motion
    theme.css           the --k-* palette (light + dark) + component styles (flap, tape, ledger)
```

## Realtime + REST wiring

`core/realtime/` is built to the real `/ws` contract: `createWebSocketSource()` implements
the same `RealtimeSource` interface as the mock, so `RealtimeConnector` picks one and
`connectRealtime` feeds the zustand stores unchanged. REST goes through `core/api/client.ts`
(same-origin — the httponly `kryptos_session` cookie rides along); SWR caches `/auth/me`,
`/portfolio` (first snapshot), `/positions` (blotter), and `/leaderboard` (polled every 5s).
`POST /positions` returns **201 on success**; a business rejection is a 4xx whose `detail`
the ticket shows, and a `503` is retried with the same `Idempotency-Key`. Closing is
idempotent (`POST /positions/{id}/close`). A `position_update{status:"liquidated"}` message
raises a transient toast (`LiquidationToast`); a `bankruptcy_reset` (equity hit $0) raises
the `BankruptcyModal`, and a restored `account_update` follows.
