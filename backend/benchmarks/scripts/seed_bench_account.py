"""Seed the fixtures the k6 load tests need (Milestones A and C).

Two jobs:

* **default** — register (or log in) one dedicated benchmark account and print its
  `kryptos_session` cookie value to **stdout**, so a k6 run can skip `/auth/register`
  (rate-limited 5 / 300 s / IP, which a ceiling sweep blows through)::

      COOKIE=$(python benchmarks/scripts/seed_bench_account.py)
      k6 run -e COOKIE=$COOKIE benchmarks/k6/ws_latency.js

* ``--accounts N`` — additionally insert N synthetic accounts straight into Postgres
  and the ``leaderboard:equity`` ZSET, so ``leaderboard_latency.js`` benchmarks a board
  of N real accounts. The backend's 30 s rebuild recomputes the same scores from
  Postgres (these accounts hold no positions, so equity == cash) and keeps them.

* ``--clear`` — delete the synthetic accounts (the single login account stays).

Run from ``backend/`` with docker-compose Postgres/Redis up and, for the default/cookie
job, the app running on :8000. Everything except the cookie goes to **stderr** so stdout
stays capturable.
"""

import argparse
import asyncio
import random
import ssl
import sys
import uuid
from decimal import Decimal

import httpx
import redis.asyncio as redis
import truststore
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import get_settings
from app.db import AsyncSessionLocal
from app.leaderboard import ZSET_KEY
from app.models import User

_BENCH_EMAIL = "bench@bench.kryptos"
_BENCH_USERNAME = "benchmark"
_BENCH_PASSWORD = "benchmark-load-1"  # throwaway local fixture credential
_SYNTH_LIKE = "bench+%@bench.kryptos"  # bench+{i}@bench.kryptos
_CHUNK = 1000


def _log(message: str) -> None:
    print(message, file=sys.stderr)


def _cents(amount: Decimal) -> int:
    return int((amount * 100).to_integral_value())


async def _print_cookie(base_url: str) -> str:
    """Register-or-login the one bench account; return its session cookie value.

    Login is tried first so re-runs don't burn the register rate limit.
    """
    # Verify TLS against the OS trust store (mirrors app/market_data/kraken.py) so this
    # works against an https:// deploy from a machine behind a TLS-inspecting proxy/AV.
    ssl_ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    async with httpx.AsyncClient(
        base_url=base_url, timeout=30.0, verify=ssl_ctx
    ) as client:
        resp = await client.post(
            "/auth/login",
            json={"email": _BENCH_EMAIL, "password": _BENCH_PASSWORD},
        )
        if resp.status_code == 401:
            resp = await client.post(
                "/auth/register",
                json={
                    "email": _BENCH_EMAIL,
                    "username": _BENCH_USERNAME,
                    "password": _BENCH_PASSWORD,
                },
            )
        resp.raise_for_status()
    cookie = resp.cookies.get("kryptos_session")
    if not cookie:
        raise RuntimeError("no kryptos_session cookie in the auth response")
    return cookie


async def _seed_accounts(n: int) -> int:
    """Insert N synthetic users + their leaderboard scores. Idempotent (ON CONFLICT DO
    NOTHING on email). Returns the total synthetic-account count afterwards.
    """
    settings = get_settings()
    rng = random.Random(1234)
    rows = [
        {
            "id": uuid.uuid4(),
            "email": f"bench+{i}@bench.kryptos",
            "username": f"bench{i}",
            "password_hash": "benchmark-synthetic-no-login",
            "starting_cash_balance": settings.starting_cash_balance,
            "cash_balance": Decimal(rng.randint(0, 5_000_000)) / 100,  # $0-$50k, 2dp
        }
        for i in range(n)
    ]

    async with AsyncSessionLocal() as db:
        for start in range(0, n, _CHUNK):
            await db.execute(
                pg_insert(User).on_conflict_do_nothing(index_elements=["email"]),
                rows[start : start + _CHUNK],
            )
        await db.commit()
        existing = (
            await db.execute(
                select(User.id, User.cash_balance).where(User.email.like(_SYNTH_LIKE))
            )
        ).all()

    client = redis.from_url(settings.redis_url)
    try:
        mapping = {str(uid): _cents(cash) for uid, cash in existing}
        items = list(mapping.items())
        for start in range(0, len(items), 5000):
            await client.zadd(ZSET_KEY, dict(items[start : start + 5000]))
    finally:
        await client.aclose()
    return len(existing)


async def _clear() -> int:
    settings = get_settings()
    async with AsyncSessionLocal() as db:
        ids = [
            str(r[0])
            for r in (
                await db.execute(select(User.id).where(User.email.like(_SYNTH_LIKE)))
            ).all()
        ]
        await db.execute(delete(User).where(User.email.like(_SYNTH_LIKE)))
        await db.commit()

    if ids:
        client = redis.from_url(settings.redis_url)
        try:
            for start in range(0, len(ids), 5000):
                await client.zrem(ZSET_KEY, *ids[start : start + 5000])
        finally:
            await client.aclose()
    return len(ids)


async def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument(
        "--accounts",
        type=int,
        default=0,
        help="also insert N synthetic leaderboard accounts",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="delete the synthetic accounts and exit",
    )
    args = parser.parse_args()

    if args.clear:
        _log(f"cleared {await _clear()} synthetic accounts")
        return

    if args.accounts:
        _log(f"seeding {args.accounts} synthetic accounts ...")
        total = await _seed_accounts(args.accounts)
        _log(f"leaderboard:equity now holds {total} synthetic accounts (+ real users)")

    print(await _print_cookie(args.base_url))  # stdout: the cookie, nothing else


if __name__ == "__main__":
    asyncio.run(_main())
