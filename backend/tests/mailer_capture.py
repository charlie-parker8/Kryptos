"""Test-only capture backend for app.mailer. Importable (no `test_` prefix), same convention
as helpers.py — pytest puts tests/ on sys.path. The autouse `email_outbox` fixture patches
`app.mailer.send_email` -> `capture`."""

import re
from dataclasses import dataclass

_TOKEN_RE = re.compile(r"[?&]token=([A-Za-z0-9_-]+)")


@dataclass
class SentEmail:
    to: str
    subject: str
    html: str
    text: str


OUTBOX: list[SentEmail] = []


async def capture(*, to: str, subject: str, html: str, text: str) -> None:
    OUTBOX.append(SentEmail(to=to, subject=subject, html=html, text=text))


def verification_token_for(email: str) -> str:
    """Token from the most recent verification email sent to `email`."""
    for sent in reversed(OUTBOX):
        if sent.to == email:
            m = _TOKEN_RE.search(sent.text) or _TOKEN_RE.search(sent.html)
            if m:
                return m.group(1)
    raise AssertionError(f"no verification email with a token for {email!r}")
