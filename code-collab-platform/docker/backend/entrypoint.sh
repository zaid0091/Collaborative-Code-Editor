#!/bin/sh
set -e

host="${POSTGRES_HOST:-postgres}"
port="${POSTGRES_PORT:-5432}"

echo "Waiting for PostgreSQL at ${host}:${port}..."
python - <<'PY'
import os
import socket
import sys
import time

host = os.environ.get("POSTGRES_HOST", "postgres")
port = int(os.environ.get("POSTGRES_PORT", "5432"))

for _ in range(60):
    try:
        with socket.create_connection((host, port), timeout=1):
            print("PostgreSQL is ready")
            sys.exit(0)
    except OSError:
        time.sleep(1)

print("Timed out waiting for PostgreSQL", file=sys.stderr)
sys.exit(1)
PY

echo "Waiting for Redis..."
python - <<'PY'
import os
import socket
import sys
import time
from urllib.parse import urlparse

redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
parsed = urlparse(redis_url)
host = parsed.hostname or "redis"
port = parsed.port or 6379

for _ in range(60):
    try:
        with socket.create_connection((host, port), timeout=1):
            print("Redis is ready")
            sys.exit(0)
    except OSError:
        time.sleep(1)

print("Timed out waiting for Redis", file=sys.stderr)
sys.exit(1)
PY

exec "$@"
