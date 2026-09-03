# Tenant isolation — audit (2026-09-02)

**Question:** does the database guarantee that one account cannot read or write another
account's rows — not only the application layer?

## Where we stand

Tenant isolation is **application-level only**, and — as of this audit — **complete**. Every
request-scoped query over a user-owned table (`positions`, `ledger_entries`,
`user_sessions`, `email_verification_tokens`) is filtered by `user_id`, or by a secret
credential hash that is strictly stronger than an ownership check:

| Site | Scoping |
|---|---|
| `app/routers/positions.py` — `open` idempotency lookup, one-per-pair clash, `list_positions`, close cursor | `Position.user_id == user.id` |
| `app/positions.py` — `open_position`, `close_position` (`SELECT … FOR UPDATE` on both the user and position rows) | `user_id ==` on every `Position` / `User` select |
| `app/account.py` — `get_account_snapshot` | `Position.user_id == user.id` |
| `app/bankruptcy.py` — gate + revalue | `User.id == user_id`, `Position.user_id == user_id` |
| `app/deps.py`, `app/routers/auth.py` — session load, logout | scoped by `user_sessions.token_hash` (the cookie's SHA-256) |
| `app/verification.py` — `consume_token` | scoped by `email_verification_tokens.token_hash`, then `User.id == token.user_id` |

**Intended cross-account reads** (all system- or public-context, none request-scoped):

- `app/leaderboard.py::get_board` — reads other accounts' `username` + equity for the
  public board. This is the one deliberate cross-tenant read.
- `app/leaderboard.py::rebuild` — the periodic full re-valuation, a background job.
- `app/position_index.py::reconcile`, `app/price_stream.py` — the per-tick liquidation
  engine and its Redis index scan every open position on a pair, across all accounts. That
  is the product ("mark and liquidate every account every tick, connected or not").

No missing `WHERE user_id = …` was found on any request path.

## Database backstop: none

```
pg_class.relrowsecurity / relforcerowsecurity : false on every table
pg_policies                                    : (none)
connection role (local docker)                 : superuser, BYPASSRLS
```

The backend connects with a single Postgres role via one asyncpg pool (`app/db.py`); there
are no RLS policies. A future missing `WHERE user_id = …` would leak data with nothing at
the database to stop it. This is a normal, defensible design for a server-rendered API (the
DB is never exposed to clients, unlike a Supabase/PostgREST setup) — RLS here would be
**defense-in-depth**, not the primary control.

## Recommendation

1. **Ship now:** the cross-tenant regression tests in
   `backend/tests/test_tenant_isolation.py` (close / list / portfolio probed with a second
   account). Cheap, and they lock in the current guarantee.
2. **Follow-up ticket (not done here):** full RLS. It is a session/transaction-lifecycle
   refactor, not a drop-in:
   - `ENABLE` + `FORCE ROW LEVEL SECURITY` on `positions`, `ledger_entries`,
     `user_sessions`, `email_verification_tokens`; policies keyed on a GUC
     (`current_setting('app.user_id')::uuid`).
   - Every request's DB work must run in a transaction that first does
     `SET LOCAL app.user_id = :uid` — so `get_session` (and the WS / price-stream session
     factories) become transaction-scoped and take the current user, interacting with the
     existing explicit `SELECT … FOR UPDATE` locking in `app/positions.py`.
   - The background workers (`price_stream`, `leaderboard.rebuild`, liquidation engine)
     operate across all accounts — they need a separate role or a service-context GUC.
   - Provision a dedicated `kryptos_app` role `NOSUPERUSER NOBYPASSRLS` with table
     `GRANT`s and point `KRYPTOS_DATABASE_URL` at it (Supabase's pooler role may have
     `BYPASSRLS`, which makes policies a no-op).
   - Payoff is a backstop, not a new capability.
