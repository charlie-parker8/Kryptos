from typing import ClassVar

import httpx
import pytest

from app import mailer
from app.config import Settings

# The autouse `email_outbox` fixture (conftest.py) patches `app.mailer.send_email` to a
# capture stub. These tests exercise the real adapter, so they restore the genuine function
# first — captured here at import time, before any fixture runs.
_REAL_SEND_EMAIL = mailer.send_email


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "boom",
                request=httpx.Request("POST", "http://x"),
                response=self,  # type: ignore[arg-type]
            )


class _FakeClient:
    instances: ClassVar[list["_FakeClient"]] = []

    def __init__(self, *, status_code: int = 200, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.status_code = status_code
        self.posted: dict[str, object] = {}
        _FakeClient.instances.append(self)

    async def post(
        self, url: str, *, headers: dict[str, str], json: dict[str, object]
    ) -> _FakeResponse:
        self.posted = {"url": url, "headers": headers, "json": json}
        return _FakeResponse(self.status_code)

    async def aclose(self) -> None:
        self.closed = True


def _settings(**over: object) -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://x/y",
        resend_api_key="re_test",
        resend_api_base_url="https://api.resend.test",
        email_from="Kryptos <t@example.com>",
        frontend_origin="https://app.example.com",
        **over,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_null_backend_logs_and_does_not_raise() -> None:
    await mailer._send_via_null(to="a@b.com", subject="s", html="h", text="t")


@pytest.mark.asyncio
async def test_resend_backend_posts_expected_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeClient.instances.clear()
    monkeypatch.setattr(mailer, "send_email", _REAL_SEND_EMAIL)
    monkeypatch.setattr(mailer, "get_settings", _settings)
    monkeypatch.setattr(
        mailer.httpx, "AsyncClient", lambda **kw: _FakeClient(status_code=200, **kw)
    )

    await mailer.send_verification_email("user@example.com", "tok123456789012345")

    sent = _FakeClient.instances[-1].posted
    assert sent["url"] == "https://api.resend.test/emails"
    assert sent["headers"]["Authorization"] == "Bearer re_test"  # type: ignore[index]
    body = sent["json"]
    assert body["to"] == ["user@example.com"]  # type: ignore[index]
    assert "tok123456789012345" in body["text"]  # type: ignore[operator]


@pytest.mark.asyncio
async def test_resend_backend_raises_email_error_on_5xx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mailer, "send_email", _REAL_SEND_EMAIL)
    monkeypatch.setattr(mailer, "get_settings", _settings)
    monkeypatch.setattr(
        mailer.httpx, "AsyncClient", lambda **kw: _FakeClient(status_code=502, **kw)
    )
    with pytest.raises(mailer.EmailError):
        await mailer.send_verification_email("user@example.com", "tok123456789012345")


def test_build_verification_link_uses_frontend_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mailer, "get_settings", _settings)
    assert (
        mailer.build_verification_link("abc")
        == "https://app.example.com/verify?token=abc"
    )
