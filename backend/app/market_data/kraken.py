"""The one market-data adapter module (per CLAUDE.md) isolating Kraken's API from the rest of the app.

Canonical pair format used everywhere outside this module: "BASE/USD", e.g. "BTC/USD" — this
matches Kraken's own WebSocket v2 `symbol` field exactly, so no translation is needed there.
Kraken's REST endpoints still expect legacy asset codes for a handful of assets (most notably
XBT for Bitcoin); _KRAKEN_REST_ASSET_ALIASES maps canonical base assets to those legacy codes
only when constructing REST queries. Nothing outside this module ever sees a Kraken-native code.
"""

import json
import re
import ssl
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
import truststore
import websockets


class KrakenError(RuntimeError):
    """Kraken returned an error payload or an unexpected response shape."""


_KRAKEN_REST_ASSET_ALIASES: dict[str, str] = {
    "BTC": "XBT",
}

# The only status Kraken reports that means "accepts new market orders" — anything else
# (cancel_only, post_only, limit_only, reduce_only, work_in_progress, maintenance) blocks
# execution under invariant 11.
_TRADABLE_STATUS = "online"


def _to_kraken_rest_pair(pair: str) -> str:
    base, sep, quote = pair.partition("/")
    if not sep or not base or not quote:
        raise ValueError(f"expected a canonical 'BASE/QUOTE' pair, got {pair!r}")
    translated_base = _KRAKEN_REST_ASSET_ALIASES.get(base, base)
    return f"{translated_base}{quote}"


