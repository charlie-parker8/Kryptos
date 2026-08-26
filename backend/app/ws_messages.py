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
