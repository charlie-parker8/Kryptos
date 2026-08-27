"""Tests for the production-deployment hardening layer: CORS allowlist, the state-changing
Origin check + security headers, the WebSocket Origin check, per-IP rate limiting, and the
/health readiness semantics (Postgres hard, Redis soft).
"""

import uuid

import pytest
import redis.asyncio as redis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.deps import SESSION_COOKIE_NAME
from app.main import app
from app.routers.ws import portfolio_ws

ALLOWED_ORIGIN = get_settings().allowed_origins[0]
FOREIGN_ORIGIN = "https://evil.example"


def _bare_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _reg_body() -> dict[str, str]:
    return {
        "email": f"{uuid.uuid4()}@example.com",
        "username": f"u{uuid.uuid4().hex[:12]}",
        "password": "correct-horse-1",
    }


# --- CORS -------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cors_preflight_allows_the_configured_origin_with_credentials() -> None:
    async with _bare_client() as client:
        response = await client.options(
            "/orders",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,idempotency-key",
            },
        )
    assert response.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN
    assert response.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.asyncio
async def test_cors_preflight_does_not_greenlight_a_foreign_origin() -> None:
    async with _bare_client() as client:
        response = await client.options(
            "/orders",
            headers={
                "Origin": FOREIGN_ORIGIN,
                "Access-Control-Request-Method": "POST",
            },
        )
    assert response.headers.get("access-control-allow-origin") != FOREIGN_ORIGIN


# --- state-changing Origin check + security headers -----------------------------------


@pytest.mark.asyncio
async def test_state_changing_request_from_a_foreign_origin_is_rejected() -> None:
    async with _bare_client() as client:
        response = await client.post(
            "/auth/login",
            json={"email": "a@b.com", "password": "whatever1"},
            headers={"Origin": FOREIGN_ORIGIN},
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "Cross-origin request rejected"


@pytest.mark.asyncio
async def test_state_changing_request_from_the_allowed_origin_passes_the_check(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/auth/register", json=_reg_body(), headers={"Origin": ALLOWED_ORIGIN}
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_request_without_an_origin_header_is_allowed() -> None:
    # non-browser clients (curl, the health pinger, k6) send no Origin
    async with _bare_client() as client:
        response = await client.post(
            "/auth/login", json={"email": "a@b.com", "password": "whatever1"}
        )
    assert response.status_code == 401  # reached the handler, not blocked


@pytest.mark.asyncio
async def test_security_headers_present_on_responses() -> None:
    async with _bare_client() as client:
        response = await client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "same-origin"
    assert "strict-transport-security" not in response.headers  # http, not https


@pytest.mark.asyncio
async def test_hsts_header_present_over_https() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://test"
    ) as client:
        response = await client.get("/health")
    assert response.headers["strict-transport-security"].startswith("max-age=")


# --- WebSocket Origin check ----------------------------------------------------------


@pytest.mark.asyncio
async def test_ws_rejects_a_foreign_origin(
    redis_client: redis.Redis, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    from test_ws import FakeWebSocket

    fake_ws = FakeWebSocket(
        cookies={SESSION_COOKIE_NAME: "irrelevant"},
        headers={"origin": FOREIGN_ORIGIN},
    )
    await portfolio_ws(
        fake_ws, session_factory=session_factory, redis_client=redis_client
    )
    assert fake_ws.accepted is False
    assert fake_ws.closed_code == 1008


@pytest.mark.asyncio
async def test_ws_allows_the_configured_origin(
    client: AsyncClient,
    redis_client: redis.Redis,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    import asyncio

    from test_ws import FakeWebSocket

    await client.post("/auth/register", json=_reg_body())
    fake_ws = FakeWebSocket(
        cookies={SESSION_COOKIE_NAME: client.cookies[SESSION_COOKIE_NAME]},
        headers={"origin": ALLOWED_ORIGIN},
    )
    task = asyncio.create_task(
        portfolio_ws(
            fake_ws, session_factory=session_factory, redis_client=redis_client
        )
    )
    await fake_ws.ready.wait()
    fake_ws.simulate_disconnect()
    await task
    assert fake_ws.accepted is True
    assert fake_ws.closed_code is None


# --- rate limiting -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_is_rate_limited_per_ip(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # freeze the fixed window so the test can't straddle a minute boundary
    monkeypatch.setattr("app.rate_limit.time.time", lambda: 1_000.0)
    body = {"email": "nobody@example.com", "password": "wrongpass1"}

    statuses = [
        (await client.post("/auth/login", json=body)).status_code for _ in range(12)
    ]

    assert statuses[0] == 401  # first attempts reach the handler
    assert 429 in statuses  # the limit (10/min) trips within 12 tries
    assert statuses[-1] == 429


@pytest.mark.asyncio
async def test_rate_limiter_fails_open_when_redis_errors(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _boom(*_args: object, **_kwargs: object) -> object:
        raise redis.RedisError("down")

    monkeypatch.setattr("app.redis_client.redis_client.incr", _boom)
    response = await client.post(
        "/auth/login", json={"email": "x@y.com", "password": "wrongpass1"}
    )
    assert response.status_code == 401  # not blocked despite Redis being down


# --- /health readiness semantics --------------------------------------------------


@pytest.mark.asyncio
async def test_health_returns_503_when_postgres_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("db down")

    monkeypatch.setattr("app.main.AsyncSessionLocal", _boom)
    async with _bare_client() as client:
        response = await client.get("/health")
    assert response.status_code == 503
    assert response.json()["checks"]["database"] == "error"


@pytest.mark.asyncio
async def test_health_stays_200_when_only_redis_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _boom() -> object:
        raise RuntimeError("redis down")

    monkeypatch.setattr("app.main.redis_client.ping", _boom)
    async with _bare_client() as client:
        response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["redis"] == "error"
    assert body["checks"]["database"] == "ok"
