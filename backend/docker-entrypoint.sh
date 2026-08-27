#!/bin/sh
# Fail-closed startup: run migrations before serving. This container is always a single
# instance (see Dockerfile header), so a plain `alembic upgrade head` on boot is safe — no
# competing migrator — and a migration failure blocking startup is the behaviour we want.
set -eu

echo "kryptos: running database migrations..."
alembic upgrade head

echo "kryptos: starting uvicorn on 0.0.0.0:${PORT:-8000} (workers=1)"
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips "*"
