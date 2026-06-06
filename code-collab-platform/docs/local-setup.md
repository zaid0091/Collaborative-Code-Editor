# Local Setup

Development environment setup guide — placeholder.

## Prerequisites

- Docker and Docker Compose
- Python 3.11+
- Node.js 20+

## Quick start

```bash
cp .env.example .env
docker compose up -d --build
```

Services:

| Service | Port | Notes |
|---------|------|-------|
| nginx | 80, 443 | Reverse proxy (API, WS, frontend) |
| backend | 8000 | Django ASGI (uvicorn) |
| frontend | 3000 | Static React app |
| postgres | 5432 | PostgreSQL 16 |
| redis | 6379 | Redis 7 (512MB, allkeys-lru) |

Celery workers: `celery-persist`, `celery-exec-high`, `celery-exec-low`, `celery-beat`.

Execution workers mount `/var/run/docker.sock`; the backend service does **not**.
