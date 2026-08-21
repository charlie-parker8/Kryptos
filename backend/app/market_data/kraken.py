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

import httpx
import truststore


class KrakenError(RuntimeError):
    """Kraken returned an error payload or an unexpected response shape."""


_KRAKEN_REST_ASSET_ALIASES: dict[str, str] = {
    "BTC": "XBT",
}


def _to_kraken_rest_pair(pair: str) -> str:
    base, sep, quote = pair.partition("/")
    if not sep or not base or not quote:
        raise ValueError(f"expected a canonical 'BASE/QUOTE' pair, got {pair!r}")
    translated_base = _KRAKEN_REST_ASSET_ALIASES.get(base, base)
    return f"{translated_base}{quote}"


@dataclass(frozen=True)
class Ticker:
    pair: str  # canonical form, e.g. "BTC/USD"
    bid: Decimal
    ask: Decimal
    last: Decimal
    as_of: datetime  # UTC fetch time — Kraken's ticker has no timestamp; used for staleness checks (invariant #10)


async def get_ticker(
    pair: str,
    *,
    base_url: str,
    timeout: float,
    client: httpx.AsyncClient | None = None,
) -> Ticker:
    """Fetch bid/ask/last for `pair` (canonical form, e.g. "BTC/USD") via Kraken's public REST Ticker endpoint.

    Buys use `ask`, sells use `bid` — see the order-execution phase for those rules.
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
            f"{base_url}/0/public/Ticker", params={"pair": _to_kraken_rest_pair(pair)}
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("error"):
            raise KrakenError(str(payload["error"]))
        result = payload["result"]
        # Kraken keys the response by its own legacy pair code (e.g. "XXBTZUSD"); we already know
        # which canonical pair we requested, so the response key itself is irrelevant.
        data = next(iter(result.values()))
        return Ticker(
            pair=pair,
            bid=Decimal(data["b"][0]),
            ask=Decimal(data["a"][0]),
            last=Decimal(data["c"][0]),
            as_of=datetime.now(UTC),
        )
    finally:
        if owns_client:
            await client.aclose()


# get_tradable_asset_pairs() (via /0/public/AssetPairs) is deferred until order execution needs
# per-pair precision and the invariant #11 tradability gate — nothing consumes it yet.
