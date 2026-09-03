import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import redis.asyncio as redis
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import leaderboard, mailer, verification
from app.account import get_account_snapshot
from app.config import get_settings
from app.db import get_session
from app.deps import SESSION_COOKIE_NAME, get_current_user
from app.models import User, UserSession
from app.rate_limit import rate_limit
from app.redis_client import get_redis
from app.security import (
    generate_session_token,
    hash_password,
    hash_session_token,
    normalize_email,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

logger = logging.getLogger(__name__)

# Per-IP throttles on the unauthenticated surface. Generous enough for real fat-fingering,
# tight enough to blunt credential stuffing / signup spam.
_register_rate_limit = rate_limit("auth_register", limit=5, window_seconds=300)
_login_rate_limit = rate_limit("auth_login", limit=10, window_seconds=60)

# A precomputed hash so a login attempt against an unregistered email still pays bcrypt's
# cost, keeping response timing indistinguishable from a wrong-password attempt on a real
# account — otherwise timing would let a caller enumerate registered addresses.
_DUMMY_PASSWORD_HASH = hash_password("not-a-real-password-used-only-for-timing")


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(
        min_length=3, max_length=32, pattern=r"^[A-Za-z0-9._-]+$"
    )
    password: str = Field(min_length=8, max_length=72)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return normalize_email(value)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return normalize_email(value)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    username: str
    email_verified: bool
    cash_balance: Decimal
    starting_cash_balance: Decimal
    created_at: datetime


async def _issue_session(db: AsyncSession, user: User, response: Response) -> None:
    settings = get_settings()
    token = generate_session_token()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_session_token(token),
            expires_at=datetime.now(UTC)
            + timedelta(seconds=settings.session_ttl_seconds),
        )
    )
    await db.commit()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path="/",
    )


async def _authenticate(db: AsyncSession, email: str, password: str) -> User | None:
    user = await db.scalar(select(User).where(User.email == email))
    password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    if not verify_password(password, password_hash):
        return None
    return user


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_register_rate_limit)],
)
async def register(
    payload: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_session),  # noqa: B008 — FastAPI's own DI idiom
) -> User:
    settings = get_settings()
    user = User(
        email=payload.email,
        username=payload.username,
        password_hash=hash_password(payload.password),
        starting_cash_balance=settings.starting_cash_balance,
        cash_balance=settings.starting_cash_balance,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, _registration_conflict_detail(exc)
        ) from None

    raw_token = await verification.issue_token(db, user.id)
    await _issue_session(db, user, response)  # commits both the session and the token
    # Best-effort: a mail-provider outage must not fail signup — the user can resend later.
    # The account enters the leaderboard only once the email is verified (see
    # confirm_verification and leaderboard.rebuild).
    try:
        await mailer.send_verification_email(user.email, raw_token)
    except mailer.EmailError:
        logger.warning(
            "verification email send failed for %s", user.id, exc_info=True
        )
    return user


def _registration_conflict_detail(exc: IntegrityError) -> str:
    """Map a unique-violation on register to a specific message. The email unique index is
    Postgres-auto-named `users_email_key`; the username one is `uq_users_username`.
    """
    text = str(exc.orig)
    if "uq_users_username" in text:
        return "Username already taken"
    if "users_email_key" in text:
        return "Email already registered"
    return "Email or username already taken"


@router.post(
    "/login",
    response_model=UserResponse,
    dependencies=[Depends(_login_rate_limit)],
)
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_session),  # noqa: B008 — FastAPI's own DI idiom
) -> User:
    user = await _authenticate(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    await _issue_session(db, user, response)
    return user


_verify_request_rate_limit = rate_limit(
    "auth_verify_request", limit=5, window_seconds=3600
)
_verify_confirm_rate_limit = rate_limit(
    "auth_verify_confirm", limit=20, window_seconds=3600
)


class VerifyConfirmRequest(BaseModel):
    token: str = Field(min_length=16, max_length=512)


@router.post(
    "/verify/request",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(_verify_request_rate_limit)],
)
async def request_verification(
    user: User = Depends(get_current_user),  # noqa: B008 — FastAPI's own DI idiom
    db: AsyncSession = Depends(get_session),  # noqa: B008 — FastAPI's own DI idiom
) -> None:
    """Re-send the verification email. Authenticated-only, so there is no email in the body
    and thus no enumeration vector. No-op (still 202) if already verified."""
    if user.email_verified_at is not None:
        return
    raw_token = await verification.issue_token(db, user.id)
    await db.commit()
    try:
        await mailer.send_verification_email(user.email, raw_token)
    except mailer.EmailError:
        logger.warning("verification resend failed for %s", user.id, exc_info=True)


@router.post(
    "/verify/confirm",
    response_model=UserResponse,
    dependencies=[Depends(_verify_confirm_rate_limit)],
)
async def confirm_verification(
    payload: VerifyConfirmRequest,
    db: AsyncSession = Depends(get_session),  # noqa: B008 — FastAPI's own DI idiom
    redis_client: redis.Redis = Depends(get_redis),  # noqa: B008 — FastAPI's own DI idiom
) -> User:
    """Redeem a verification link. Unauthenticated (the token is the credential) and POST so
    a scanner's link prefetch can't burn it. On first success, seed the leaderboard."""
    result, user = await verification.consume_token(db, payload.token)
    if result is verification.VerifyResult.INVALID or user is None:
        await db.rollback()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "That verification link is invalid or has expired.",
        )
    await db.commit()
    if result is verification.VerifyResult.OK:
        settings = get_settings()
        snapshot = await get_account_snapshot(db, redis_client, settings, user)
        await leaderboard.update_score(redis_client, user.id, snapshot.equity)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    db: AsyncSession = Depends(get_session),  # noqa: B008 — FastAPI's own DI idiom
) -> None:
    if session_token is not None:
        await db.execute(
            update(UserSession)
            .where(
                UserSession.token_hash == hash_session_token(session_token),
                UserSession.revoked_at.is_(None),
            )
            .values(revoked_at=func.now())
        )
        await db.commit()
    # Mirror the attributes _issue_session set so the browser matches and clears the cookie.
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=get_settings().environment == "production",
        samesite="lax",
    )


@router.get("/me", response_model=UserResponse)
async def me(
    user: User = Depends(get_current_user),  # noqa: B008 — FastAPI's own DI idiom
) -> User:
    return user
