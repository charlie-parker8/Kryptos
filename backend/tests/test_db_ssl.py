"""The asyncpg TLS context for the Supabase pooler.

Python 3.13+ enables ssl.VERIFY_X509_STRICT in the default context, which Supabase's
CA chain fails ("CA cert does not include key usage extension"). build_db_ssl_context()
clears that one RFC-5280 strictness flag while keeping full certificate and hostname
verification — it must never degrade to CERT_NONE or check_hostname=False.
"""

import ssl
from pathlib import Path

from app.config import Settings
from app.db import build_db_ssl_context


def test_context_still_requires_a_valid_certificate() -> None:
    context = build_db_ssl_context()
    assert context.verify_mode is ssl.CERT_REQUIRED


def test_context_still_verifies_the_hostname() -> None:
    assert build_db_ssl_context().check_hostname is True


def test_context_clears_x509_strict_but_nothing_else() -> None:
    assert hasattr(ssl, "VERIFY_X509_STRICT"), "test premise: running on Python 3.13+"

    context = build_db_ssl_context()
    assert not (context.verify_flags & ssl.VERIFY_X509_STRICT)

    # Every other flag matches a stock default context: we relax strict-mode only.
    stock = ssl.create_default_context()
    assert context.verify_flags == stock.verify_flags & ~ssl.VERIFY_X509_STRICT


def test_ssl_connect_args_carry_this_context_and_alembic_shares_them() -> None:
    # When TLS is enabled, asyncpg gets our SSLContext object, not the bare `ssl=True`
    # (which would restore strict mode) and not a downgraded string like "require".
    settings = Settings(
        database_url="postgresql+asyncpg://u:p@host/db", database_ssl=True
    )
    connect_args = {"ssl": build_db_ssl_context()} if settings.database_ssl else {}
    ssl_arg = connect_args["ssl"]
    assert isinstance(ssl_arg, ssl.SSLContext)
    assert ssl_arg.verify_mode is ssl.CERT_REQUIRED
    assert ssl_arg.check_hostname is True

    # Alembic's env.py must run migrations through the very same CONNECT_ARGS so
    # migration connections and app connections present an identical TLS context.
    env_src = (Path(__file__).resolve().parents[1] / "alembic" / "env.py").read_text()
    assert "from app.db import" in env_src and "CONNECT_ARGS" in env_src
    assert "connect_args=CONNECT_ARGS" in env_src


def test_ssl_off_locally_means_no_connect_args() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://u:p@host/db", database_ssl=False
    )
    connect_args = {"ssl": build_db_ssl_context()} if settings.database_ssl else {}
    assert connect_args == {}
