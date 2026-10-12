import asyncio

import httpx
import pytest

from app import keepalive
from app.config import Settings
from app.main import app, lifespan


def _settings(**overrides: object) -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://x:x@localhost/x",
        self_ping_url="https://api.example.test/health",
        self_ping_interval_seconds=300,
        **overrides,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_pings_configured_url_then_sleeps_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, json={"status": "ok"})

    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        if len(slept) == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(keepalive.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await keepalive.run_self_ping(
            _settings(), transport=httpx.MockTransport(handler)
        )

    assert requested == ["https://api.example.test/health"] * 2
    assert slept == [300, 300]


@pytest.mark.asyncio
async def test_request_failure_is_swallowed_and_loop_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200)

    sleeps = 0

    async def fake_sleep(seconds: float) -> None:
        nonlocal sleeps
        sleeps += 1
        if sleeps == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(keepalive.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await keepalive.run_self_ping(
            _settings(), transport=httpx.MockTransport(handler)
        )

    assert calls == 2  # the failed first ping did not stop the loop


@pytest.mark.asyncio
async def test_lifespan_starts_self_ping_only_when_url_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[Settings] = []

    async def fake_self_ping(settings: Settings) -> None:
        started.append(settings)
        await asyncio.Event().wait()

    async def idle(*_: object) -> None:
        await asyncio.Event().wait()

    from app import main

    monkeypatch.setattr(main, "run_self_ping", fake_self_ping)
    for name in ("run_price_stream", "run_leaderboard_refresh", "run_candle_stream"):
        monkeypatch.setattr(main, name, idle)

    for url, expected in (("https://api.example.test/health", 1), (None, 0)):
        started.clear()
        monkeypatch.setattr(
            main,
            "get_settings",
            lambda url=url: _settings().model_copy(update={"self_ping_url": url}),
        )
        async with lifespan(app):
            await asyncio.sleep(0)
        assert len(started) == expected
