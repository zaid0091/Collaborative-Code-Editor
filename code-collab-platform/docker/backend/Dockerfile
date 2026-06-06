FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app/backend

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app \
    && useradd --system --gid app --home-dir /app/backend app

COPY backend/requirements/base.txt backend/requirements/prod.txt /tmp/requirements/
RUN pip install --upgrade pip \
    && pip install -r /tmp/requirements/prod.txt

COPY backend/ /app/backend/
COPY docker/backend/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh \
    && chown -R app:app /app/backend

USER app

ENV DJANGO_SETTINGS_MODULE=config.settings.dev \
    PYTHONPATH=/app/backend

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
