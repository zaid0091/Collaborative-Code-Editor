"""Health and readiness probes (Section 11)."""

from __future__ import annotations

import os
import socket
import time

import redis
from django.conf import settings
from django.db import connection
from django.http import JsonResponse


def _run_health_checks() -> tuple[dict, int]:
    checks = {}
    status_code = 200

    try:
        start = time.monotonic()
        connection.ensure_connection()
        checks["database"] = {
            "status": "ok",
            "latency_ms": round((time.monotonic() - start) * 1000, 2),
        }
    except Exception as exc:
        checks["database"] = {"status": "error", "message": type(exc).__name__}
        status_code = 503

    try:
        start = time.monotonic()
        client = redis.from_url(settings.REDIS_URL)
        client.ping()
        checks["redis"] = {
            "status": "ok",
            "latency_ms": round((time.monotonic() - start) * 1000, 2),
        }
    except Exception as exc:
        checks["redis"] = {"status": "error", "message": type(exc).__name__}
        status_code = 503

    return checks, status_code


def health_check(request):
    """
    GET /health/
    Checks DB and Redis connectivity.
    Returns 200 if all healthy, 503 if any check fails.
    """
    del request
    checks, status_code = _run_health_checks()
    return JsonResponse(
        {
            "status": "ok" if status_code == 200 else "degraded",
            "checks": checks,
        },
        status=status_code,
    )


def readiness_check(request):
    """
    GET /ready/
    Kubernetes readiness probe — includes health checks and node drain status.
    """
    del request
    checks, status_code = _run_health_checks()
    if status_code != 200:
        return JsonResponse(
            {
                "status": "degraded",
                "checks": checks,
            },
            status=status_code,
        )

    try:
        client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        node_id = os.environ.get("NODE_ID", socket.gethostname())
        if client.get(f"node:{node_id}:draining"):
            checks["node"] = {"status": "draining"}
            return JsonResponse(
                {
                    "status": "draining",
                    "checks": checks,
                },
                status=503,
            )
    except Exception as exc:
        checks["node"] = {"status": "error", "message": type(exc).__name__}
        return JsonResponse(
            {
                "status": "degraded",
                "checks": checks,
            },
            status=503,
        )

    return JsonResponse(
        {
            "status": "ok",
            "checks": checks,
        },
        status=200,
    )
