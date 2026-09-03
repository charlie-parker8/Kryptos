import uuid
from datetime import UTC, datetime, timedelta

import pytest
import redis.asyncio as redis
from httpx import AsyncClient
from mailer_capture import SentEmail, verification_token_for
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import leaderboard
from app.config import Settings
from app.models import EmailVerificationToken
from app.security import hash_session_token


async def _register_unverified(
    client: AsyncClient,
) -> tuple[str, dict[str, object]]:
    email = f"{uuid.uuid4()}@example.com"
    resp = await client.post(
        "/auth/register",
        json={
            "email": email,
            "username": f"u{uuid.uuid4().hex[:12]}",
            "password": "correct-horse-1",
        },
    )
    assert resp.status_code == 201, resp.text
    return email, resp.json()


@pytest.mark.asyncio
async def test_new_account_is_unverified(client: AsyncClient) -> None:
    await _register_unverified(client)
    me = await client.get("/auth/me")
    assert me.json()["email_verified"] is False


@pytest.mark.asyncio
async def test_register_sends_verification_email(
    client: AsyncClient, email_outbox: list[SentEmail]
) -> None:
    email, _ = await _register_unverified(client)
    assert any(s.to == email for s in email_outbox)
    assert "/verify?token=" in email_outbox[-1].text


@pytest.mark.asyncio
async def test_confirm_verifies_and_is_single_use(client: AsyncClient) -> None:
    email, _ = await _register_unverified(client)
    token = verification_token_for(email)

    first = await client.post("/auth/verify/confirm", json={"token": token})
    assert first.status_code == 200
    assert first.json()["email_verified"] is True
    assert (await client.get("/auth/me")).json()["email_verified"] is True

    second = await client.post("/auth/verify/confirm", json={"token": token})
    assert second.status_code == 400


@pytest.mark.asyncio
async def test_confirm_rejects_unknown_token(client: AsyncClient) -> None:
    r = await client.post("/auth/verify/confirm", json={"token": "x" * 20})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_confirm_rejects_expired_token(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _email, body = await _register_unverified(client)
    raw = "expired-raw-token-value-000"
    db_session.add(
        EmailVerificationToken(
            user_id=uuid.UUID(str(body["id"])),
            token_hash=hash_session_token(raw),
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    )
    await db_session.commit()
    r = await client.post("/auth/verify/confirm", json={"token": raw})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_request_verification_resends_then_noop_when_verified(
    client: AsyncClient, email_outbox: list[SentEmail]
) -> None:
    email, _ = await _register_unverified(client)
    before = len(email_outbox)
    r = await client.post("/auth/verify/request")
    assert r.status_code == 202
    assert len(email_outbox) == before + 1

    await client.post(
        "/auth/verify/confirm", json={"token": verification_token_for(email)}
    )
    count = len(email_outbox)
    r = await client.post("/auth/verify/request")
    assert r.status_code == 202
    assert len(email_outbox) == count  # no new email


@pytest.mark.asyncio
async def test_request_verification_requires_auth(client: AsyncClient) -> None:
    assert (await client.post("/auth/verify/request")).status_code == 401


@pytest.mark.asyncio
async def test_verify_request_is_rate_limited(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.rate_limit

    frozen = 1_000_000.0
    monkeypatch.setattr(app.rate_limit.time, "time", lambda: frozen)
    await _register_unverified(client)
    codes = [
        (await client.post("/auth/verify/request")).status_code for _ in range(7)
    ]
    assert 429 in codes


@pytest.mark.asyncio
async def test_login_works_while_unverified(client: AsyncClient) -> None:
    email, _ = await _register_unverified(client)
    r = await client.post(
        "/auth/login", json={"email": email, "password": "correct-horse-1"}
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_unverified_user_absent_from_leaderboard_rebuild(
    client: AsyncClient,
    redis_client: redis.Redis,
    test_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, body = await _register_unverified(client)
    async with session_factory() as db:
        await leaderboard.rebuild(db, redis_client, test_settings)
    assert await redis_client.zscore(leaderboard.ZSET_KEY, str(body["id"])) is None


@pytest.mark.asyncio
async def test_register_lowercases_email(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    mixed = f"MixedCase-{uuid.uuid4().hex}@Example.COM"
    resp = await client.post(
        "/auth/register",
        json={
            "email": mixed,
            "username": f"u{uuid.uuid4().hex[:12]}",
            "password": "correct-horse-1",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["email"] == mixed.lower()


@pytest.mark.asyncio
async def test_login_is_case_insensitive_on_email(client: AsyncClient) -> None:
    email = f"case-{uuid.uuid4().hex}@example.com"
    await client.post(
        "/auth/register",
        json={
            "email": email,
            "username": f"u{uuid.uuid4().hex[:12]}",
            "password": "correct-horse-1",
        },
    )
    r = await client.post(
        "/auth/login", json={"email": email.upper(), "password": "correct-horse-1"}
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_duplicate_email_differing_only_in_case_is_rejected(
    client: AsyncClient,
) -> None:
    email = f"dup-{uuid.uuid4().hex}@example.com"
    body = {
        "email": email,
        "username": f"u{uuid.uuid4().hex[:12]}",
        "password": "correct-horse-1",
    }
    assert (await client.post("/auth/register", json=body)).status_code == 201
    body2 = {**body, "email": email.upper(), "username": f"u{uuid.uuid4().hex[:12]}"}
    assert (await client.post("/auth/register", json=body2)).status_code == 409
