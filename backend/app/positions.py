"""Leveraged-position execution — open and close, the one place the position invariants are
enforced together: idempotency, price freshness, tradability, free-cash sufficiency, row
locking, and the position + ledger + balance write as one atomic transaction per call.

`close_position` is shared by three callers: the HTTP route (user close), the per-tick
liquidation scan (`app.price_stream`) and the bankruptcy path (`app.bankruptcy`, via
`_settle_position`). A position goes `open -> closed | liquidated` exactly once, under a
`SELECT ... FOR UPDATE` on the position row — which is what makes concurrent close vs.
liquidation, and retried closes, safe without a second idempotency key.

Concurrency tests call `open_position` / `close_position` directly from independent
AsyncSession instances under `asyncio.gather` to exercise real row locking — see
backend/tests/test_positions_concurrency.py.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, cast

import httpx
import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import position_index
from app import positions_math as pm
from app.config import Settings
from app.market_data.cache import get_latest_ticker
from app.market_data.kraken import KrakenError, get_pair_status
from app.market_data.pricing import StalePriceError
from app.models import LedgerEntry, Position, User

logger = logging.getLogger(__name__)

CENT = Decimal("0.01")
PRICE_QUANTUM = Decimal("0.00000001")

CloseReason = Literal["user", "liquidation", "bankruptcy"]
OpenRejectionReason = Literal[
    "leverage_not_allowed",
    "below_min_collateral",
    "position_exists",
    "insufficient_free_cash",
    "stale_price",
    "pair_not_tradable",
]


class PositionRejectedError(Exception):
    """A definitive "no" to an open request — nothing is persisted, the idempotency key is
    not consumed, and the route maps `reason` to a 4xx with per-reason copy.
    """

    def __init__(self, reason: OpenRejectionReason) -> None:
        self.reason = reason
        super().__init__(reason)


class PositionNotFoundError(Exception):
    """No open-or-closed position with that id belongs to this user (route → 404)."""

    def __init__(self, position_id: uuid.UUID) -> None:
        self.position_id = position_id
        super().__init__(str(position_id))


class MarketDataUnavailableError(RuntimeError):
    """The provider gave no definitive answer (unreachable / unparseable). Nothing is
    persisted; the route returns 503 and the caller should retry with the same key.
    """


def quantize_cash(amount: Decimal) -> Decimal:
    """Round a computed cash amount to whole cents. Decision: ROUND_HALF_UP for all
    server-computed money quantization (unchanged from the spot model).
    """
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def _base_asset(pair: str) -> str:
    return pair.split("/", 1)[0]


def _open_fee(collateral: Decimal, leverage: int, taker_fee_bps: int) -> Decimal:
    return quantize_cash(
        pm.notional(collateral, leverage) * Decimal(taker_fee_bps) / Decimal(10000)
    )


async def open_position(
    db: AsyncSession,
    redis_client: redis.Redis,
    settings: Settings,
    *,
    user_id: uuid.UUID,
    idempotency_key: str,
    pair: str,
    side: pm.PositionSide,
    collateral: Decimal,
    leverage: int,
) -> Position:
    """Open (or replay) one leveraged position for `user_id`. `pair` must be a validated
    canonical USD pair and `collateral` a positive Decimal — the caller's job.

    Returns the persisted open Position, or — on a duplicate `(user_id, idempotency_key)` —
    the original row unchanged (business logic never re-evaluated). Raises
    `PositionRejectedError` for a business "no", `MarketDataUnavailableError` (persisting
    nothing) when the provider couldn't be reached.
    """
    existing = await db.scalar(
        select(Position).where(
            Position.user_id == user_id, Position.idempotency_key == idempotency_key
        )
    )
    if existing is not None:
        return existing

    if leverage not in settings.leverage_presets:
        raise PositionRejectedError("leverage_not_allowed")
    if collateral < settings.min_collateral:
        raise PositionRejectedError("below_min_collateral")

    # Market data BEFORE any lock — keeps the locked section down to the cash check + write.
    try:
        ticker = await get_latest_ticker(
            redis_client,
            pair,
            base_url=settings.kraken_rest_base_url,
            timeout=settings.kraken_request_timeout_seconds,
            max_age_seconds=settings.price_max_age_seconds,
        )
    except StalePriceError as exc:
        raise PositionRejectedError("stale_price") from exc
    except (KrakenError, httpx.HTTPError) as exc:
        raise MarketDataUnavailableError(
            f"could not fetch a price for {pair}: {exc}"
        ) from exc

    try:
        pair_status = await get_pair_status(
            pair,
            base_url=settings.kraken_rest_base_url,
            timeout=settings.kraken_request_timeout_seconds,
        )
    except (KrakenError, httpx.HTTPError) as exc:
        raise MarketDataUnavailableError(
            f"could not fetch tradability for {pair}: {exc}"
        ) from exc
    if not pair_status.tradable:
        raise PositionRejectedError("pair_not_tradable")

    entry_price = ticker.last.quantize(PRICE_QUANTUM, rounding=ROUND_HALF_UP)
    size = pm.position_size(
        collateral=collateral, leverage=leverage, entry_price=entry_price
    )
    if size <= 0:
        raise PositionRejectedError("below_min_collateral")
    open_fee = _open_fee(collateral, leverage, settings.taker_fee_bps)
    liquidation_price = pm.liquidation_price(
        side=side,
        entry_price=entry_price,
        leverage=leverage,
        maintenance_margin_rate=settings.maintenance_margin_rate,
    )
    total_debit = quantize_cash(collateral + open_fee)

    user = (
        await db.execute(select(User).where(User.id == user_id).with_for_update())
    ).scalar_one()

    if total_debit > user.cash_balance:
        await db.rollback()
        raise PositionRejectedError("insufficient_free_cash")

    clash = await db.scalar(
        select(Position.id).where(
            Position.user_id == user_id,
            Position.pair == pair,
            Position.status == "open",
        )
    )
    if clash is not None:
        await db.rollback()
        raise PositionRejectedError("position_exists")

    position = Position(
        user_id=user_id,
        idempotency_key=idempotency_key,
        pair=pair,
        side=side,
        status="open",
        leverage=leverage,
        collateral=collateral,
        size=size,
        entry_price=entry_price,
        liquidation_price=liquidation_price,
        open_fee=open_fee,
        opened_at=datetime.now(UTC),
    )
    db.add(position)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        dup = await db.scalar(
            select(Position).where(
                Position.user_id == user_id,
                Position.idempotency_key == idempotency_key,
            )
        )
        if dup is not None:
            return dup
        clash = await db.scalar(
            select(Position.id).where(
                Position.user_id == user_id,
                Position.pair == pair,
                Position.status == "open",
            )
        )
        if clash is not None:
            raise PositionRejectedError("position_exists") from None
        raise

    user.cash_balance -= total_debit
    db.add(
        LedgerEntry(
            user_id=user_id,
            position_id=position.id,
            entry_type="position_open",
            cash_delta=-total_debit,
            cash_balance_after=user.cash_balance,
            symbol=_base_asset(pair),
            quantity_delta=size,
        )
    )
    await db.commit()
    await position_index.add_open_position(redis_client, pair, position.id)
    return position


@dataclass(frozen=True)
class Settlement:
    close_price: Decimal
    realized_pnl: Decimal
    close_fee: Decimal
    returned_cash: Decimal


def settle_position(
    position: Position,
    user: User,
    *,
    close_price: Decimal,
    reason: CloseReason,
    taker_fee_bps: int,
) -> Settlement:
    """Apply a close to session-attached `position` and `user` — no I/O, no commit, no
    ledger, no lock. Shared by `close_position` (route + liquidation) and `app.bankruptcy`.
    """
    realized_pnl = pm.unrealized_pnl(
        side=cast("pm.PositionSide", position.side),
        size=position.size,
        entry_price=position.entry_price,
        mark_price=close_price,
    )
    close_fee = _open_fee(position.collateral, position.leverage, taker_fee_bps)
    returned = pm.settlement_cash(
        collateral=position.collateral, realized_pnl=realized_pnl, close_fee=close_fee
    )
    position.status = "liquidated" if reason == "liquidation" else "closed"
    position.close_price = close_price
    position.close_fee = close_fee
    position.realized_pnl = realized_pnl
    position.close_reason = reason
    position.closed_at = datetime.now(UTC)
    user.cash_balance += returned
    return Settlement(close_price, realized_pnl, close_fee, returned)


async def _get_position(
    db: AsyncSession, user_id: uuid.UUID, position_id: uuid.UUID
) -> Position | None:
    position: Position | None = await db.scalar(
        select(Position).where(
            Position.id == position_id, Position.user_id == user_id
        )
    )
    return position


async def close_position(
    db: AsyncSession,
    redis_client: redis.Redis,
    settings: Settings,
    *,
    user_id: uuid.UUID,
    position_id: uuid.UUID,
    reason: Literal["user", "liquidation"],
    mark_override: Decimal | None = None,
) -> tuple[Position, bool]:
    """Close (or return the already-terminal) position. Locks the user row then the
    position row; a non-open position is returned unchanged (idempotent — safe from the
    route, the liquidation scan, and on retry).

    Returns `(position, closed_now)` — `closed_now` is True only when *this* call performed
    the transition, so the liquidation scan can avoid a duplicate notification when a user
    close (or an earlier tick) got there first.

    `mark_override` is the fresh tick price for a liquidation; a user close (None) fetches
    a fresh `last` under invariant 10 and raises `StalePriceError` if there isn't one.
    Tradability is *not* required to close (relaxed invariant 11 — reduce-only spirit).
    """
    # The position's pair never changes, so an unlocked read is enough to price a user
    # close; the authoritative status check happens under the lock below.
    preview = await _get_position(db, user_id, position_id)
    if preview is None:
        raise PositionNotFoundError(position_id)

    if mark_override is None:
        try:
            ticker = await get_latest_ticker(
                redis_client,
                preview.pair,
                base_url=settings.kraken_rest_base_url,
                timeout=settings.kraken_request_timeout_seconds,
                max_age_seconds=settings.price_max_age_seconds,
            )
        except StalePriceError:
            raise
        except (KrakenError, httpx.HTTPError) as exc:
            raise MarketDataUnavailableError(
                f"could not fetch a price for {preview.pair}: {exc}"
            ) from exc
        close_price = ticker.last
    else:
        close_price = mark_override

    # `populate_existing` forces these locked rows to overwrite whatever the unlocked
    # `preview` read (or a prior call in this session) put in the identity map — without it
    # a concurrent close/liquidation that already committed would be invisible and we'd
    # settle the position twice.
    user = (
        await db.execute(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    position = (
        await db.execute(
            select(Position)
            .where(Position.id == position_id, Position.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()

    if position is None:  # pragma: no cover - preview found it a moment ago
        await db.rollback()
        raise PositionNotFoundError(position_id)
    if position.status != "open":
        await db.rollback()
        terminal = await _get_position(db, user_id, position_id)
        assert terminal is not None
        return terminal, False

    settlement = settle_position(
        position,
        user,
        close_price=close_price.quantize(PRICE_QUANTUM, rounding=ROUND_HALF_UP),
        reason=reason,
        taker_fee_bps=settings.taker_fee_bps,
    )
    db.add(
        LedgerEntry(
            user_id=user_id,
            position_id=position.id,
            entry_type="liquidation" if reason == "liquidation" else "position_close",
            cash_delta=settlement.returned_cash,
            cash_balance_after=user.cash_balance,
            symbol=_base_asset(position.pair),
            quantity_delta=-position.size,
        )
    )
    await db.commit()
    await position_index.remove_open_position(
        redis_client, position.pair, position.id
    )
    return position, True
