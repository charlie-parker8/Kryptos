# Deployment runbook

How Kryptos goes from a local `docker-compose` + `vite dev` setup to a public deployment on
free hosting, and how to operate it there.

## Topology

```
  app.<domain>   ──Vercel (static SPA, CDN)
       │  fetch(credentials: "include") + WebSocket, same-site → Lax cookie rides along
       ▼
  api.<domain>   ──Render (Docker, 1 free instance: uvicorn --workers 1)
       ├── PostgreSQL ──── Supabase free (via the Supavisor pooler, session mode, TLS)
       └── Key Value ───── Render Key Value free (private network, redis://, 25 MB, ≤50 conns)

  GitHub Actions cron ── GET https://api.<domain>/health every ~10 min (keep-alive)
```

`app.<domain>` and `api.<domain>` are **different origins but the same site**, so the
`HttpOnly; Secure; SameSite=Lax` session cookie is sent on cross-origin `fetch`/WebSocket
calls without third-party-cookie problems. This is why a custom domain is required — the
bare `*.vercel.app` / `*.onrender.com` hosts are cross-*site* and would need
`SameSite=None`.

**Single instance is a hard constraint.** The API process runs the price-stream and
leaderboard-refresh asyncio tasks and an in-process WebSocket fan-out. Never raise the
worker count or instance count — the Dockerfile pins `--workers 1` and `render.yaml` uses a
single free web service.

