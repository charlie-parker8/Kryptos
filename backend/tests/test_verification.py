import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app import verification
from app.models import EmailVerificationToken, User
from app.security import hash_session_token
from app.verification import VerifyResult


async def _user(db: AsyncSession, *, verified: bool = False) -> User:
    user = User(
        email=f"{uuid.uuid4()}@example.com",
        username=f"u{uuid.uuid4().hex[:12]}",
        password_hash="x",
        starting_cash_balance=Decimal("10000.00"),
        cash_balance=Decimal("10000.00"),
        email_verified_at=datetime.now(UTC) if verified else None,
    )
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_issue_then_consume_verifies(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    raw = await verification.issue_token(db_session, user.id)
    await db_session.commit()

    result, out = await verification.consume_token(db_session, raw)
    await db_session.commit()

    assert result is VerifyResult.OK
    assert out is not None and out.id == user.id
    assert user.email_verified_at is not None


@pytest.mark.asyncio
async def test_consume_is_single_use(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    raw = await verification.issue_token(db_session, user.id)
    await db_session.commit()

    await verification.consume_token(db_session, raw)
    await db_session.commit()
    result, _ = await verification.consume_token(db_session, raw)
    assert result is VerifyResult.INVALID


@pytest.mark.asyncio
async def test_consume_rejects_unknown_token(db_session: AsyncSession) -> None:
    result, out = await verification.consume_token(db_session, "does-not-exist")
    assert result is VerifyResult.INVALID and out is None


@pytest.mark.asyncio
async def test_consume_rejects_expired_token(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    raw = "expired-token-raw-value-1234"
    db_session.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_session_token(raw),
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    )
    await db_session.commit()

    result, _ = await verification.consume_token(db_session, raw)
    assert result is VerifyResult.INVALID


@pytest.mark.asyncio
async def test_second_token_when_already_verified_reports_already(
    db_session: AsyncSession,
) -> None:
    user = await _user(db_session)
    raw1 = await verification.issue_token(db_session, user.id)
    raw2 = await verification.issue_token(db_session, user.id)
    await db_session.commit()

    await verification.consume_token(db_session, raw1)
    await db_session.commit()
    result, out = await verification.consume_token(db_session, raw2)
    await db_session.commit()

    assert result is VerifyResult.ALREADY_VERIFIED and out is not None
