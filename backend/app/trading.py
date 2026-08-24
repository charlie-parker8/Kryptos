"""Market order execution — the one place invariants 1-11 (12/bankruptcy is a later phase)
are enforced together: idempotency, price freshness/tradability, cash/holdings sufficiency,
row locking, and the order+ledger+balance write, all as one atomic transaction per call.

Two real call sites: app.routers.orders (HTTP) and tests/test_orders_concurrency.py, which
calls this directly from two independent AsyncSession instances to exercise real row
locking under asyncio.gather — the locking/idempotency/decimal logic is too intricate to
embed inline in a route handler and still unit/concurrency-test cleanly.
"""

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

import httpx
import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.market_data.cache import get_latest_ticker
from app.market_data.kraken import KrakenError, get_pair_status
from app.market_data.pricing import OrderSide, StalePriceError, executable_price
from app.models import Holding, LedgerEntry, Order, User

RejectionReason = Literal[
    "insufficient_funds", "insufficient_holdings", "stale_price", "pair_not_tradable"
]

CENT = Decimal("0.01")
COST_BASIS_QUANTUM = Decimal("0.00000001")  # matches holdings.average_cost's Numeric(20,8)


class MarketDataUnavailableError(RuntimeError):
    """The provider gave no definitive answer (unreachable, malformed response) — as
    opposed to a definitive "no" (stale price, not tradable). Nothing is persisted and the
    idempotency key is not consumed; callers should retry with the same key.
    """


def quantize_cash(amount: Decimal) -> Decimal:
    """Round a computed cash amount (buy cost / sell proceeds) to whole cents. Decision:
    ROUND_HALF_UP for all server-computed money quantization.
    """
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def weighted_average_cost(
    *,
    existing_quantity: Decimal,
    existing_average_cost: Decimal,
    fill_quantity: Decimal,
    fill_price: Decimal,
) -> Decimal:
    """New weighted-average cost after a buy fill (buys only — a sell never calls this;
    average_cost is untouched on sells). Quantized to holdings.average_cost's 8-decimal
    precision. Uses full-precision fill_price * fill_quantity, not the cents-rounded cash
    cost, so rounding error can't compound into the cost basis across repeated buys — only
    the cash_balance debit itself rounds to cents.
    """
    new_quantity = existing_quantity + fill_quantity
    numerator = existing_average_cost * existing_quantity + fill_price * fill_quantity
    return (numerator / new_quantity).quantize(COST_BASIS_QUANTUM, rounding=ROUND_HALF_UP)


