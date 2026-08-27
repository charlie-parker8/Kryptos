"""Pydantic schemas for the two message types app.routers.ws pushes over `/ws`. Kept separate
from app.portfolio so the WS-only concerns (a `type` discriminator, `broadcast_at`) don't leak
into the plain REST `PortfolioSnapshot` response shape those messages otherwise mirror exactly.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.portfolio import PortfolioSnapshot


class PriceTickMessage(BaseModel):
    type: Literal["price_tick"] = "price_tick"
    pair: str
    bid: Decimal
    ask: Decimal
    last: Decimal
    as_of: datetime
    broadcast_at: int  # unix ms — docs/metrics-benchmark-plan.md Milestone A measures against this


class PortfolioUpdateMessage(PortfolioSnapshot):
    type: Literal["portfolio_update"] = "portfolio_update"


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
    """Pushed to one user's connections when their net worth hit $0 and the account was
    reset (see app.bankruptcy). A `portfolio_update` with the restored balances follows.
    """

    type: Literal["bankruptcy_reset"] = "bankruptcy_reset"
    starting_cash_balance: Decimal
    cleared_symbols: list[str]
    reset_at: datetime
