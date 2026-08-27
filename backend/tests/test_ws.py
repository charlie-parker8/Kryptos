"""Route-level tests for app.routers.ws's portfolio_ws — calling the handler function
directly with a fake WebSocket double (see tests/test_ws_manager.py's module docstring for
why: ASGITransport doesn't implement the websocket protocol, and Starlette's sync TestClient
runs on a separate event loop our asyncpg connections can't safely cross). This still
exercises the real auth lookup, real DB session, real Redis, and real Pydantic
serialization — only the transport is faked.
"""

import asyncio
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import redis.asyncio as redis
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import candle_stream
from app.deps import SESSION_COOKIE_NAME
from app.market_data.fake import FakeMarketData
from app.market_data.kraken import Candle
from app.price_stream import handle_tick
from app.routers.ws import portfolio_ws


class FakeWebSocket:
    def __init__(
        self,
        cookies: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.cookies = cookies or {}
        self.headers = headers or {}
        self.accepted = False
        self.closed_code: int | None = None
        self.sent: list[dict[str, object]] = []
        # Set the moment the handler reaches its blocking receive() loop — i.e. once
        # connect()/the initial snapshot send have already happened — so a test can
        # deterministically wait for "fully set up" before acting, regardless of how many
        # real awaits (DB, Redis) happen in between.
        self.ready = asyncio.Event()
        self._disconnect = asyncio.Event()

    async def accept(self) -> None:
        self.accepted = True

    async def close(self, code: int = 1000) -> None:
        self.closed_code = code

    async def send_json(self, payload: dict[str, object]) -> None:
        self.sent.append(payload)

    async def receive(self) -> dict[str, object]:
        # Real Starlette WebSocket.receive() returns the raw ASGI message on a disconnect
        # rather than raising — it only raises WebSocketDisconnect from receive_text()/
        # receive_json(). Matching that exactly is what caught a real bug during manual
        # smoke testing: the route was relying on an exception this method never raises.
        self.ready.set()
        await self._disconnect.wait()
        return {"type": "websocket.disconnect", "code": 1000}

    def simulate_disconnect(self) -> None:
        self._disconnect.set()


def _headers(key: str | None = None) -> dict[str, str]:
    return {"Idempotency-Key": key or str(uuid.uuid4())}


async def _register(client: AsyncClient) -> dict[str, object]:
    response = await client.post(
        "/auth/register",
        json={
            "email": f"{uuid.uuid4()}@example.com",
            "username": f"u{uuid.uuid4().hex[:12]}",
            "password": "correct-horse-1",
        },
    )
    return response.json()


def _session_cookie(client: AsyncClient) -> str:
    return client.cookies[SESSION_COOKIE_NAME]


@pytest.mark.asyncio
async def test_ws_rejects_a_connection_without_a_session_cookie(
    redis_client: redis.Redis, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    fake_ws = FakeWebSocket()

    await portfolio_ws(
        fake_ws, session_factory=session_factory, redis_client=redis_client
    )

    assert fake_ws.accepted is False
    assert fake_ws.closed_code == 1008
    assert fake_ws.sent == []


@pytest.mark.asyncio
async def test_ws_rejects_a_connection_with_a_bogus_session_cookie(
    redis_client: redis.Redis, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    fake_ws = FakeWebSocket(cookies={SESSION_COOKIE_NAME: "not-a-real-token"})

    await portfolio_ws(
        fake_ws, session_factory=session_factory, redis_client=redis_client
    )

    assert fake_ws.accepted is False
    assert fake_ws.closed_code == 1008


@pytest.mark.asyncio
async def test_ws_sends_an_initial_portfolio_update_on_connect(
    client: AsyncClient,
    redis_client: redis.Redis,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await _register(client)
    fake_ws = FakeWebSocket(cookies={SESSION_COOKIE_NAME: _session_cookie(client)})

    task = asyncio.create_task(
        portfolio_ws(fake_ws, session_factory=session_factory, redis_client=redis_client)
    )
    await fake_ws.ready.wait()
    fake_ws.simulate_disconnect()
    await task

    assert fake_ws.accepted is True
    assert fake_ws.sent[0]["type"] == "portfolio_update"
    assert Decimal(str(fake_ws.sent[0]["cash_balance"])) == Decimal(
        str(user["cash_balance"])
    )
    assert fake_ws.sent[0]["holdings"] == []


@pytest.mark.asyncio
async def test_ws_receives_a_portfolio_update_after_an_order_fills(
    client: AsyncClient,
    fake_market_data: FakeMarketData,
    redis_client: redis.Redis,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _register(client)
    fake_market_data.set_price(
        "BTC/USD", bid=Decimal(50000), ask=Decimal(50000), last=Decimal(50000)
    )
    fake_ws = FakeWebSocket(cookies={SESSION_COOKIE_NAME: _session_cookie(client)})

    task = asyncio.create_task(
        portfolio_ws(fake_ws, session_factory=session_factory, redis_client=redis_client)
    )
    await fake_ws.ready.wait()
    assert len(fake_ws.sent) == 1  # just the initial snapshot so far

    await client.post(
        "/orders",
        json={"symbol": "BTC/USD", "side": "buy", "quantity": "0.1"},
        headers=_headers(),
    )

    fake_ws.simulate_disconnect()
    await task

    assert len(fake_ws.sent) == 2
    pushed = fake_ws.sent[1]
    assert pushed["type"] == "portfolio_update"
    assert len(pushed["holdings"]) == 1
    assert pushed["holdings"][0]["symbol"] == "BTC"


@pytest.mark.asyncio
async def test_ws_receives_a_simulated_price_tick_with_broadcast_at(
    client: AsyncClient,
    fake_market_data: FakeMarketData,
    redis_client: redis.Redis,
    session_factory: async_sessionmaker[AsyncSession],
    test_settings: object,
) -> None:
    await _register(client)
    fake_ws = FakeWebSocket(cookies={SESSION_COOKIE_NAME: _session_cookie(client)})

    task = asyncio.create_task(
        portfolio_ws(fake_ws, session_factory=session_factory, redis_client=redis_client)
    )
    await fake_ws.ready.wait()

    ticker = await fake_market_data.get_ticker("BTC/USD")
    await handle_tick(ticker, test_settings, redis_client, session_factory)

    fake_ws.simulate_disconnect()
    await task

    assert len(fake_ws.sent) == 2
    tick_message = fake_ws.sent[1]
    assert tick_message["type"] == "price_tick"
    assert tick_message["pair"] == "BTC/USD"
    assert isinstance(tick_message["broadcast_at"], int)
    assert tick_message["broadcast_at"] > 0


@pytest.mark.asyncio
async def test_ws_receives_a_candle_update_frame(
    client: AsyncClient,
    fake_market_data: FakeMarketData,
    redis_client: redis.Redis,
    session_factory: async_sessionmaker[AsyncSession],
    test_settings: object,
) -> None:
    candle_stream.reset_forming_throttle()
    await _register(client)
    fake_ws = FakeWebSocket(cookies={SESSION_COOKIE_NAME: _session_cookie(client)})

    task = asyncio.create_task(
        portfolio_ws(fake_ws, session_factory=session_factory, redis_client=redis_client)
    )
    await fake_ws.ready.wait()

    candle = Candle(
        pair="BTC/USD",
        interval=1,
        open_time=datetime(2024, 5, 1, 12, 0, tzinfo=UTC),
        open=Decimal(100),
        high=Decimal(101),
        low=Decimal(99),
        close=Decimal("100.5"),
        volume=Decimal(1),
    )
    await candle_stream.handle_candle(candle, test_settings, redis_client)

    fake_ws.simulate_disconnect()
    await task

    assert len(fake_ws.sent) == 2
    candle_message = fake_ws.sent[1]
    assert candle_message["type"] == "candle_update"
    assert candle_message["pair"] == "BTC/USD"
    assert candle_message["interval"] == 1
    assert candle_message["closed"] is False
    assert candle_message["open_time"] == int(candle.open_time.timestamp())
    assert isinstance(candle_message["broadcast_at"], int)
