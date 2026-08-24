import pytest

from app.config import get_settings
from app.market_data.kraken import get_pair_status, get_ticker


@pytest.mark.network
@pytest.mark.asyncio
async def test_get_ticker_returns_a_real_live_price() -> None:
    settings = get_settings()
    ticker = await get_ticker(
        "BTC/USD",
        base_url=settings.kraken_rest_base_url,
        timeout=settings.kraken_request_timeout_seconds,
    )

    assert ticker.pair == "BTC/USD"
    assert ticker.bid > 0
    assert ticker.ask > 0
    assert ticker.bid <= ticker.ask
    assert ticker.last > 0


@pytest.mark.network
@pytest.mark.asyncio
async def test_get_pair_status_returns_a_real_live_status() -> None:
    settings = get_settings()
    status = await get_pair_status(
        "BTC/USD",
        base_url=settings.kraken_rest_base_url,
        timeout=settings.kraken_request_timeout_seconds,
    )

    assert status.pair == "BTC/USD"
    assert status.status
    assert status.tradable == (status.status == "online")
