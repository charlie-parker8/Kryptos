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

    starting_cash_balance: Decimal = Decimal("100000.00")
    price_max_age_seconds: int = 10
    session_ttl_seconds: int = 60 * 60 * 24 * 7  # 7 days

    kraken_rest_base_url: str = "https://api.kraken.com"
    kraken_ws_url: str = "wss://ws.kraken.com/v2"
    kraken_request_timeout_seconds: float = 5.0

    supported_pairs: list[str] = Field(
        default_factory=lambda: ["BTC/USD", "ETH/USD", "SOL/USD"]
    )

    @property
    def allowed_origins(self) -> list[str]:
        """The exact browser origins allowed to call the API / open the WebSocket. One
        entry today; a list so CORSMiddleware and the Origin checks share one source."""
        return [self.frontend_origin]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # required fields are sourced from the environment
