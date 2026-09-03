"""The one transactional-email adapter (per CLAUDE.md's one-adapter rule) — isolates the
email provider (Resend) from the rest of the app, exactly as app.market_data.kraken isolates
the price provider.

With no KRYPTOS_RESEND_API_KEY set, `send_email` uses a null backend that logs and sends
nothing — the CI / offline-dev default. Tests monkeypatch `send_email` itself
(tests/mailer_capture.py + the autouse `email_outbox` fixture).
"""

import logging
import ssl

import httpx
import truststore

from app.config import get_settings

logger = logging.getLogger(__name__)

_VERIFICATION_SUBJECT = "Verify your Kryptos email"


class EmailError(RuntimeError):
    """The email provider rejected the send or was unreachable."""


async def send_email(*, to: str, subject: str, html: str, text: str) -> None:
    """Deliver one email. Resend when an API key is configured, else the null backend.
    Raises EmailError only from the Resend path — the registration / resend callers treat a
    failure as best-effort (a provider outage must not fail signup)."""
    settings = get_settings()
    if settings.resend_api_key:
        await _send_via_resend(to=to, subject=subject, html=html, text=text)
    else:
        await _send_via_null(to=to, subject=subject, html=html, text=text)


async def _send_via_null(*, to: str, subject: str, html: str, text: str) -> None:
    logger.info("email(null backend): to=%s subject=%r", to, subject)


async def _send_via_resend(*, to: str, subject: str, html: str, text: str) -> None:
    settings = get_settings()
    # Same OS-trust-store rationale as app.market_data.kraken's httpx client.
    client = httpx.AsyncClient(
        timeout=settings.email_request_timeout_seconds,
        verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
    )
    try:
        resp = await client.post(
            f"{settings.resend_api_base_url}/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.email_from,
                "to": [to],
                "subject": subject,
                "html": html,
                "text": text,
            },
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise EmailError(f"Resend send failed: {exc}") from exc
    finally:
        await client.aclose()


def build_verification_link(token: str) -> str:
    return f"{get_settings().frontend_origin}/verify?token={token}"


async def send_verification_email(to: str, token: str) -> None:
    """Send the 'confirm your address' email. Calls the module-global `send_email` so a
    single monkeypatch point covers every caller."""
    link = build_verification_link(token)
    html = (
        "<p>Welcome to Kryptos. Confirm this email address to open positions and join the "
        f'leaderboard:</p><p><a href="{link}">Verify my email</a></p>'
        "<p>This link expires in 24 hours. If you didn't create a Kryptos account, ignore "
        "this email.</p>"
    )
    text = (
        "Welcome to Kryptos. Confirm this email address to open positions and join the "
        f"leaderboard:\n\n{link}\n\nThis link expires in 24 hours. If you didn't create a "
        "Kryptos account, ignore this email."
    )
    await send_email(to=to, subject=_VERIFICATION_SUBJECT, html=html, text=text)
