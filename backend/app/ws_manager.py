"""In-process WebSocket connection registry and fan-out. Per CLAUDE.md, the MVP uses in-process
fan-out — not Redis Pub/Sub — since WebSocket delivery is still the same process as everything
else; a module-level singleton (mirroring app.redis_client's pattern) so app.price_stream (price
tick fan-out, liquidation notifications) and app.routers.positions (post-open/close account push)
can both reach the same connections app.routers.ws registers, without importing from each other.
"""

import logging
import uuid

from fastapi import WebSocket

from app.ws_messages import (
    AccountUpdateMessage,
    BankruptcyResetMessage,
    CandleUpdateMessage,
    PositionUpdateMessage,
    PriceTickMessage,
)

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._by_user: dict[uuid.UUID, set[WebSocket]] = {}

    def connect(self, user_id: uuid.UUID, websocket: WebSocket) -> None:
        self._by_user.setdefault(user_id, set()).add(websocket)

    def disconnect(self, user_id: uuid.UUID, websocket: WebSocket) -> None:
        connections = self._by_user.get(user_id)
        if connections is None:
            return
        connections.discard(websocket)
        if not connections:
            del self._by_user[user_id]

    def connected_user_ids(self) -> list[uuid.UUID]:
        return list(self._by_user.keys())

    async def broadcast_price_tick(self, message: PriceTickMessage) -> None:
        """Prices aren't per-user — every connected client gets every tick."""
        await self._broadcast(message.model_dump(mode="json"))

    async def broadcast_candle_update(self, message: CandleUpdateMessage) -> None:
        """Candles aren't per-user — every connected client gets every update and keeps
        only the pair+interval its chart shows (mirrors broadcast_price_tick).
        """
        await self._broadcast(message.model_dump(mode="json"))

    async def send_account_update(
        self, user_id: uuid.UUID, message: AccountUpdateMessage
    ) -> None:
        await self._send_to_user(user_id, message.model_dump(mode="json"))

    async def send_position_update(
        self, user_id: uuid.UUID, message: PositionUpdateMessage
    ) -> None:
        await self._send_to_user(user_id, message.model_dump(mode="json"))

    async def send_bankruptcy_reset(
        self, user_id: uuid.UUID, message: BankruptcyResetMessage
    ) -> None:
        await self._send_to_user(user_id, message.model_dump(mode="json"))

    async def _broadcast(self, payload: dict[str, object]) -> None:
        for user_id, connections in list(self._by_user.items()):
            for websocket in list(connections):
                await self._send_or_disconnect(user_id, websocket, payload)

    async def _send_to_user(
        self, user_id: uuid.UUID, payload: dict[str, object]
    ) -> None:
        connections = self._by_user.get(user_id)
        if not connections:
            return
        for websocket in list(connections):
            await self._send_or_disconnect(user_id, websocket, payload)

    async def _send_or_disconnect(
        self, user_id: uuid.UUID, websocket: WebSocket, payload: dict[str, object]
    ) -> None:
        try:
            await websocket.send_json(payload)
        except Exception:
            logger.debug("dropping a broken websocket connection", exc_info=True)
            self.disconnect(user_id, websocket)


ws_manager = ConnectionManager()
