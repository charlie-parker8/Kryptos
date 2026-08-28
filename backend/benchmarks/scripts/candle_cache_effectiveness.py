"""Milestone C benchmark: how much the Redis candle cache cuts outbound Kraken OHLC calls.

Same shape as cache_effectiveness.py, for the Trade-page chart's history endpoint: many
viewers each polling `GET /candles` for one pair+interval, once with the cache bypassed and
once live, counting calls that reach Kraken's REST OHLC endpoint. `get_ohlc` is stubbed
with a counter; Redis, the TTL, and the read-through logic in `app.market_data.candles` are
the real code path.

This measures the history read-through in isolation — the realistic worst case for REST
load, a cold cache polled by every open chart. The live WS stream (app.candle_stream) only
keeps the `:forming` key warm and makes no REST calls.

Run:  docker compose up -d  &&  python backend/benchmarks/scripts/candle_cache_effectiveness.py
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

from app.market_data import candles as candle_cache
from app.market_data.kraken import Candle

_RESULTS_PATH = Path(__file__).resolve().parents[1] / "RESULTS.md"
_REDIS_URL = "redis://localhost:6379/2"  # dedicated index, flushed here

PAIRS = ["BTC/USD", "ETH/USD", "SOL/USD"]
INTERVALS = [1, 5, 15, 60]
VIEWERS = 30            # concurrent open charts, each fixed on one pair+interval
READ_INTERVAL_S = 3.0   # poll cadence (SWR reconcile is 15–120s; 3s is a stress cadence)
DURATION_S = 30
HISTORY_TTL_S = 180
FORMING_TTL_S = 900
LIMIT = 500
KRAKEN_ROWS = 720  # Kraken's REST OHLC endpoint returns up to this many

_PRICE = Decimal("50000.00")
_COMBOS = [(pair, interval) for pair in PAIRS for interval in INTERVALS]


def _fake_history(pair: str, interval: int) -> list[Candle]:
    width = interval * 60
    start = int(time.time()) - width * (KRAKEN_ROWS - 1)
    return [
        Candle(
            pair=pair,
            interval=interval,
            open_time=datetime.fromtimestamp(start + i * width, tz=UTC),
            open=_PRICE,
            high=_PRICE,
            low=_PRICE,
            close=_PRICE,
            volume=Decimal(1),
        )
        for i in range(KRAKEN_ROWS)
    ]


class _CountingUpstream:
    def __init__(self) -> None:
        self.calls = 0

    async def get_ohlc(
        self, pair: str, interval: int, **_: object
    ) -> list[Candle]:
        self.calls += 1
        await asyncio.sleep(0.01)  # a token network cost (OHLC is a heavier response)
        return _fake_history(pair, interval)


async def _run(*, use_cache: bool) -> int:
    upstream = _CountingUpstream()
    client = redis.from_url(_REDIS_URL)
    await client.flushdb()

    deadline = time.monotonic() + DURATION_S

    async def viewer(index: int) -> None:
        pair, interval = _COMBOS[index % len(_COMBOS)]
        while time.monotonic() < deadline:
            if use_cache:
                await candle_cache.get_candles(
                    client,
                    pair,
                    interval,
                    limit=LIMIT,
                    base_url="http://unused.invalid",
                    timeout=1.0,
                    history_ttl_seconds=HISTORY_TTL_S,
                    forming_ttl_seconds=FORMING_TTL_S,
                )
            else:
                await upstream.get_ohlc(pair, interval)
            await asyncio.sleep(READ_INTERVAL_S)

    with patch("app.market_data.candles.get_ohlc", new=upstream.get_ohlc):
        try:
            await asyncio.gather(*(viewer(n) for n in range(VIEWERS)))
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
        f"- Workload: {VIEWERS} viewers over {len(_COMBOS)} (pair, interval) charts, "
        f"1 read/{READ_INTERVAL_S:g}s for {DURATION_S}s (history TTL {HISTORY_TTL_S}s)\n"
        f"- Kraken OHLC calls without cache: {uncached}\n"
        f"- Kraken OHLC calls with cache: {cached}\n"
        f"- Reduction: {reduction:.1f}%\n"
        f"- Forming-candle WS broadcasts are coalesced to <=1/s per (pair, interval); "
        f"the `:forming` Redis write on every trade is not rate-limited.\n"
    )
    _record_result("MILESTONE-C-CANDLE-ENTRIES", entry)
    print(entry.strip())


async def _main() -> None:
    uncached = await _run(use_cache=False)
    cached = await _run(use_cache=True)
    _append_result(uncached=uncached, cached=cached)


if __name__ == "__main__":
    asyncio.run(_main())
