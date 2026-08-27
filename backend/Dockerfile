# Kryptos FastAPI backend — single-process container (in-process WebSocket fan-out and the
# price-stream / leaderboard-refresh lifespan tasks require exactly one worker, one instance).
FROM python:3.13-slim-bookworm

# uv for dependency resolution/install (pinned; upgrade deliberately).
COPY --from=ghcr.io/astral-sh/uv:0.9.30 /uv /uvx /bin/

# ca-certificates: app/market_data/kraken.py verifies TLS against the OS trust store via
# `truststore`, and the Supabase pooler + Redis Cloud connections are TLS — all need the
# system CA bundle present.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Optional: fold an extra CA bundle into the system trust store — e.g. a local
# TLS-inspecting proxy/AV root (this repo's dev machine runs one). No-op on builders that
# don't pass the secret (Render, CI); for a local build behind an intercepting middlebox:
#   docker build --secret id=extra_ca,src=/path/to/host-ca-bundle.pem -t kryptos-api .
RUN --mount=type=secret,id=extra_ca,required=false,target=/run/secrets/extra_ca \
    if [ -s /run/secrets/extra_ca ]; then \
      cat /run/secrets/extra_ca >> /etc/ssl/certs/ca-certificates.crt; \
    fi

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

WORKDIR /app

# Dependency layer — cached until pyproject.toml / uv.lock change.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Application source.
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini docker-entrypoint.sh ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

RUN chmod +x docker-entrypoint.sh \
 && useradd --system --home-dir /app --shell /usr/sbin/nologin appuser \
 && chown -R appuser:appuser /app

ENV PATH="/app/.venv/bin:$PATH"
USER appuser

# Render injects $PORT; 8000 is the local-run default (see docker-entrypoint.sh).
EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
