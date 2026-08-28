import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LedgerEntry, Position, User

STARTING_CASH = Decimal("10000.00")


def _make_user(**overrides: object) -> User:
    defaults: dict[str, object] = {
        "email": f"{uuid.uuid4()}@example.com",
        "username": f"u{uuid.uuid4().hex[:12]}",
        "password_hash": "not-a-real-hash",
        "starting_cash_balance": STARTING_CASH,
        "cash_balance": STARTING_CASH,
    }
    defaults.update(overrides)
    return User(**defaults)


def _make_position(user_id: uuid.UUID, **overrides: object) -> Position:
    defaults: dict[str, object] = {
        "user_id": user_id,
        "idempotency_key": f"open-{uuid.uuid4().hex[:8]}",
        "pair": "BTC/USD",
        "side": "long",
        "status": "open",
        "leverage": 10,
        "collateral": Decimal("1000.00"),
        "size": Decimal("0.2000000000"),
        "entry_price": Decimal("50000.00000000"),
        "liquidation_price": Decimal("45250.00000000"),
        "open_fee": Decimal("0.00"),
    }
    defaults.update(overrides)
    return Position(**defaults)


@pytest.mark.asyncio
async def test_insert_full_chain_succeeds(db_session: AsyncSession) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    position = _make_position(user.id)
    db_session.add(position)
    await db_session.flush()

    db_session.add(
        LedgerEntry(
            user_id=user.id,
            position_id=position.id,
            entry_type="position_open",
            cash_delta=Decimal("-1000.00"),
            cash_balance_after=Decimal("9000.00"),
            symbol="BTC",
            quantity_delta=Decimal("0.2"),
        )
    )
    await db_session.commit()

    assert position.id is not None


@pytest.mark.asyncio
async def test_duplicate_idempotency_key_rejected(db_session: AsyncSession) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    db_session.add(_make_position(user.id, idempotency_key="dup", pair="BTC/USD"))
    await db_session.commit()

    db_session.add(_make_position(user.id, idempotency_key="dup", pair="ETH/USD"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_second_open_position_on_same_pair_rejected(
    db_session: AsyncSession,
) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    db_session.add(_make_position(user.id, pair="BTC/USD"))
    await db_session.commit()

    db_session.add(_make_position(user.id, pair="BTC/USD"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_a_closed_position_frees_the_pair_for_a_new_open(
    db_session: AsyncSession,
) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    first = _make_position(
        user.id,
        pair="BTC/USD",
        status="closed",
        close_price=Decimal("51000.00000000"),
        close_fee=Decimal("0.00"),
        realized_pnl=Decimal("200.00"),
        close_reason="user",
        closed_at=datetime.now(UTC),
    )
    db_session.add(first)
    await db_session.commit()

    db_session.add(_make_position(user.id, pair="BTC/USD"))
    await db_session.commit()  # must not raise — the partial index only covers status='open'


@pytest.mark.asyncio
async def test_negative_cash_balance_rejected(db_session: AsyncSession) -> None:
    db_session.add(_make_user(cash_balance=Decimal("-1.00")))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_non_usd_position_pair_rejected(db_session: AsyncSession) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    db_session.add(_make_position(user.id, pair="BTC/EUR"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_invalid_side_rejected(db_session: AsyncSession) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    db_session.add(_make_position(user.id, side="buy"))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_non_positive_collateral_rejected(db_session: AsyncSession) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    db_session.add(_make_position(user.id, collateral=Decimal("0.00")))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_open_position_with_close_data_rejected(
    db_session: AsyncSession,
) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    db_session.add(
        _make_position(user.id, status="open", close_price=Decimal("1.0"))
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
