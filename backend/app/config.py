from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT_ENV = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT_ENV,
        env_file_encoding="utf-8",
        env_prefix="KRYPTOS_",
        # "ignore", not "forbid": the same .env also carries POSTGRES_*/REDIS_PORT for
        # docker-compose, which pydantic-settings sees but doesn't own.
        extra="ignore",
    )

    environment: str = "development"

    database_url: str = Field(...)
    # Managed Postgres (Supabase pooler) requires TLS; local docker-compose Postgres does
    # not. Set KRYPTOS_DATABASE_SSL=true in the hosted environment only.
    database_ssl: bool = False
    redis_url: str = "redis://localhost:6379/0"

    # The browser origin the SPA is served from. Same-origin in local dev (Vite proxy);
    # in the split deploy it's https://app.<domain>. Drives the CORS allowlist, the
    # WebSocket Origin check, and the state-changing-request Origin check.
    frontend_origin: str = "http://localhost:5173"
    # Host header allowlist (Starlette TrustedHostMiddleware). "*" disables the check —
    # fine for local dev; set KRYPTOS_ALLOWED_HOSTS='["api.<domain>"]' in the hosted env.
    allowed_hosts: list[str] = Field(default_factory=lambda: ["*"])

    starting_cash_balance: Decimal = Decimal("10000.00")
    price_max_age_seconds: int = 10
    session_ttl_seconds: int = 60 * 60 * 24 * 7  # 7 days

    # Leveraged-position model. Collateral is committed from cash_balance (free cash) at
    # open; a position is liquidated when its equity (collateral + unrealized P&L) falls to
    # maintenance_margin_rate * notional. Entry/mark/exit/liquidation all price off the
    # Kraken `last` price. No trading fee in the MVP, but the knob stays so it can be turned
    # on without a schema change.
    leverage_presets: list[int] = Field(default_factory=lambda: [2, 5, 10])
    maintenance_margin_rate: Decimal = Decimal("0.005")
    min_collateral: Decimal = Decimal("10.00")
    taker_fee_bps: int = 0
    # Account is reset (positions closed, cash restored to starting balance) when equity
    # falls to or below this floor. Clean isolated-margin liquidations leave ~mmr*notional
    # behind, so equity crosses 0 mainly on gap moves between ticks.
    bankruptcy_equity_floor: Decimal = Decimal("0.00")

    kraken_rest_base_url: str = "https://api.kraken.com"
    kraken_ws_url: str = "wss://ws.kraken.com/v2"
    kraken_request_timeout_seconds: float = 5.0

    supported_pairs: list[str] = Field(
        default_factory=lambda: ["BTC/USD", "ETH/USD", "SOL/USD"]
    )

    # Candlestick chart (Trade page). Kraken interval minutes; the frontend mirrors this
    # list in core/realtime/types.ts. History is a Redis read-through cache in front of
    # Kraken's REST OHLC endpoint (never Postgres — invariant 8); the forming candle is
    # kept fresh from the WS v2 ohlc feed.
    supported_candle_intervals: list[int] = Field(
        default_factory=lambda: [1, 5, 15, 60]
    )
    candle_history_limit: int = 500  # bars kept per (pair, interval), and the REST ceiling
    candle_history_ttl_seconds: int = 180  # closed bars barely move; live feed covers recency
    candle_forming_ttl_seconds: int = 900  # outlives a brief stream drop mid-bucket
    kraken_ohlc_snapshot: bool = False  # REST owns history; the first WS update seeds the bar

    @property
    def allowed_origins(self) -> list[str]:
        """The exact browser origins allowed to call the API / open the WebSocket. One
        entry today; a list so CORSMiddleware and the Origin checks share one source."""
        return [self.frontend_origin]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # required fields are sourced from the environment
