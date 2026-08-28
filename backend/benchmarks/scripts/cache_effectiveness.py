"""Milestone C benchmark: how much the Redis price cache cuts outbound Kraken calls.

Simulates a realistic read workload — many clients valuing their portfolios every second
over a window — against `app.market_data.cache`, once with the cache bypassed and once with
it live, counting calls that reach the Kraken adapter. The upstream `get_ticker` is stubbed
with a counter (no real Kraken traffic); everything else — Redis, the TTL, the
cache-or-fetch logic — is the real code path.

Run:  docker compose up -d  &&  python backend/benchmarks/scripts/cache_effectiveness.py
Appends one dated entry to backend/benchmarks/RESULTS.md.
"""

import asyncio
import subprocess
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import redis.asyncio as redis

from app.market_data import cache as price_cache
from app.market_data.kraken import Ticker

_RESULTS_PATH = Path(__file__).resolve().parents[1] / "RESULTS.md"
_REDIS_URL = "redis://localhost:6379/2"  # dedicated index, flushed here

PAIRS = ["BTC/USD", "ETH/USD", "SOL/USD"]
VIEWERS = 50          # concurrent dashboards revaluing their portfolios
READ_INTERVAL_S = 1.0  # each viewer revalues once per second...
DURATION_S = 20        # ...for this long
MAX_AGE_S = 10         # cache TTL / staleness bound (matches KRYPTOS_PRICE_MAX_AGE_SECONDS)


class _CountingUpstream:
    def __init__(self) -> None:
        self.calls = 0

    async def get_ticker(self, pair: str, **_: object) -> Ticker:
        self.calls += 1
        await asyncio.sleep(0.005)  # a token network cost
        return Ticker(
            pair=pair,
            bid=Decimal("100.00"),
            ask=Decimal("100.02"),
            last=Decimal("100.01"),
            as_of=datetime.now(UTC),
        )


async def _run(*, use_cache: bool) -> int:
    upstream = _CountingUpstream()
    client = redis.from_url(_REDIS_URL)
    await client.flushdb()

    deadline = time.monotonic() + DURATION_S

    async def viewer() -> None:
        while time.monotonic() < deadline:
            for pair in PAIRS:
                if use_cache:
                    await price_cache.get_latest_ticker(
                        client,
                        pair,
                        base_url="http://unused.invalid",
                        timeout=1.0,
                        max_age_seconds=MAX_AGE_S,
                    )
                else:
                    await upstream.get_ticker(pair)
            await asyncio.sleep(READ_INTERVAL_S)

    # Patch the adapter entry point the cache calls on a miss.
    with patch("app.market_data.cache.get_ticker", new=upstream.get_ticker):
        try:
            await asyncio.gather(*(viewer() for _ in range(VIEWERS)))
        finally:
            await client.flushdb()
            await client.aclose()
    return upstream.calls


def _git_commit() -> str:
    return (
        subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        or "unknown"
    )


def _record_result(section_marker: str, entry: str) -> None:
    """Insert `entry` after `<!-- section_marker -->` in RESULTS.md (newest first) rather
    than appending to EOF, so each milestone's runs stay under their own heading.
    """
    text = _RESULTS_PATH.read_text(encoding="utf-8") if _RESULTS_PATH.exists() else ""
    anchor = f"<!-- {section_marker} -->"
    head, sep, tail = text.partition(anchor)
    block = entry.strip("\n")
    if not sep:
        _RESULTS_PATH.write_text(
            text.rstrip("\n") + "\n\n" + block + "\n", encoding="utf-8"
        )
        return
    _RESULTS_PATH.write_text(
        head + anchor + "\n\n" + block + "\n\n" + tail.lstrip("\n"), encoding="utf-8"
    )


def _append_result(*, uncached: int, cached: int) -> None:
    reduction = (uncached - cached) / uncached * 100 if uncached else 0.0
    entry = (
        f"\n### {datetime.now(UTC):%Y-%m-%d} — {_git_commit()}\n"
        f"- Workload: {VIEWERS} viewers × {len(PAIRS)} pairs, "
        f"1 read/s for {DURATION_S}s (cache TTL {MAX_AGE_S}s)\n"
        f"- Kraken calls without cache: {uncached}\n"
        f"- Kraken calls with cache: {cached}\n"
        f"- Reduction: {reduction:.1f}%\n"
    )
    _record_result("MILESTONE-C-PRICE-ENTRIES", entry)
    print(entry.strip())


async def _main() -> None:
    uncached = await _run(use_cache=False)
    cached = await _run(use_cache=True)
    _append_result(uncached=uncached, cached=cached)


if __name__ == "__main__":
    asyncio.run(_main())
