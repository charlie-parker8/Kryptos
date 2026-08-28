"""Pure position math — Decimal in, Decimal out, no I/O.

Kept separate from app.positions (which does the DB + Redis work) so the P&L, margin and
liquidation formulas can be unit-tested without a database or a network.

There is one price in this model: the Kraken `last` price. Entry, mark, exit and the stored
`liquidation_price` all use it — no bid/ask spread. Money quantizes to whole cents
ROUND_HALF_UP; sizes quantize to 10 dp ROUND_DOWN so realized notional never exceeds
`collateral * leverage`.
"""

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Literal

PositionSide = Literal["long", "short"]

CENT = Decimal("0.01")
SIZE_QUANTUM = Decimal("0.0000000001")  # 10 dp — matches positions.size Numeric(28, 10)
PRICE_QUANTUM = Decimal("0.00000001")  # 8 dp — matches positions.*_price Numeric(20, 8)


def notional(collateral: Decimal, leverage: int) -> Decimal:
    """Position size in USD: what the collateral controls at `leverage`."""
    return collateral * leverage


def position_size(
    *, collateral: Decimal, leverage: int, entry_price: Decimal
) -> Decimal:
    """Base-asset quantity the collateral controls. Rounded DOWN to 10 dp so
    `size * entry_price` can't exceed `collateral * leverage` (the leftover dust is ignored).
    """
    raw = notional(collateral, leverage) / entry_price
    return raw.quantize(SIZE_QUANTUM, rounding=ROUND_DOWN)


def unrealized_pnl(
    *,
    side: PositionSide,
    size: Decimal,
    entry_price: Decimal,
    mark_price: Decimal,
) -> Decimal:
    """Signed P&L at `mark_price`, quantized to cents. Long gains when price rises, short
    gains when it falls.
    """
    if side == "long":
        raw = size * (mark_price - entry_price)
    else:
        raw = size * (entry_price - mark_price)
    return raw.quantize(CENT, rounding=ROUND_HALF_UP)


def maintenance_margin(
    *, collateral: Decimal, leverage: int, maintenance_margin_rate: Decimal
) -> Decimal:
    """The equity floor below which a position is liquidated: `mmr * notional`."""
    return (notional(collateral, leverage) * maintenance_margin_rate).quantize(
        CENT, rounding=ROUND_HALF_UP
    )


def position_equity(*, collateral: Decimal, unrealized_pnl: Decimal) -> Decimal:
    """What the position is currently worth to the account: collateral plus its P&L."""
    return collateral + unrealized_pnl


def liquidation_price(
    *,
    side: PositionSide,
    entry_price: Decimal,
    leverage: int,
    maintenance_margin_rate: Decimal,
) -> Decimal:
    """The mark price at which `position_equity` would equal `maintenance_margin`.

    Long: equity = collateral + size*(P - entry), size = collateral*L/entry,
    MM = mmr*collateral*L. Setting equity = MM and solving gives

        P_liq = entry * (1 + mmr - 1/L)

    Short is symmetric: ``entry * (1 - mmr + 1/L)``.
    """
    inv_leverage = Decimal(1) / Decimal(leverage)
    if side == "long":
        factor = Decimal(1) + maintenance_margin_rate - inv_leverage
    else:
        factor = Decimal(1) - maintenance_margin_rate + inv_leverage
    liq = entry_price * factor
    if liq < PRICE_QUANTUM:
        # A <=1x long can drive the factor to <=0; the presets are all >=2x so this is only
        # a defensive floor to keep the stored value positive (CHECK ck_positions_*).
        return PRICE_QUANTUM
    return liq.quantize(PRICE_QUANTUM, rounding=ROUND_HALF_UP)


def is_liquidatable(
    *, side: PositionSide, mark_price: Decimal, liquidation_price: Decimal
) -> bool:
    """Cheap pre-check against the stored liquidation price (no lock needed)."""
    if side == "long":
        return mark_price <= liquidation_price
    return mark_price >= liquidation_price


def settlement_cash(
    *, collateral: Decimal, realized_pnl: Decimal, close_fee: Decimal
) -> Decimal:
    """Cash returned to free balance when a position closes: ``collateral + realized_pnl -
    close_fee``, floored at 0. Isolated margin — a loss larger than the collateral is
    absorbed by the house, never clawed back from the rest of the account's cash.
    """
    raw = collateral + realized_pnl - close_fee
    return raw if raw > Decimal(0) else Decimal("0.00")


def account_equity(
    *,
    cash_balance: Decimal,
    open_positions: list[tuple[Decimal, Decimal]],
) -> Decimal:
    """Total account value: free cash plus every open position's ``collateral +
    unrealized_pnl``. `open_positions` is a list of ``(collateral, unrealized_pnl)`` pairs.
    Can be negative (gap move past a liquidation price between ticks).
    """
    total = cash_balance
    for collateral, upnl in open_positions:
        total += collateral + upnl
    return total
