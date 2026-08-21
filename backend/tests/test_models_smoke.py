import uuid
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Holding, LedgerEntry, Order, User


def _make_user(**overrides: object) -> User:
    defaults: dict[str, object] = {
        "email": f"{uuid.uuid4()}@example.com",
        "password_hash": "not-a-real-hash",
        "starting_cash_balance": Decimal("100000.00"),
        "cash_balance": Decimal("100000.00"),
    }
    defaults.update(overrides)
    return User(**defaults)


@pytest.mark.asyncio
async def test_insert_full_chain_succeeds(db_session: AsyncSession) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    holding = Holding(
        user_id=user.id,
        symbol="BTC",
        quantity=Decimal("0.5"),
        average_cost=Decimal("60000.00000000"),
    )
    order = Order(
        user_id=user.id,
        idempotency_key="order-1",
        symbol="BTC/USD",
        side="buy",
        status="filled",
        quantity=Decimal("0.5"),
        execution_price=Decimal("60000.00000000"),
    )
    db_session.add_all([holding, order])
    await db_session.flush()

    ledger_entry = LedgerEntry(
        user_id=user.id,
        order_id=order.id,
        entry_type="order_buy",
        cash_delta=Decimal("-30000.00"),
        cash_balance_after=Decimal("70000.00"),
        symbol="BTC",
        quantity_delta=Decimal("0.5"),
    )
    db_session.add(ledger_entry)
    await db_session.commit()

    assert user.id is not None
    assert holding.id is not None
    assert order.id is not None
    assert ledger_entry.id is not None


@pytest.mark.asyncio
async def test_duplicate_idempotency_key_rejected(db_session: AsyncSession) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    db_session.add(
        Order(
            user_id=user.id,
            idempotency_key="dup-key",
            symbol="BTC/USD",
            side="buy",
            quantity=Decimal("0.1"),
        )
    )
    await db_session.commit()

    db_session.add(
        Order(
            user_id=user.id,
            idempotency_key="dup-key",
            symbol="ETH/USD",
            side="sell",
            quantity=Decimal(1),
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_negative_cash_balance_rejected(db_session: AsyncSession) -> None:
    db_session.add(_make_user(cash_balance=Decimal("-1.00")))
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_non_usd_order_symbol_rejected(db_session: AsyncSession) -> None:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()

    db_session.add(
        Order(
            user_id=user.id,
            idempotency_key="bad-symbol",
            symbol="BTC/EUR",
            side="buy",
            quantity=Decimal("0.1"),
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
