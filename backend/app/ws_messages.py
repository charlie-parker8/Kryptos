"""Pydantic schemas for the messages app.routers.ws pushes over `/ws`. Kept separate from
app.account so the WS-only concerns (a `type` discriminator, `broadcast_at`) don't leak
into the plain REST `AccountSnapshot` response shape `account_update` otherwise mirrors.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.account import AccountSnapshot


class PriceTickMessage(BaseModel):
    type: Literal["price_tick"] = "price_tick"
    pair: str
    bid: Decimal
    ask: Decimal
    last: Decimal
    as_of: datetime
    broadcast_at: int  # unix ms — docs/metrics-benchmark-plan.md Milestone A measures against this


class AccountUpdateMessage(AccountSnapshot):
    """A per-user snapshot: free cash, derived equity, total unrealized P&L, and every open
    position valued at the latest `last` price. Sent on `/ws` connect, after an open or
    close, and per tick to users holding a position on the ticked pair.
    """

    type: Literal["account_update"] = "account_update"


class PositionUpdateMessage(BaseModel):
    """Sent to one user's connections when a position reaches a terminal state — a user
    close, an automatic liquidation, or a bankruptcy reset. Drives the blotter refresh and
    (for liquidations) a toast. An `account_update` with the new balances follows.
    """

    type: Literal["position_update"] = "position_update"
    position_id: uuid.UUID
    pair: str
    side: Literal["long", "short"]
    status: Literal["closed", "liquidated"]
    close_price: Decimal
    realized_pnl: Decimal
    reason: Literal["user", "liquidation", "bankruptcy"]
    at: datetime


class CandleUpdateMessage(BaseModel):
    """Broadcast to every connection (like PriceTickMessage — candles aren't per-user); the
    client keeps only the pair+interval its chart is showing. `closed` is True on the frame
    that finalises a bucket, False for the still-forming bar. See app.candle_stream.
    """

    type: Literal["candle_update"] = "candle_update"
    pair: str
    interval: int  # minutes
    open_time: int  # unix seconds — the bucket start (lightweight-charts `time`)
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    closed: bool
    broadcast_at: int  # unix ms — mirrors PriceTickMessage


class BankruptcyResetMessage(BaseModel):
    """Pushed to one user's connections when their account equity hit the floor and the
    account was reset (see app.bankruptcy). A `position_update` per closed position and an
    `account_update` with the restored balance follow.
    """

    type: Literal["bankruptcy_reset"] = "bankruptcy_reset"
    starting_cash_balance: Decimal
    closed_positions: list[str]  # pair strings, e.g. ["BTC/USD", "ETH/USD"]
    reset_at: datetime
