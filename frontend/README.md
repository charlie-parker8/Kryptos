# Kryptos frontend

Vite + React + TypeScript (strict) + TailwindCSS v4.

## Direction

The **trading-desk** identity: a dimmed trading room — deep slate ink, terminal amber,
muted sage/brick for up/down, 1px rules, no glow. Signatures are the **split-flap
net-worth board** and a **ticker tape welded to the bottom edge**. Light mode is a bright
trading floor / printed ledger; the flap board and the tape stay dark in both modes
because they are physical objects. Toggle in the top bar; the choice persists
(`localStorage`, versioned) and otherwise follows the OS setting. IBM Plex Sans + Mono.

Currently one screen — the Dashboard — on a mock live feed. Trade, Auth, and Leaderboard,
plus real backend wiring, come next.

## Run

```
npm install
npm run dev        # http://localhost:5173
npm run build      # tsc -b && vite build
npm run typecheck
npm run lint        # oxlint
```

Add `?frozen` to freeze the feed on one deterministic frame (for screenshots).

## Layout

```
src/
  main.tsx             fonts + realtime init + router
  routes.tsx
  theme.ts             light/dark state (data-theme on <html>, no-flash script in index.html)
  core/                data + behaviour, provider-agnostic
    realtime/           RealtimeSource seam, wire types (mirror the backend /ws), mock feed
    state/              zustand stores (rAF-coalesced) + narrow selector hooks
    lib/                money / format / staleness / direction helpers
    primitives/         AnimatedNumber, Marquee, StaleBadge, LiveDot, Delta, DirGlyph, ComingSoon
    useDashboardData.ts
  dashboard/           the screen: AppShell, Dashboard, MarketLadder, Positions,
                       TapeTicker, AccountSummary, SplitFlapNumber, ThemeToggle
  styles/
    index.css           Tailwind @theme mapping + base + browser-surface + reduced-motion
    theme.css           the --k-* palette (light + dark) + component styles (flap, tape, ledger)
```

## Backend integration (next)

`src/core/realtime/` is built to the real `/ws` contract. Swap `createMockSource` for a
`WebSocket('/ws')` implementation of `RealtimeSource`, add a Vite dev proxy for the REST
routes (same-origin so the `kryptos_session` cookie works), and add SWR hooks for
`/portfolio` `/orders` `/holdings` `/auth/me`. `POST /orders` returns 201 even on
rejection — branch on the body. See `.claude/plans/`.
