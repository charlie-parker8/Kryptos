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


class BankruptcyResetMessage(BaseModel):
    """Pushed to one user's connections when their net worth hit $0 and the account was
    reset (see app.bankruptcy). A `portfolio_update` with the restored balances follows.
    """

    type: Literal["bankruptcy_reset"] = "bankruptcy_reset"
    starting_cash_balance: Decimal
    cleared_symbols: list[str]
    reset_at: datetime
