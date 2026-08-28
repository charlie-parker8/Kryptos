from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.market_data.kraken import Ticker
from app.market_data.pricing import StalePriceError, ensure_fresh, mark_price


def _ticker(**overrides: object) -> Ticker:
    defaults: dict[str, object] = {
        "pair": "BTC/USD",
        "bid": Decimal("49995.00"),
        "ask": Decimal("50005.00"),
        "last": Decimal("50000.00"),
        "as_of": datetime.now(UTC),
    }
    defaults.update(overrides)
    return Ticker(**defaults)  # type: ignore[arg-type]


def test_mark_price_is_last() -> None:
    ticker = _ticker()
    assert mark_price(ticker) == ticker.last
    assert mark_price(ticker) != ticker.bid
    assert mark_price(ticker) != ticker.ask


def test_ensure_fresh_accepts_quote_within_max_age() -> None:
    now = datetime.now(UTC)
    ticker = _ticker(as_of=now - timedelta(seconds=5))
    ensure_fresh(ticker, max_age_seconds=10, now=now)


def test_ensure_fresh_accepts_quote_exactly_at_max_age() -> None:
    now = datetime.now(UTC)
    ticker = _ticker(as_of=now - timedelta(seconds=10))
    ensure_fresh(ticker, max_age_seconds=10, now=now)


def test_ensure_fresh_rejects_quote_older_than_max_age() -> None:
    now = datetime.now(UTC)
    ticker = _ticker(as_of=now - timedelta(seconds=11))
    with pytest.raises(StalePriceError):
        ensure_fresh(ticker, max_age_seconds=10, now=now)
