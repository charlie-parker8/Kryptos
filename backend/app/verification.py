"""Email-verification token lifecycle — issue a single-use, time-boxed token and consume it.

The raw token goes in the emailed link; only its SHA-256 hash is stored (reusing
app.security.hash_session_token). Consuming locks the token row and the user row so a
double-click or a scanner prefetch cannot verify twice or race a concurrent consume.
"""

import enum
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import EmailVerificationToken, User
from app.security import hash_session_token

_TOKEN_BYTES = 32


class VerifyResult(enum.Enum):
    OK = "ok"
    ALREADY_VERIFIED = "already_verified"
    INVALID = "invalid"


async def issue_token(db: AsyncSession, user_id: uuid.UUID) -> str:
    """Create a pending verification token for `user_id`; return the raw token for the email
    link. The caller owns the transaction / commit."""
    raw = secrets.token_urlsafe(_TOKEN_BYTES)
    db.add(
        EmailVerificationToken(
            user_id=user_id,
            token_hash=hash_session_token(raw),
            expires_at=datetime.now(UTC)
            + timedelta(seconds=get_settings().email_verification_ttl_seconds),
        )
    )
    return raw


async def consume_token(
    db: AsyncSession, raw: str
) -> tuple[VerifyResult, User | None]:
    """Redeem a raw token. Unknown / already-consumed / expired -> (INVALID, None).
    Otherwise mark the token consumed and, unless already verified, set the user's
    email_verified_at. The caller owns the commit."""
    token = await db.scalar(
        select(EmailVerificationToken)
        .where(EmailVerificationToken.token_hash == hash_session_token(raw))
        .with_for_update()
    )
    now = datetime.now(UTC)
    if token is None or token.consumed_at is not None or token.expires_at <= now:
        return VerifyResult.INVALID, None

    user = await db.scalar(
        select(User).where(User.id == token.user_id).with_for_update()
    )
    if user is None:  # unreachable (FK cascade) — keeps the type honest
        return VerifyResult.INVALID, None

    token.consumed_at = now
    if user.email_verified_at is not None:
        return VerifyResult.ALREADY_VERIFIED, user
    user.email_verified_at = now
    return VerifyResult.OK, user
