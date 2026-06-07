"""Daily per-user AI token budget tracking."""

from __future__ import annotations

import os

import redis


def _redis_client():
    try:
        from django.conf import settings

        url = settings.REDIS_URL
        budget = settings.AI_DAILY_TOKEN_BUDGET
    except Exception:
        url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
        budget = int(os.environ.get("AI_DAILY_TOKEN_BUDGET", 50000))
    return redis.from_url(url, decode_responses=True), budget


def check_and_consume_tokens(user_id: str, estimated_tokens: int) -> bool:
    """Return True if within budget, False if exceeded."""
    client, budget = _redis_client()
    key = f"ai:tokens:{user_id}"
    used = int(client.get(key) or 0)

    if used + estimated_tokens > budget:
        return False

    client.incrby(key, estimated_tokens)
    client.expire(key, 86400)
    return True


def get_usage(user_id: str) -> dict:
    client, budget = _redis_client()
    used = int(client.get(f"ai:tokens:{user_id}") or 0)
    return {"used": used, "budget": budget, "remaining": max(budget - used, 0)}
