"""Shared helpers for the leveraged-position test suites. Not collected by pytest (no
`test_` prefix); importable as `from helpers import ...` because pytest puts `tests/` on
sys.path (prepend import mode, no `tests/__init__.py`).
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import redis.asyncio as redis
from httpx import AsyncClient, Response
from mailer_capture import verification_token_for

from app.market_data.cache import set_cached_ticker
from app.market_data.fake import FakeMarketData
from app.market_data.kraken import Ticker

STARTING_CASH = Decimal("10000.00")


async def set_market_price(
    fake: FakeMarketData,
    redis_client: redis.Redis,
    pair: str,
    price: str | Decimal,
    *,
    age_seconds: float = 0.0,
) -> None:
    """Move both the fake provider and the warm Redis cache to `price` (single-price
    model — bid == ask == last), so a subsequent open/close/liquidation reads it.
    """
    p = Decimal(str(price))
    fake.set_price(pair, bid=p, ask=p, last=p)
    as_of = datetime.now(UTC).timestamp() - age_seconds
    await set_cached_ticker(
        redis_client,
        Ticker(
            pair=pair,
            bid=p,
            ask=p,
            last=p,
            as_of=datetime.fromtimestamp(as_of, UTC),
        ),
        ttl_seconds=300,
    )


def idem(key: str | None = None) -> dict[str, str]:
    return {"Idempotency-Key": key or str(uuid.uuid4())}


async def register(
    client: AsyncClient, *, verified: bool = True
) -> dict[str, object]:
    """Register a fresh account. `verified=True` (the default) also redeems the verification
    link from the captured email, so the caller can immediately open positions / rank on the
    leaderboard; pass `verified=False` to exercise the unverified state.
    """
    email = f"{uuid.uuid4()}@example.com"
    response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "username": f"u{uuid.uuid4().hex[:12]}",
            "password": "correct-horse-1",
        },
    )
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    if verified:
        confirm = await client.post(
            "/auth/verify/confirm", json={"token": verification_token_for(email)}
        )
        assert confirm.status_code == 200, confirm.text
        body = confirm.json()
    return body


async def open_position(
    client: AsyncClient,
    *,
    pair: str = "BTC/USD",
    side: str = "long",
    collateral: str = "1000",
    leverage: int = 10,
    key: str | None = None,
) -> Response:
    return await client.post(
        "/positions",
        json={
            "pair": pair,
            "side": side,
            "collateral": collateral,
            "leverage": leverage,
        },
        headers=idem(key),
    )


async def close_position(
    client: AsyncClient, position_id: str, *, key: str | None = None
) -> Response:
    return await client.post(
        f"/positions/{position_id}/close", headers=idem(key)
    )
