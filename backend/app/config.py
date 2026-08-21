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
    redis_url: str = "redis://localhost:6379/0"

    starting_cash_balance: Decimal = Decimal("100000.00")
    price_max_age_seconds: int = 10

    kraken_rest_base_url: str = "https://api.kraken.com"
    kraken_ws_url: str = "wss://ws.kraken.com/v2"
    kraken_request_timeout_seconds: float = 5.0


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # required fields are sourced from the environment