async def execute_order(
    db: AsyncSession,
    redis_client: redis.Redis,
    settings: Settings,
    *,
    user_id: uuid.UUID,
    idempotency_key: str,
    symbol: str,
    side: OrderSide,
    quantity: Decimal,
) -> Order:
    """Execute (or replay) one market order for `user_id`. `symbol` must already be a
    validated canonical pair (e.g. "BTC/USD") and `quantity` a validated positive Decimal
    with <=10 decimal places — both are the caller's job (app.routers.orders validates via
    Pydantic before calling this; this function trusts its inputs).

    Returns the persisted Order — status "filled" or "rejected" — whenever the provider
    gave a definitive answer, including on a duplicate submission (same
    (user_id, idempotency_key)): the original order is returned unchanged, business logic
    never re-evaluated — a replay does not check whether the *new* request's symbol/side/
    quantity match the original. Raises MarketDataUnavailableError, persisting nothing,
    when the provider itself couldn't be reached or returned something unparseable.
    """
    existing = await db.scalar(
        select(Order).where(
            Order.user_id == user_id, Order.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        return existing

    # Market data BEFORE any lock — keeps the locked critical section down to just the
    # balance/holding check + write.
    try:
        ticker = await get_latest_ticker(
            redis_client,
            symbol,
            base_url=settings.kraken_rest_base_url,
            timeout=settings.kraken_request_timeout_seconds,
            max_age_seconds=settings.price_max_age_seconds,
        )
    except StalePriceError:
        return await _persist_rejected_order(
            db,
            user_id=user_id,
            idempotency_key=idempotency_key,
            symbol=symbol,
            side=side,
            quantity=quantity,
            reason="stale_price",
        )
    except (KrakenError, httpx.HTTPError) as exc:
        raise MarketDataUnavailableError(
            f"could not fetch a price for {symbol}: {exc}"
        ) from exc

    # Not cached this phase (pair-status caching deferred) — always a live call.
    try:
        pair_status = await get_pair_status(
            symbol,
            base_url=settings.kraken_rest_base_url,
            timeout=settings.kraken_request_timeout_seconds,
        )
    except (KrakenError, httpx.HTTPError) as exc:
        raise MarketDataUnavailableError(
            f"could not fetch tradability for {symbol}: {exc}"
        ) from exc

    if not pair_status.tradable:
        return await _persist_rejected_order(
            db,
            user_id=user_id,
            idempotency_key=idempotency_key,
            symbol=symbol,
            side=side,
            quantity=quantity,
            reason="pair_not_tradable",
        )

    price = executable_price(ticker, side).quantize(
        COST_BASIS_QUANTUM, rounding=ROUND_HALF_UP
    )
    base_asset = symbol.split("/", 1)[0]

    # Lock order is always user row, then holding row, for every order regardless of side
    # or symbol. Two orders touching the same user always request these two locks in the
    # same order, so contention serializes them (one blocks until the other commits or
    # rolls back) rather than deadlocking — a deadlock needs some transaction to acquire
    # them in the opposite order, which this code never does.
    user = (
        await db.execute(select(User).where(User.id == user_id).with_for_update())
    ).scalar_one()

    # Ensure-then-lock: SELECT ... FOR UPDATE on a row that doesn't exist yet locks
    # nothing, so a symbol traded for the first time needs its holding row created first.
    # ON CONFLICT DO NOTHING keeps this race-safe without ever raising inside the
    # transaction (a caught IntegrityError here would otherwise poison the transaction
    # without a SAVEPOINT).
    await db.execute(
        pg_insert(Holding)
        .values(
            id=uuid.uuid4(),
            user_id=user_id,
            symbol=base_asset,
            quantity=Decimal(0),
            average_cost=Decimal(0),
        )
        .on_conflict_do_nothing(constraint="uq_holdings_user_symbol")
    )
    holding = (
        await db.execute(
            select(Holding)
            .where(Holding.user_id == user_id, Holding.symbol == base_asset)
            .with_for_update()
        )
    ).scalar_one()

    if side == "buy":
        cost = quantize_cash(price * quantity)
        if cost > user.cash_balance:
            return await _persist_rejected_order(
                db,
                user_id=user_id,
                idempotency_key=idempotency_key,
                symbol=symbol,
                side=side,
                quantity=quantity,
                reason="insufficient_funds",
            )
    else:
        if quantity > holding.quantity:
            return await _persist_rejected_order(
                db,
                user_id=user_id,
                idempotency_key=idempotency_key,
                symbol=symbol,
                side=side,
                quantity=quantity,
                reason="insufficient_holdings",
            )
        proceeds = quantize_cash(price * quantity)

    order = Order(
        user_id=user_id,
        idempotency_key=idempotency_key,
        symbol=symbol,
        side=side,
        status="filled",
        quantity=quantity,
        execution_price=price,
        filled_at=datetime.now(UTC),
    )
    db.add(order)
    # This flush (needed now for order.id, the ledger row's FK) is where a concurrent
    # duplicate's unique-constraint violation actually surfaces: the other transaction was
    # blocked on the user-row lock above and only reaches its own insert after we've
    # already committed, so ITS insert fails immediately here, not at some later commit().
    # Must be caught at the flush, not deferred.
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return await _fetch_committed_duplicate(
            db, user_id=user_id, idempotency_key=idempotency_key
        )

    if side == "buy":
        new_average_cost = weighted_average_cost(
            existing_quantity=holding.quantity,
            existing_average_cost=holding.average_cost,
            fill_quantity=quantity,
            fill_price=price,
        )
        holding.quantity += quantity
        holding.average_cost = new_average_cost
        user.cash_balance -= cost
        cash_delta = -cost
        quantity_delta = quantity
        entry_type: Literal["order_buy", "order_sell"] = "order_buy"
    else:
        holding.quantity -= quantity
        user.cash_balance += proceeds
        cash_delta = proceeds
        quantity_delta = -quantity
        entry_type = "order_sell"

    db.add(
        LedgerEntry(
            user_id=user_id,
            order_id=order.id,
            entry_type=entry_type,
            cash_delta=cash_delta,
            cash_balance_after=user.cash_balance,
            symbol=base_asset,
            quantity_delta=quantity_delta,
        )
    )

    await db.commit()
    return order


async def _persist_rejected_order(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    idempotency_key: str,
    symbol: str,
    side: OrderSide,
    quantity: Decimal,
    reason: RejectionReason,
) -> Order:
    order = Order(
        user_id=user_id,
        idempotency_key=idempotency_key,
        symbol=symbol,
        side=side,
        status="rejected",
        quantity=quantity,
        rejection_reason=reason,
    )
    db.add(order)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return await _fetch_committed_duplicate(
            db, user_id=user_id, idempotency_key=idempotency_key
        )
    return order


async def _fetch_committed_duplicate(
    db: AsyncSession, *, user_id: uuid.UUID, idempotency_key: str
) -> Order:
    """After an IntegrityError on (user_id, idempotency_key), the concurrent request that
    got there first has already committed — fetch and return its row so every duplicate
    submission resolves to exactly one order.
    """
    existing = await db.scalar(
        select(Order).where(
            Order.user_id == user_id, Order.idempotency_key == idempotency_key
        )
    )
    if existing is None:  # pragma: no cover - defensive: constraint fired for another reason
        raise RuntimeError(
            f"uq_orders_user_idempotency_key violated for user_id={user_id!r} "
            f"idempotency_key={idempotency_key!r} but no committed order was found"
        )
    return existing
