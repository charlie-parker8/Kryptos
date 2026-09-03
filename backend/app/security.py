"""Password hashing and session-token helpers — no framework/request concerns here."""

import hashlib
import secrets

import bcrypt

# bcrypt only examines the first 72 bytes of its input and silently ignores the rest, so two
# distinct passwords sharing a 72-byte prefix would hash identically. Request schemas cap
# password length at this same bound so that can't happen.
_BCRYPT_MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    assert len(encoded) <= _BCRYPT_MAX_PASSWORD_BYTES, (
        "password exceeds bcrypt's input limit"
    )
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_email(value: str) -> str:
    """Canonical form stored in `users.email` — trimmed and lowercased. Deliberately simple:
    no provider-specific dot/plus-tag folding (a Gmail-ism, out of scope). The DB CHECK
    `email = lower(email)` backstops this.
    """
    return value.strip().lower()
