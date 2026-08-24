import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.deps import SESSION_COOKIE_NAME
from app.models import User, UserSession
from app.security import hash_password, hash_session_token, verify_password


def _unique_email() -> str:
    return f"{uuid.uuid4()}@example.com"


@pytest.mark.asyncio
async def test_register_creates_user_with_configured_starting_balance(
    client: AsyncClient,
) -> None:
    email = _unique_email()
    response = await client.post(
        "/auth/register", json={"email": email, "password": "correct-horse-1"}
    )

    assert response.status_code == 201
    body = response.json()
    settings = get_settings()
    assert body["email"] == email
    assert Decimal(str(body["cash_balance"])) == settings.starting_cash_balance
    assert Decimal(str(body["starting_cash_balance"])) == settings.starting_cash_balance
    assert SESSION_COOKIE_NAME in response.cookies


@pytest.mark.asyncio
async def test_register_hashes_password_not_plaintext(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    email = _unique_email()
    password = "correct-horse-1"
    await client.post("/auth/register", json={"email": email, "password": password})

    user = await db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    assert user.password_hash != password
    assert user.password_hash.startswith("$2b$")
    assert verify_password(password, user.password_hash)


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(client: AsyncClient) -> None:
    email = _unique_email()
    payload = {"email": email, "password": "correct-horse-1"}

    first = await client.post("/auth/register", json=payload)
    assert first.status_code == 201

    second = await client.post(
        "/auth/register", json={"email": email, "password": "another-password-2"}
    )
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_register_rejects_short_password(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/register", json={"email": _unique_email(), "password": "short"}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_rejects_invalid_email(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/register",
        json={"email": "not-an-email", "password": "correct-horse-1"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_concurrent_duplicate_emails_only_one_succeeds(
    client: AsyncClient,
) -> None:
    email = _unique_email()
    payload = {"email": email, "password": "correct-horse-1"}

    responses = await asyncio.gather(
        client.post("/auth/register", json=payload),
        client.post("/auth/register", json=payload),
    )

    assert sorted(r.status_code for r in responses) == [201, 409]


@pytest.mark.asyncio
async def test_login_succeeds_with_correct_credentials(client: AsyncClient) -> None:
    email = _unique_email()
    password = "correct-horse-1"
    await client.post("/auth/register", json={"email": email, "password": password})

    response = await client.post(
        "/auth/login", json={"email": email, "password": password}
    )

    assert response.status_code == 200
    assert response.json()["email"] == email
    assert SESSION_COOKIE_NAME in response.cookies


@pytest.mark.asyncio
async def test_login_rejects_wrong_password(client: AsyncClient) -> None:
    email = _unique_email()
    await client.post(
        "/auth/register", json={"email": email, "password": "correct-horse-1"}
    )

    response = await client.post(
        "/auth/login", json={"email": email, "password": "wrong-password-1"}
    )

    assert response.status_code == 401
    assert SESSION_COOKIE_NAME not in response.cookies


@pytest.mark.asyncio
async def test_login_rejects_unknown_email_with_same_message_as_wrong_password(
    client: AsyncClient,
) -> None:
    known_email = _unique_email()
    await client.post(
        "/auth/register", json={"email": known_email, "password": "correct-horse-1"}
    )

    wrong_password = await client.post(
        "/auth/login", json={"email": known_email, "password": "wrong-password-1"}
    )
    unknown_email = await client.post(
        "/auth/login",
        json={"email": _unique_email(), "password": "wrong-password-1"},
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json()["detail"] == unknown_email.json()["detail"]


@pytest.mark.asyncio
async def test_me_returns_current_user_with_valid_session(client: AsyncClient) -> None:
    email = _unique_email()
    await client.post(
        "/auth/register", json={"email": email, "password": "correct-horse-1"}
    )

    response = await client.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == email


@pytest.mark.asyncio
async def test_me_rejects_missing_session(client: AsyncClient) -> None:
    response = await client.get("/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_rejects_garbage_session_token(client: AsyncClient) -> None:
    client.cookies.set(SESSION_COOKIE_NAME, "not-a-real-token")
    response = await client.get("/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_rejects_expired_session(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = User(
        email=_unique_email(),
        password_hash=hash_password("correct-horse-1"),
        starting_cash_balance=Decimal("100000.00"),
        cash_balance=Decimal("100000.00"),
    )
    db_session.add(user)
    await db_session.flush()

    raw_token = f"expired-{uuid.uuid4()}"
    db_session.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_session_token(raw_token),
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    )
    await db_session.commit()

    client.cookies.set(SESSION_COOKIE_NAME, raw_token)
    response = await client.get("/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_rejects_revoked_session(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = User(
        email=_unique_email(),
        password_hash=hash_password("correct-horse-1"),
        starting_cash_balance=Decimal("100000.00"),
        cash_balance=Decimal("100000.00"),
    )
    db_session.add(user)
    await db_session.flush()

    raw_token = f"revoked-{uuid.uuid4()}"
    db_session.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_session_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(days=1),
            revoked_at=datetime.now(UTC),
        )
    )
    await db_session.commit()

    client.cookies.set(SESSION_COOKIE_NAME, raw_token)
    response = await client.get("/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_session(client: AsyncClient) -> None:
    email = _unique_email()
    await client.post(
        "/auth/register", json={"email": email, "password": "correct-horse-1"}
    )

    logout_response = await client.post("/auth/logout")
    assert logout_response.status_code == 204

    me_response = await client.get("/auth/me")
    assert me_response.status_code == 401


@pytest.mark.asyncio
async def test_logout_without_session_is_a_no_op(client: AsyncClient) -> None:
    response = await client.post("/auth/logout")
    assert response.status_code == 204