**Redis lives on Render too.** The cache/leaderboard store is a Render Key Value instance
(Render's managed Redis), reached from the API over Render's private network — same
provider, same account, no separate signup, no public internet hop, no TLS.

## Prerequisites

- A custom domain you control DNS for.
- Accounts: [Vercel](https://vercel.com), [Render](https://render.com),
  [Supabase](https://supabase.com). (Render Key Value comes with the Render account.)
- The repo pushed to GitHub (Render and Vercel deploy from it).

## 1. DNS

Add two records at your DNS provider (fill in the targets from steps 4 and 5):

| Host | Type | Target |
|------|------|--------|
| `api` | CNAME | `kryptos-api.onrender.com` (Render gives the exact value) |
| `app` | CNAME | `cname.vercel-dns.com` (Vercel gives the exact value) |

## 2. Supabase (PostgreSQL)

1. Create a project. Pick the region closest to the Render region you'll choose in step 4.
2. Save the database password shown at creation.
3. **Connect → "Connection pooling" → "Session" mode.** Copy that URI. It looks like:
   `postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres`
   - Use the **pooler** host (`...pooler.supabase.com`), not the direct
     `db.<ref>.supabase.co` host — the direct host is IPv6-only and Render can't reach it.
   - Use **session mode** (port `5432` on the pooler), not transaction mode (`6543`) —
     session mode behaves like a normal connection, which is what a long-lived server + the
     migration step want.
4. Rewrite the scheme for SQLAlchemy's async driver: `postgresql://` → `postgresql+asyncpg://`.
   That final string is `KRYPTOS_DATABASE_URL`.
5. TLS is handled by `KRYPTOS_DATABASE_SSL=true` (set in `render.yaml`); nothing else to do.

Free-tier note: the project **pauses after 7 days of no activity** and must be resumed from
the dashboard. The keep-alive job (step 6) prevents this as long as it keeps running.

## 3. Render Key Value (Redis)

Nothing to do here if you deploy via the Blueprint in step 4 — `render.yaml` declares a
free `kryptos-kv` Key Value instance and wires `KRYPTOS_REDIS_URL` into the API service
automatically (private-network `redis://` URL, no TLS, no secret to copy).

Manual setup (Option B in step 4): **New → Key Value**, name `kryptos-kv`, instance type
**Free**, same region as the web service, **Maxmemory policy `allkeys-lru`**. Leave the IP
allow list empty so only Render-internal clients can connect. Then on the web service set
`KRYPTOS_REDIS_URL` to the instance's **Internal Key Value URL** (`redis://red-…:6379`).

The app caps its connection pool at 20 (`app/redis_client.py`) — under the free plan's
50-connection limit. Render Key Value free is not metered per command (matters: the price
stream writes to the cache several times a second while the instance is awake) but has
**no persistence** — a restart or deploy empties it. That's fine: every key is a
rebuildable cache (prices refill from Kraken within seconds; the leaderboard ZSET is
rebuilt from Postgres on the next refresh cycle and backfilled on login — CLAUDE.md
invariant 8).

## 4. Render (API)

Option A — Blueprint: in Render, **New → Blueprint**, point at the repo. It reads
`render.yaml` and creates the `kryptos-api` web service **and** the `kryptos-kv` Key Value
instance, with `KRYPTOS_REDIS_URL` already wired between them. You'll be prompted only for
the `sync:false` env vars (`KRYPTOS_DATABASE_URL`, `KRYPTOS_FRONTEND_ORIGIN`).

Option B — manual: create the Key Value instance first (step 3), then **New → Web Service**
→ the repo → Runtime **Docker**, Dockerfile path `./backend/Dockerfile`, Docker context
`./backend`, Health check path `/health`, instance type **Free**, same region as the Key
Value instance.

Set environment variables (Environment tab; mark the secrets as such):

| Key | Value |
|-----|-------|
| `KRYPTOS_ENVIRONMENT` | `production` |
| `KRYPTOS_DATABASE_SSL` | `true` |
| `KRYPTOS_DATABASE_URL` | the `postgresql+asyncpg://…pooler.supabase.com:5432/postgres` string from step 2 |
| `KRYPTOS_REDIS_URL` | the **Internal Key Value URL** (`redis://red-…:6379`) from step 3 |
| `KRYPTOS_FRONTEND_ORIGIN` | `https://app.<domain>` |
| `KRYPTOS_STARTING_CASH_BALANCE` | `100000.00` (optional) |
| `KRYPTOS_ALLOWED_HOSTS` | *(optional)* `["api.<domain>","kryptos-api.onrender.com"]` — see Troubleshooting |

Then: **Settings → Custom Domains → add `api.<domain>`**, and put the CNAME target it shows
into DNS (step 1). Render provisions TLS automatically.

The container runs `alembic upgrade head` before `uvicorn` on every boot (see
`backend/docker-entrypoint.sh`) — a failed migration fails the deploy, which is intended.

## 5. Vercel (SPA)

1. **Add New → Project** → the repo.
2. **Root Directory: `frontend`.** Framework preset: Vite (auto-detected). Build command
   `npm run build`, output `dist` (defaults).
3. Environment Variables:
   - `VITE_API_URL` = `https://api.<domain>`
   - `VITE_WS_URL` = `wss://api.<domain>/ws`
4. Edit `frontend/vercel.json`: in the `Content-Security-Policy` header, replace both
   `api.CHANGE-ME.example` occurrences with `api.<domain>`. Commit and redeploy.
5. **Settings → Domains → add `app.<domain>`**, put its CNAME target into DNS.

`vercel.json` already handles the SPA deep-link rewrite (`/trade`, `/leaderboard` → `index.html`)
and the security headers. `frontend/public/theme-init.js` is external (not inline) so the
CSP stays `script-src 'self'`.

## 6. Keep-alive

`.github/workflows/keepalive.yml` is already in the repo. Enable it:

1. Repo **Settings → Secrets and variables → Actions → Variables → New variable**:
   `KEEPALIVE_URL` = `https://api.<domain>/health`
2. **Actions** tab → enable workflows if prompted → run *keep-alive* once via
   "Run workflow" to confirm it's green.

A run turns red on HTTP 503 (Postgres unreachable) or no response — that doubles as a free
uptime alert. GitHub may delay cron by 5–15 min and disables schedules after 60 days of repo
inactivity.

## 7. Smoke test

Against `https://app.<domain>`:

1. Register a new account → you land on the dashboard with live BTC/ETH/SOL prices.
2. DevTools → Application → Cookies: `kryptos_session` is `Secure`, `HttpOnly`,
   `SameSite=Lax`, no `Domain` attribute, on `api.<domain>`.
3. DevTools → Network → WS: the `wss://api.<domain>/ws` connection is `101 Switching
   Protocols` and receiving `price_tick` frames.
4. Place a market buy → the position appears; net worth updates over the socket.
5. Open `/leaderboard`, then reload the page (tests the SPA rewrite) — still works.
6. Sign out → redirected to `/login`; revisiting `/` keeps you logged out.

`curl` checks:

```bash
curl -si https://api.<domain>/health                     # 200, {"status":"ok",...}
curl -si -X OPTIONS https://api.<domain>/orders \
  -H 'Origin: https://app.<domain>' \
  -H 'Access-Control-Request-Method: POST'                # ACAO echoes the origin, ACAC: true
curl -si -X POST https://api.<domain>/auth/login \
  -H 'Origin: https://evil.example' -H 'Content-Type: application/json' \
  -d '{"email":"a@b.com","password":"x"}'                 # 403 Cross-origin request rejected
```

## Operations

**Migrations.** Add a revision locally (`alembic revision --autogenerate -m "..."`), commit,
push. Render redeploys and runs `alembic upgrade head` on boot. To run one out of band:
Render **Shell** tab → `alembic upgrade head` / `alembic downgrade -1`.

**Rollback.** Render **Deploys** tab → "Redeploy" a previous successful deploy. If a bad
migration shipped, roll the code back *and* `alembic downgrade` to the matching revision.

**Logs.** Render **Logs** tab (live). The price-stream/leaderboard tasks log reconnects and
cycle failures there.

**Free-tier ceilings.** Render web service: 750 instance-hours/month — one always-on
service is ~720–744h, so run only the one. Render Key Value free: 25 MB, 50 connections,
no persistence. Supabase: 500 MB, 2 projects. Vercel Hobby: non-commercial use only.

**Cold starts.** With the keep-alive job running, the instance stays warm. If it lapses, the
first request after 15 min idle takes ~30–60 s, and for the first few seconds after wake the
Kraken stream hasn't refilled the price cache, so orders return `stale_price` (invariant 10)
until it does — expected, self-heals in seconds.

## Troubleshooting

**Build fails with `invalid peer certificate: UnknownIssuer` (local only).** This dev
machine runs a TLS-inspecting AV (Norton). Render's builders don't, so this only bites local
`docker build`. Export the Windows trust store to a PEM bundle:

```powershell
$pem = New-Object System.Text.StringBuilder
foreach ($s in 'Cert:\LocalMachine\Root','Cert:\CurrentUser\Root','Cert:\LocalMachine\CA') {
  Get-ChildItem $s -ErrorAction SilentlyContinue | ForEach-Object {
    [void]$pem.AppendLine('-----BEGIN CERTIFICATE-----')
    [void]$pem.AppendLine([Convert]::ToBase64String($_.RawData,'InsertLineBreaks'))
    [void]$pem.AppendLine('-----END CERTIFICATE-----')
  }
}
Set-Content -Path host-ca-bundle.pem -Value $pem.ToString() -Encoding ascii
```

then pass it as a build secret (it's `.gitignore`d):

```bash
docker build --secret id=extra_ca,src=host-ca-bundle.pem -t kryptos-api ./backend
```

The `Dockerfile` folds it into the system trust store; without the secret the step is a
no-op (`required=false`).

**Render deploy health check 400s.** `KRYPTOS_ALLOWED_HOSTS` is set but doesn't include the
host Render's checker uses. Add `kryptos-api.onrender.com` to the list, or unset the var
(the check then allows any host — acceptable here: the app builds no URLs from the Host
header and the cookie is host-only).

**DB connection errors / `Network is unreachable`.** You're using the direct
`db.<ref>.supabase.co` host (IPv6-only). Switch to the `…pooler.supabase.com:5432` session-mode
URI.

**`prepared statement "__asyncpg_…" already exists`.** Only happens on the transaction-mode
pooler (`:6543`). Use session mode (`:5432`). If you must use transaction mode, add
`?prepared_statement_cache_size=0` to `KRYPTOS_DATABASE_URL` and set
`connect_args["statement_cache_size"] = 0` in `app/db.py`.

**Redis `Connection refused` / `Name or service not known`.** `KRYPTOS_REDIS_URL` must be
the Key Value instance's **Internal** URL (`redis://red-…:6379`), and the web service must
be in the **same Render region** as the Key Value instance — private networking doesn't
cross regions. The external URL (`rediss://`) also works but needs the client IP on the
instance's allow list.

**Leaderboard is empty after a deploy.** Expected — Render Key Value free has no
persistence, so a deploy or restart wipes the cache. It refills on the next
leaderboard-refresh cycle and as users log in (CLAUDE.md invariant 8); no action needed.

**CORS errors in the browser.** `KRYPTOS_FRONTEND_ORIGIN` must be the exact scheme+host of
the SPA (`https://app.<domain>`, no trailing slash, no path).

**Login works but the session doesn't stick.** The API isn't seeing HTTPS. Confirm
`KRYPTOS_ENVIRONMENT=production` (so the cookie gets `Secure`) and that Render terminates TLS
(it does by default) — `uvicorn` runs with `--proxy-headers`.

## Provider swaps

The market-data adapter (`backend/app/market_data/`) is the only Kraken-specific code;
`CLAUDE.md` flags that Kraken's real-time-feed redistribution terms are unconfirmed. Prices
reach only authenticated users over `/ws`; keep a footer disclaimer and don't market the app
as a data feed. If Render's free tier changes, **Koyeb** free is the closest Docker-friendly
substitute — same env vars, same single-instance model. For the cache, any Redis-compatible
endpoint works: point `KRYPTOS_REDIS_URL` at it (`rediss://` for an external TLS provider
such as Redis Cloud or Upstash — note Upstash meters per command, which the price stream
would burn through).
