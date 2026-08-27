"""Deterministic stand-in for the Kraken adapter (app.market_data.kraken).

CLAUDE.md permits mock market data only for automated tests and offline development —
never in production. This is not wired behind any provider interface (CLAUDE.md also
warns against a generic "provider interface" beyond the one Kraken adapter); tests import
it directly in place of app.market_data.kraken. Each instance owns its own state so one
test's overrides (a stale quote, a paused pair) can never leak into another.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.market_data.kraken import Candle, PairStatus, Ticker

DEFAULT_TICKERS: dict[str, tuple[Decimal, Decimal, Decimal]] = {
    "BTC/USD": (Decimal("49995.00"), Decimal("50005.00"), Decimal("50000.00")),
}


@dataclass
class FakeMarketData:
    tickers: dict[str, tuple[Decimal, Decimal, Decimal]] = field(
        default_factory=lambda: dict(DEFAULT_TICKERS)
    )
    _as_of_overrides: dict[str, datetime] = field(default_factory=dict)
    _statuses: dict[str, str] = field(default_factory=dict)
    _candles: dict[tuple[str, int], list[Candle]] = field(default_factory=dict)

    def set_price(
        self, pair: str, *, bid: Decimal, ask: Decimal, last: Decimal
    ) -> None:
        self.tickers[pair] = (bid, ask, last)

    def set_stale(self, pair: str, *, age_seconds: float) -> None:
        """Back-date `pair`'s quote so a freshness check (invariant 10) rejects it."""
        self._as_of_overrides[pair] = datetime.now(UTC) - timedelta(seconds=age_seconds)

    def set_status(self, pair: str, status: str) -> None:
        """Simulate Kraken reporting `pair` as e.g. "cancel_only" or "maintenance"
        (invariant 11); any value other than "online" is treated as not tradable.
        """
        self._statuses[pair] = status

    async def get_ticker(self, pair: str) -> Ticker:
        if pair not in self.tickers:
            raise KeyError(f"no fake price seeded for {pair!r}; call set_price() first")
        bid, ask, last = self.tickers[pair]
        as_of = self._as_of_overrides.get(pair, datetime.now(UTC))
        return Ticker(pair=pair, bid=bid, ask=ask, last=last, as_of=as_of)

    async def get_pair_status(self, pair: str) -> PairStatus:
        status = self._statuses.get(pair, "online")
        return PairStatus(pair=pair, status=status, tradable=status == "online")

    def set_candles(self, pair: str, interval: int, candles: list[Candle]) -> None:
        """Seed the OHLC history `get_ohlc(pair, interval)` returns (oldest first,
        trailing row = still-forming bucket, matching Kraken's REST endpoint).
        """
        self._candles[(pair, interval)] = list(candles)

    async def get_ohlc(
        self, pair: str, interval: int, **_: object
    ) -> list[Candle]:
        return list(self._candles.get((pair, interval), []))
