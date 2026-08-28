"""Pure position math — no DB, no network. Verifies the P&L / margin / liquidation formulas
that app.positions, app.account and app.bankruptcy all lean on.
"""

from decimal import Decimal

import pytest

from app import positions_math as pm

MMR = Decimal("0.005")


def test_notional_is_collateral_times_leverage() -> None:
    assert pm.notional(Decimal("1000.00"), 10) == Decimal("10000.00")


def test_position_size_divides_notional_by_entry() -> None:
    size = pm.position_size(
        collateral=Decimal(1000), leverage=10, entry_price=Decimal(50000)
    )
    assert size == Decimal("0.2000000000")


def test_position_size_rounds_down_so_notional_is_never_exceeded() -> None:
    size = pm.position_size(
        collateral=Decimal(10), leverage=3, entry_price=Decimal(7)
    )
    assert size == Decimal("4.2857142857")
    assert size * Decimal(7) <= Decimal(30)


def test_unrealized_pnl_long_gains_when_price_rises() -> None:
    upnl = pm.unrealized_pnl(
        side="long",
        size=Decimal("0.2"),
        entry_price=Decimal(50000),
        mark_price=Decimal(55000),
    )
    assert upnl == Decimal("1000.00")


def test_unrealized_pnl_short_gains_when_price_falls() -> None:
    upnl = pm.unrealized_pnl(
        side="short",
        size=Decimal("0.2"),
        entry_price=Decimal(50000),
        mark_price=Decimal(45000),
    )
    assert upnl == Decimal("1000.00")


def test_unrealized_pnl_short_loses_when_price_rises() -> None:
    upnl = pm.unrealized_pnl(
        side="short",
        size=Decimal("0.2"),
        entry_price=Decimal(50000),
        mark_price=Decimal(55000),
    )
    assert upnl == Decimal("-1000.00")


def test_unrealized_pnl_quantizes_to_cents_half_up() -> None:
    upnl = pm.unrealized_pnl(
        side="long",
        size=Decimal("0.0000000001"),
        entry_price=Decimal(0),
        mark_price=Decimal("50000.5"),
    )
    # 0.0000000001 * 50000.5 = 0.00000500005 -> 0.01? no: rounds to 0.00
    assert upnl == Decimal("0.00")


def test_maintenance_margin_is_rate_times_notional() -> None:
    mm = pm.maintenance_margin(
        collateral=Decimal(1000), leverage=10, maintenance_margin_rate=MMR
    )
    assert mm == Decimal("50.00")


@pytest.mark.parametrize("leverage", [2, 5, 10])
def test_long_liquidation_price_drives_equity_to_maintenance_margin(
    leverage: int,
) -> None:
    collateral = Decimal(1000)
    entry = Decimal(50000)
    liq = pm.liquidation_price(
        side="long",
        entry_price=entry,
        leverage=leverage,
        maintenance_margin_rate=MMR,
    )
    size = pm.position_size(
        collateral=collateral, leverage=leverage, entry_price=entry
    )
    upnl = pm.unrealized_pnl(
        side="long", size=size, entry_price=entry, mark_price=liq
    )
    equity = pm.position_equity(collateral=collateral, unrealized_pnl=upnl)
    mm = pm.maintenance_margin(
        collateral=collateral, leverage=leverage, maintenance_margin_rate=MMR
    )
    assert abs(equity - mm) <= Decimal("0.02")


@pytest.mark.parametrize("leverage", [2, 5, 10])
def test_short_liquidation_price_drives_equity_to_maintenance_margin(
    leverage: int,
) -> None:
    collateral = Decimal(1000)
    entry = Decimal(50000)
    liq = pm.liquidation_price(
        side="short",
        entry_price=entry,
        leverage=leverage,
        maintenance_margin_rate=MMR,
    )
    size = pm.position_size(
        collateral=collateral, leverage=leverage, entry_price=entry
    )
    upnl = pm.unrealized_pnl(
        side="short", size=size, entry_price=entry, mark_price=liq
    )
    equity = pm.position_equity(collateral=collateral, unrealized_pnl=upnl)
    mm = pm.maintenance_margin(
        collateral=collateral, leverage=leverage, maintenance_margin_rate=MMR
    )
    assert abs(equity - mm) <= Decimal("0.02")


def test_long_liquidation_is_below_entry_short_is_above() -> None:
    entry = Decimal(50000)
    long_liq = pm.liquidation_price(
        side="long", entry_price=entry, leverage=10, maintenance_margin_rate=MMR
    )
    short_liq = pm.liquidation_price(
        side="short", entry_price=entry, leverage=10, maintenance_margin_rate=MMR
    )
    assert long_liq == Decimal("45250.00000000")
    assert short_liq == Decimal("54750.00000000")


def test_is_liquidatable_long() -> None:
    assert pm.is_liquidatable(
        side="long", mark_price=Decimal(45250), liquidation_price=Decimal(45250)
    )
    assert pm.is_liquidatable(
        side="long", mark_price=Decimal(45000), liquidation_price=Decimal(45250)
    )
    assert not pm.is_liquidatable(
        side="long", mark_price=Decimal(45300), liquidation_price=Decimal(45250)
    )


def test_is_liquidatable_short() -> None:
    assert pm.is_liquidatable(
        side="short", mark_price=Decimal(54750), liquidation_price=Decimal(54750)
    )
    assert pm.is_liquidatable(
        side="short", mark_price=Decimal(55000), liquidation_price=Decimal(54750)
    )
    assert not pm.is_liquidatable(
        side="short", mark_price=Decimal(54700), liquidation_price=Decimal(54750)
    )


def test_settlement_cash_returns_collateral_plus_pnl() -> None:
    assert pm.settlement_cash(
        collateral=Decimal(1000),
        realized_pnl=Decimal(-950),
        close_fee=Decimal(0),
    ) == Decimal(50)
    assert pm.settlement_cash(
        collateral=Decimal(1000),
        realized_pnl=Decimal(500),
        close_fee=Decimal(0),
    ) == Decimal(1500)


def test_settlement_cash_floors_at_zero_on_a_loss_beyond_collateral() -> None:
    assert pm.settlement_cash(
        collateral=Decimal(1000),
        realized_pnl=Decimal(-1200),
        close_fee=Decimal(0),
    ) == Decimal("0.00")


def test_account_equity_sums_free_cash_and_open_positions() -> None:
    equity = pm.account_equity(
        cash_balance=Decimal(5000),
        open_positions=[
            (Decimal(1000), Decimal(250)),
            (Decimal(2000), Decimal(-300)),
        ],
    )
    assert equity == Decimal(7950)


def test_account_equity_can_go_negative() -> None:
    equity = pm.account_equity(
        cash_balance=Decimal(0),
        open_positions=[(Decimal(1000), Decimal(-1500))],
    )
    assert equity == Decimal(-500)