async def _fetch_public(
    endpoint: str,
    *,
    pair: str,
    base_url: str,
    timeout: float,
    client: httpx.AsyncClient | None,
) -> dict[str, Any]:
    """Shared GET + error-envelope handling for Kraken's public REST endpoints, which all
    key their result by Kraken's own legacy pair code (e.g. "XXBTZUSD"). Callers already
    know which canonical pair they requested, so that key is irrelevant and discarded here.
    """
    owns_client = client is None
    # Verify against the OS trust store rather than httpx's bundled certifi CAs: on machines
    # behind a TLS-inspecting corporate proxy/AV, the OS store is what actually has the
    # intercepting root CA installed. Still full certificate validation, not verify=False.
    client = client or httpx.AsyncClient(
        timeout=timeout, verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    )
    try:
        resp = await client.get(
            f"{base_url}/0/public/{endpoint}",
            params={"pair": _to_kraken_rest_pair(pair)},
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("error"):
            raise KrakenError(str(payload["error"]))
        result: dict[str, Any] = payload["result"]
        return next(iter(result.values()))
    finally:
        if owns_client:
            await client.aclose()


@dataclass(frozen=True)
class Ticker:
    pair: str  # canonical form, e.g. "BTC/USD"
    bid: Decimal
    ask: Decimal
    last: Decimal
    as_of: datetime  # UTC fetch time — Kraken's ticker has no timestamp; used for staleness checks (invariant #10)


@dataclass(frozen=True)
class PairStatus:
    pair: str  # canonical form, e.g. "BTC/USD"
    status: str  # raw Kraken status, e.g. "online", "cancel_only", "maintenance"
    tradable: bool  # True only when status == "online" — see invariant 11


@dataclass(frozen=True)
class Candle:
    pair: str  # canonical form, e.g. "BTC/USD"
    interval: int  # candle width in minutes
    open_time: datetime  # UTC; start of the bucket (WS interval_begin / REST row[0])
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal  # base-asset volume traded in the bucket
    vwap: Decimal | None = None
    trades: int | None = None


async def get_ticker(
    pair: str,
    *,
    base_url: str,
    timeout: float,
    client: httpx.AsyncClient | None = None,
) -> Ticker:
    """Fetch bid/ask/last for `pair` (canonical form, e.g. "BTC/USD") via Kraken's public REST Ticker endpoint.

    Buys use `ask`, sells use `bid` — see app.market_data.pricing.executable_price.
    """
    data = await _fetch_public(
        "Ticker", pair=pair, base_url=base_url, timeout=timeout, client=client
    )
    return Ticker(
        pair=pair,
        bid=Decimal(data["b"][0]),
        ask=Decimal(data["a"][0]),
        last=Decimal(data["c"][0]),
        as_of=datetime.now(UTC),
    )


async def get_pair_status(
    pair: str,
    *,
    base_url: str,
    timeout: float,
    client: httpx.AsyncClient | None = None,
) -> PairStatus:
    """Fetch whether `pair` is currently tradable via Kraken's public REST AssetPairs
    endpoint. Backs invariant 11: market orders are rejected whenever the provider reports
    a pair as anything other than fully "online" (paused, cancel-only, post-only,
    limit-only, etc.), until it reports tradable again.
    """
    data = await _fetch_public(
        "AssetPairs", pair=pair, base_url=base_url, timeout=timeout, client=client
    )
    status = data["status"]
    return PairStatus(pair=pair, status=status, tradable=status == _TRADABLE_STATUS)


def parse_ticker_message(payload: dict[str, Any]) -> list[Ticker]:
    """Pure — no I/O. Kraken's WS v2 ticker channel sends `{"channel": "ticker", "type":
    "snapshot"|"update", "data": [{"symbol": ..., "bid": ..., "ask": ..., "last": ...}, ...]}`;
    everything else on the same connection (subscribe acks, heartbeats, other channels)
    returns []. `symbol` arrives already in canonical form (e.g. "BTC/USD") — Kraken's WS v2
    API uses the same pair spelling this module uses everywhere outside REST calls, unlike
    the legacy codes _KRAKEN_REST_ASSET_ALIASES translates for the REST endpoints above.
    """
    if payload.get("channel") != "ticker" or payload.get("type") not in (
        "snapshot",
        "update",
    ):
        return []

    now = datetime.now(UTC)
    tickers: list[Ticker] = []
    for item in payload.get("data", []):
        try:
            tickers.append(
                Ticker(
                    pair=item["symbol"],
                    bid=Decimal(str(item["bid"])),
                    ask=Decimal(str(item["ask"])),
                    last=Decimal(str(item["last"])),
                    as_of=now,
                )
            )
        except (KeyError, InvalidOperation):
            continue  # a malformed entry must not drop the rest of a batch
    return tickers


async def stream_tickers(
    pairs: list[str],
    ws_url: str,
    *,
    on_tick: Callable[[Ticker], Awaitable[None]],
) -> None:
    """Long-lived: connects to Kraken's WS v2 API, subscribes to the ticker channel for
    `pairs`, and calls `on_tick()` for every parsed Ticker, forever — until the connection
    drops or is cancelled. Raises on connection/setup failure; reconnect-with-backoff is the
    caller's job (app.price_stream) so this stays a single, directly testable unit (parsing
    is exercised via parse_ticker_message; this function itself is only exercised by the
    `network`-marked integration test, same as get_ticker/get_pair_status above).
    """
    # Same OS-trust-store rationale as _fetch_public's httpx client.
    ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    async with websockets.connect(ws_url, ssl=ssl_context) as ws:
        await ws.send(
            json.dumps(
                {"method": "subscribe", "params": {"channel": "ticker", "symbol": pairs}}
            )
        )
        async for raw_message in ws:
            payload = json.loads(raw_message)
            for ticker in parse_ticker_message(payload):
                await on_tick(ticker)


# --- OHLC candles (CLAUDE.md line 21: Kraken REST OHLC + WS v2 ohlc, in this one adapter) ---

_RFC3339_FRACTIONAL_RE = re.compile(r"\.\d+")


def _parse_rfc3339_seconds(timestamp: str) -> datetime:
    """Parse an RFC 3339 timestamp, discarding any fractional-seconds component.

    Kraken's WS v2 `ohlc` frames stamp `interval_begin` with nanosecond precision (9
    fractional digits), which `datetime.fromisoformat` won't accept. Candle boundaries are
    always whole-second aligned, so dropping the fraction is lossless.
    """
    cleaned = _RFC3339_FRACTIONAL_RE.sub("", timestamp).replace("Z", "+00:00")
    return datetime.fromisoformat(cleaned)


def parse_ohlc_message(payload: dict[str, Any]) -> list[Candle]:
    """Pure — no I/O. Kraken's WS v2 ohlc channel sends `{"channel": "ohlc", "type":
    "snapshot"|"update", "data": [{"symbol": ..., "open": ..., "high": ..., "low": ...,
    "close": ..., "volume": ..., "vwap": ..., "trades": ..., "interval_begin": ...,
    "interval": ...}, ...]}`; everything else on the connection (subscribe acks,
    heartbeats, other channels) returns []. Numeric fields arrive as JSON numbers here
    (unlike the ticker channel's strings and the REST OHLC endpoint's strings), so each is
    coerced via `Decimal(str(...))` to avoid binary-float artifacts.

    Stateless: Kraken sends no "this candle just closed" flag, so this returns whatever
    candles a single frame carried without deciding which are final — app.candle_stream
    infers a bucket roll from a change in `interval_begin`.
    """
    if payload.get("channel") != "ohlc" or payload.get("type") not in (
        "snapshot",
        "update",
    ):
        return []

    candles: list[Candle] = []
    for item in payload.get("data", []):
        try:
            vwap = item.get("vwap")
            trades = item.get("trades")
            candles.append(
                Candle(
                    pair=item["symbol"],
                    interval=int(item["interval"]),
                    open_time=_parse_rfc3339_seconds(item["interval_begin"]),
                    open=Decimal(str(item["open"])),
                    high=Decimal(str(item["high"])),
                    low=Decimal(str(item["low"])),
                    close=Decimal(str(item["close"])),
                    volume=Decimal(str(item["volume"])),
                    vwap=Decimal(str(vwap)) if vwap is not None else None,
                    trades=int(trades) if trades is not None else None,
                )
            )
        except (KeyError, ValueError, InvalidOperation):
            continue  # a malformed entry must not drop the rest of a batch
    return candles


def _parse_ohlc_rest_result(
    result: dict[str, Any], *, pair: str, interval: int
) -> list[Candle]:
    """Pure. Kraken's REST OHLC result keys the candle array by the legacy pair code and
    adds a separate `last` cursor entry, so — unlike every other public endpoint — the
    result dict has two keys and `_fetch_public`'s "take the only value" shortcut doesn't
    apply. Prices arrive as strings here (contrast the WS channel's numbers). Oldest first;
    the final row is the still-forming bucket.
    """
    rows = next(value for key, value in result.items() if key != "last")
    return [
        Candle(
            pair=pair,
            interval=interval,
            open_time=datetime.fromtimestamp(int(row[0]), tz=UTC),
            open=Decimal(row[1]),
            high=Decimal(row[2]),
            low=Decimal(row[3]),
            close=Decimal(row[4]),
            vwap=Decimal(row[5]),
            volume=Decimal(row[6]),
            trades=int(row[7]),
        )
        for row in rows
    ]


async def get_ohlc(
    pair: str,
    interval: int,
    *,
    base_url: str,
    timeout: float,
    since: int | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[Candle]:
    """Fetch recent OHLC candles for `pair` (canonical form, e.g. "BTC/USD") at `interval`
    minutes via Kraken's public REST OHLC endpoint. Returns up to ~720 of the most recent
    candles, oldest first; the final candle is the still-forming bucket. `since` (a cursor
    from a previous response's `last`) narrows the result to newer candles.

    Not routed through `_fetch_public`: the OHLC result dict carries both the candle array
    and a `last` cursor, so that helper's "take the only value" shortcut doesn't fit.
    """
    owns_client = client is None
    client = client or httpx.AsyncClient(
        timeout=timeout, verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    )
    params: dict[str, str | int] = {
        "pair": _to_kraken_rest_pair(pair),
        "interval": interval,
    }
    if since is not None:
        params["since"] = since
    try:
        resp = await client.get(f"{base_url}/0/public/OHLC", params=params)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("error"):
            raise KrakenError(str(payload["error"]))
        result: dict[str, Any] = payload["result"]
        return _parse_ohlc_rest_result(result, pair=pair, interval=interval)
    finally:
        if owns_client:
            await client.aclose()


async def stream_ohlc(
    pairs: list[str],
    interval: int,
    ws_url: str,
    *,
    on_candle: Callable[[Candle], Awaitable[None]],
    snapshot: bool = False,
) -> None:
    """Long-lived: connects to Kraken's WS v2 API, subscribes to the ohlc channel for
    `pairs` at a single `interval`, and calls `on_candle()` for every parsed Candle,
    forever — until the connection drops or is cancelled.

    One interval per connection: Kraken rejects a second ohlc interval on the same
    connection ("Already subscribed to one ohlc interval on this symbol"), so
    app.candle_stream opens one of these per configured interval. Raises on
    connection/setup failure; reconnect-with-backoff is the caller's job, mirroring
    stream_tickers — so this stays a single directly-testable unit (parsing is exercised
    via parse_ohlc_message; this function itself only by the `network`-marked test).
    """
    # Same OS-trust-store rationale as _fetch_public's httpx client.
    ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    async with websockets.connect(ws_url, ssl=ssl_context) as ws:
        await ws.send(
            json.dumps(
                {
                    "method": "subscribe",
                    "params": {
                        "channel": "ohlc",
                        "symbol": pairs,
                        "interval": interval,
                        "snapshot": snapshot,
                    },
                }
            )
        )
        async for raw_message in ws:
            payload = json.loads(raw_message)
            for candle in parse_ohlc_message(payload):
                await on_candle(candle)
