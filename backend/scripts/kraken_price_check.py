"""Manual connectivity spike: proves we can pull a real live price from Kraken.

Run with: uv run python scripts/kraken_price_check.py
"""

import asyncio
import json
import ssl

import truststore
import websockets

from app.config import get_settings
from app.market_data.kraken import get_ticker


async def check_rest() -> None:
    settings = get_settings()
    ticker = await get_ticker(
        "BTC/USD",
        base_url=settings.kraken_rest_base_url,
        timeout=settings.kraken_request_timeout_seconds,
    )
    print(
        f"[REST] {ticker.pair}: bid={ticker.bid} ask={ticker.ask} last={ticker.last} as_of={ticker.as_of}"
    )


async def check_websocket() -> None:
    settings = get_settings()
    # Same OS-trust-store rationale as the adapter's httpx client — see market_data/kraken.py.
    ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    async with websockets.connect(settings.kraken_ws_url, ssl=ssl_context) as ws:
        await ws.send(
            json.dumps(
                {
                    "method": "subscribe",
                    "params": {"channel": "ticker", "symbol": ["BTC/USD"]},
                }
            )
        )
        for _ in range(5):
            message = await ws.recv()
            print(f"[WS] {message}")
            data = json.loads(message)
            if data.get("channel") == "ticker" and data.get("type") in (
                "snapshot",
                "update",
            ):
                break


async def main() -> None:
    await check_rest()
    await check_websocket()


if __name__ == "__main__":
    asyncio.run(main())
