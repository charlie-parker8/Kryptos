# Leverage model

The authoritative spec for how a Kryptos position is opened, valued, closed, liquidated,
and how an account goes bankrupt. Implemented in `backend/app/positions_math.py` (pure
math), `backend/app/positions.py` (open/close + locking), `backend/app/account.py`
(valuation), `backend/app/price_stream.py` (the liquidation engine), and
`backend/app/bankruptcy.py`.

## One price

There is a single price in this model: Kraken's **`last`**. Entry, mark (for unrealized
P&L), exit, and the stored liquidation price all use it. There is no bid/ask spread cost.

## Config

| Setting | Env var | Default |
|---|---|---|
| Starting cash | `KRYPTOS_STARTING_CASH_BALANCE` | `10000.00` |
| Leverage presets | `KRYPTOS_LEVERAGE_PRESETS` | `[2, 5, 10]` |
| Maintenance margin rate (`mmr`) | `KRYPTOS_MAINTENANCE_MARGIN_RATE` | `0.005` (0.5%) |
| Minimum collateral | `KRYPTOS_MIN_COLLATERAL` | `10.00` |
| Taker fee | `KRYPTOS_TAKER_FEE_BPS` | `0` |
| Bankruptcy equity floor | `KRYPTOS_BANKRUPTCY_EQUITY_FLOOR` | `0.00` |
| Max price age | `KRYPTOS_PRICE_MAX_AGE_SECONDS` | `10` |

## Opening a position

Input: `pair`, `side ∈ {long, short}`, `collateral` (USD Decimal, ≤ 2 dp), `leverage ∈ presets`.

Guards, in order — the first failure is the rejection (nothing is persisted, the
idempotency key stays unconsumed):

0. account email verified (`users.email_verified_at IS NOT NULL`) → else
   `email_not_verified` (403). Checked in the router before `open_position()`, so an
   unverified account is refused even on an idempotent retry (nothing is persisted, the key
   stays unconsumed). Does not affect closing or liquidation — you can always reduce risk.
1. `leverage ∈ presets` → else `leverage_not_allowed` (422)
2. `collateral ≥ min_collateral` → else `below_min_collateral` (422)
3. fresh `last` price (invariant 10) → else `stale_price` (409)
4. pair tradable (invariant 11) → else `pair_not_tradable` (409)
5. no existing open position on `pair` → else `position_exists` (409) — also enforced by the partial unique index `uq_positions_one_open_per_pair`
6. **under the user row lock:** `collateral + open_fee ≤ free_cash` → else `insufficient_free_cash` (402)

A market-data provider outage (no definitive answer) is a `503`, not a rejection — retry
with the same key.

On success, in one transaction: insert the `positions` row (`status = 'open'`), debit
`collateral + open_fee` from `users.cash_balance`, write a `position_open` ledger entry,
then `SADD positions:open:{pair}`.

Derived and stored at open:

```
notional      = collateral × leverage
entry_price   = last                            (quantized to 8 dp)
size          = round_down(notional / entry_price, 10 dp)
open_fee      = quantize_cash(notional × fee_bps / 10000)      # 0 today
liq_price     = entry_price × (1 + mmr − 1/leverage)           # long
              = entry_price × (1 − mmr + 1/leverage)           # short
```

## Marking (continuous)

```
mark                 = latest last (tolerant — stale is flagged, never blocks display)
unrealized_pnl       = size × (mark − entry_price)             # long
                     = size × (entry_price − mark)             # short
position_equity      = collateral + unrealized_pnl
maintenance_margin   = mmr × notional
margin_ratio         = position_equity / notional
account_equity       = free_cash + Σ_open(collateral + unrealized_pnl)
```

`account_equity` can be **negative** — a gap move can carry the mark past a liquidation
price between ticks.

## Closing (user-initiated)

`POST /positions/{id}/close`. Lock the user row, then the position row `FOR UPDATE`
(consistent order). If the position is already terminal, return it unchanged (idempotent).
A user close needs a fresh `last` (invariant 10) but **not** a tradable pair (relaxed
invariant 11 — you can always reduce risk).

```
close_price   = last
realized_pnl  = unrealized_pnl(close_price)
close_fee     = quantize_cash(notional × fee_bps / 10000)      # 0 today
returned_cash = max(collateral + realized_pnl − close_fee, 0)  # isolated margin floor
```

`users.cash_balance += returned_cash`; the position goes `status = 'closed'`,
`close_reason = 'user'`; a `position_close` ledger entry is written; `SREM
positions:open:{pair}`.

## Automatic liquidation

Runs in `price_stream.handle_tick`, on every tick, for **all** accounts (connected or not).
Ticks for a pair are processed one at a time, so the scan never overlaps itself.

1. Candidate position ids come from `SMEMBERS positions:open:{pair}` (falls back to a
   direct Postgres scan on a Redis outage; reconciled from Postgres on startup and every
   leaderboard-refresh cycle).
2. Cheap pre-check against the stored `liquidation_price`: a **long** liquidates when
   `mark ≤ liq_price`, a **short** when `mark ≥ liq_price`.
3. Each crossed position is closed via the same `close_position` path with
   `reason = "liquidation"` and the tick price as the mark — re-checking `status = 'open'`
   under the row lock, so a user close (or an earlier tick) that got there first is a
   no-op. The position goes `status = 'liquidated'`, `close_reason = 'liquidation'`, and a
   `liquidation` ledger entry is written.
4. The affected user gets a `position_update{status: "liquidated"}`, a fresh
   `account_update`, a leaderboard refresh, and a bankruptcy check.

A clean liquidation at the liquidation price returns roughly `maintenance_margin` to free
cash. A gap move past the liquidation price returns `0` (the shortfall below `−collateral`
is absorbed — isolated margin) and pushes account equity toward or below the bankruptcy
floor.

## Bankruptcy reset

`bankruptcy.maybe_reset_bankrupt_account`. Lock-free gate on `equity > floor` (tolerant
valuation); if plausibly bankrupt, lock the user row and every open position `FOR UPDATE`,
re-value strictly with fresh prices (invariant 10 — any stale price defers the reset),
re-check `equity ≤ floor` under the lock, then in one transaction: close every open
position at its fresh mark (`close_reason = 'bankruptcy'`, realized P&L on the row), set
`users.cash_balance = users.starting_cash_balance`, write one `bankruptcy_reset` ledger
entry, and `SREM` each position from the index. Position and ledger history are preserved
(invariant 12). Checked on the per-tick account push, after a liquidation, after an
open/close, and on `/ws` (re)connect.

## Leaderboard

Redis ZSET `leaderboard:equity`, scores as integer cents (negatives sort correctly).
`update_score` is best-effort; `rebuild` recomputes every account's equity from Postgres +
cached prices and also reconciles `positions:open:{pair}`.
