from decimal import Decimal

from app.trading import quantize_cash, weighted_average_cost


def test_quantize_cash_rounds_half_up_at_the_half_cent() -> None:
    assert quantize_cash(Decimal("100.005")) == Decimal("100.01")


def test_quantize_cash_rounds_down_below_the_half_cent() -> None:
    assert quantize_cash(Decimal("100.004")) == Decimal("100.00")


def test_weighted_average_cost_on_first_buy_equals_fill_price() -> None:
    result = weighted_average_cost(
        existing_quantity=Decimal(0),
        existing_average_cost=Decimal(0),
        fill_quantity=Decimal("0.5"),
        fill_price=Decimal("60000.00000000"),
    )
    assert result == Decimal("60000.00000000")


def test_weighted_average_cost_blends_across_two_equal_size_buys() -> None:
    result = weighted_average_cost(
        existing_quantity=Decimal(1),
        existing_average_cost=Decimal("50000.00000000"),
        fill_quantity=Decimal(1),
        fill_price=Decimal("60000.00000000"),
    )
    assert result == Decimal("55000.00000000")


def test_weighted_average_cost_rounds_half_up_to_eight_places() -> None:
    # (1*1 + 2*2) / 3 = 1.666666... -> half-up at the 8th place
    result = weighted_average_cost(
        existing_quantity=Decimal(1),
        existing_average_cost=Decimal(1),
        fill_quantity=Decimal(2),
        fill_price=Decimal(2),
    )
    assert result == Decimal("1.66666667")
