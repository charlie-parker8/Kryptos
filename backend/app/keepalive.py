"""Self-ping keep-warm task — started from app.main's lifespan when KRYPTOS_SELF_PING_URL is set.

Render's free web service spins down after 15 minutes without an inbound request. The
GitHub Actions keep-alive cron is best-effort (runs are routinely 5-20 min late or skipped),
so on its own it can leave gaps longer than that. While the instance is awake it therefore
requests its own *public* URL: traffic has to arrive through Render's proxy to reset the idle
timer, so a loopback call would not help. The Action stays as the wake-up after a deploy or
restart, when nothing is running to ping.
"""

import asyncio
import logging

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_SECONDS = 10.0


async def run_self_ping(
    settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
) -> None:
    """Ping `settings.self_ping_url` every `self_ping_interval_seconds`. Mirrors the
    resilience loop in app.leaderboard.run_leaderboard_refresh: a failed ping is logged and
    retried next cycle; only CancelledError stops it. `transport` is a test seam."""
    assert settings.self_ping_url is not None
    async with httpx.AsyncClient(
        timeout=_REQUEST_TIMEOUT_SECONDS, transport=transport
    ) as client:
        while True:
            try:
                response = await client.get(settings.self_ping_url)
                logger.info(
                    "self-ping %s -> HTTP %s",
                    settings.self_ping_url,
                    response.status_code,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("self-ping failed; retrying next cycle", exc_info=True)
            await asyncio.sleep(settings.self_ping_interval_seconds)
