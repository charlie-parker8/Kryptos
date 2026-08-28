"""Pure unit tests for app.ws_manager's fan-out/registry logic — no ASGI, no real WebSocket,
just recording test doubles, since httpx.AsyncClient's ASGITransport doesn't implement the
websocket protocol at all (confirmed while writing these: it 404s any /ws GET) and Starlette's
sync TestClient runs the app on a separate thread/event loop that our asyncpg connections
(loop-bound) can't safely cross. See tests/test_ws.py for the route-level equivalent.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.ws_manager import ConnectionManager
from app.ws_messages import (
    AccountUpdateMessage,
    CandleUpdateMessage,
    PriceTickMessage,
)


class _RecordingWebSocket:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[dict[str, object]] = []

    async def send_json(self, payload: dict[str, object]) -> None:
        if self.fail:
            raise RuntimeError("connection closed")
        self.sent.append(payload)


def _price_tick(pair: str = "BTC/USD") -> PriceTickMessage:
    return PriceTickMessage(
        pair=pair,
        bid=Decimal(1),
        ask=Decimal(2),
        last=Decimal("1.5"),
        as_of=datetime.now(UTC),
        broadcast_at=123,
    )


def _account_update() -> AccountUpdateMessage:
    return AccountUpdateMessage(
        free_cash=Decimal(100),
        equity=Decimal(100),
        total_unrealized_pnl=Decimal(0),
        positions=[],
        as_of=datetime.now(UTC),
    )


def _candle_update(pair: str = "BTC/USD") -> CandleUpdateMessage:
    return CandleUpdateMessage(
        pair=pair,
        interval=1,
        open_time=1_714_564_800,
        open=Decimal(100),
        high=Decimal(101),
        low=Decimal(99),
        close=Decimal("100.5"),
        volume=Decimal(1),
        closed=False,
        broadcast_at=123,
    )


def test_connect_then_disconnect_removes_the_user_entirely() -> None:
    manager = ConnectionManager()
    user_id = uuid.uuid4()
    ws = _RecordingWebSocket()

    manager.connect(user_id, ws)
    assert user_id in manager.connected_user_ids()

    manager.disconnect(user_id, ws)
    assert user_id not in manager.connected_user_ids()


def test_disconnecting_one_of_two_connections_keeps_the_user_registered() -> None:
    manager = ConnectionManager()
    user_id = uuid.uuid4()
    first, second = _RecordingWebSocket(), _RecordingWebSocket()
    manager.connect(user_id, first)
    manager.connect(user_id, second)

    manager.disconnect(user_id, first)

    assert user_id in manager.connected_user_ids()


@pytest.mark.asyncio
async def test_broadcast_price_tick_reaches_every_connected_user() -> None:
    manager = ConnectionManager()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    ws_a, ws_b = _RecordingWebSocket(), _RecordingWebSocket()
    manager.connect(user_a, ws_a)
    manager.connect(user_b, ws_b)

    await manager.broadcast_price_tick(_price_tick())

    assert ws_a.sent[0]["type"] == "price_tick"
    assert ws_b.sent[0]["type"] == "price_tick"


@pytest.mark.asyncio
async def test_broadcast_candle_update_reaches_every_connected_user() -> None:
    manager = ConnectionManager()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    ws_a, ws_b = _RecordingWebSocket(), _RecordingWebSocket()
    manager.connect(user_a, ws_a)
    manager.connect(user_b, ws_b)

    await manager.broadcast_candle_update(_candle_update())

    assert ws_a.sent[0]["type"] == "candle_update"
    assert ws_b.sent[0]["type"] == "candle_update"


@pytest.mark.asyncio
async def test_send_account_update_only_reaches_the_target_user() -> None:
    manager = ConnectionManager()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    ws_a, ws_b = _RecordingWebSocket(), _RecordingWebSocket()
    manager.connect(user_a, ws_a)
    manager.connect(user_b, ws_b)

    await manager.send_account_update(user_a, _account_update())

    assert len(ws_a.sent) == 1
    assert ws_a.sent[0]["type"] == "account_update"
    assert ws_b.sent == []


@pytest.mark.asyncio
async def test_send_account_update_to_a_disconnected_user_is_a_noop() -> None:
    manager = ConnectionManager()

    await manager.send_account_update(uuid.uuid4(), _account_update())  # must not raise


@pytest.mark.asyncio
async def test_a_broken_connection_is_dropped_without_breaking_the_rest_of_the_broadcast() -> None:
    manager = ConnectionManager()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    broken, healthy = _RecordingWebSocket(fail=True), _RecordingWebSocket()
    manager.connect(user_a, broken)
    manager.connect(user_b, healthy)

    await manager.broadcast_price_tick(_price_tick())

    assert healthy.sent  # still received it despite user_a's connection failing
    assert user_a not in manager.connected_user_ids()
