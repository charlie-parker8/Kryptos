"""The one market-data adapter module (per CLAUDE.md) isolating Kraken's API from the rest of the app.

Canonical pair format used everywhere outside this module: "BASE/USD", e.g. "BTC/USD" — this
matches Kraken's own WebSocket v2 `symbol` field exactly, so no translation is needed there.
Kraken's REST endpoints still expect legacy asset codes for a handful of assets (most notably
XBT for Bitcoin); _KRAKEN_REST_ASSET_ALIASES maps canonical base assets to those legacy codes
only when constructing REST queries. Nothing outside this module ever sees a Kraken-native code.
"""

import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import truststore


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
