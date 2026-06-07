"""Per-user fairness scheduler for execution queues."""

from __future__ import annotations

import os

import redis


def _fairness_config() -> tuple[int, int, int, str]:
    try:
        from django.conf import settings

        return (
            settings.EXEC_FAIR_MAX_CONCURRENT,
            settings.EXEC_FAIR_MAX_PENDING_HIGH,
            settings.EXEC_FAIR_MAX_PENDING_LOW,
            settings.REDIS_URL,
        )
    except Exception:
        return (
            int(os.environ.get("EXEC_FAIR_MAX_CONCURRENT", 2)),
            int(os.environ.get("EXEC_FAIR_MAX_PENDING_HIGH", 3)),
            int(os.environ.get("EXEC_FAIR_MAX_PENDING_LOW", 10)),
            os.environ.get("REDIS_URL", "redis://redis:6379/0"),
        )


class FairnessScheduler:
    def __init__(self, redis_client=None):
        if redis_client is not None:
            self.redis = redis_client
        else:
            _, _, _, redis_url = _fairness_config()
            self.redis = redis.from_url(redis_url, decode_responses=True)

    def check_and_reserve(self, user_id: str, priority: str) -> tuple[bool, dict]:
        max_concurrent, max_pending_high, max_pending_low, _ = _fairness_config()

        active_key = f"exec:fair:{user_id}:active"
        pending_key = f"exec:fair:{user_id}:pending:{priority}"

        active = int(self.redis.get(active_key) or 0)
        pending_high = int(self.redis.get(f"exec:fair:{user_id}:pending:high") or 0)
        pending_low = int(self.redis.get(f"exec:fair:{user_id}:pending:low") or 0)

        stats = {
            "active": active,
            "pending_high": pending_high,
            "pending_low": pending_low,
        }

        if active >= max_concurrent:
            stats["retry_after_sec"] = 10
            return False, stats

        pending_cap = max_pending_high if priority == "high" else max_pending_low
        pending_current = pending_high if priority == "high" else pending_low

        if pending_current >= pending_cap:
            stats["retry_after_sec"] = 30
            return False, stats

        self.redis.incr(pending_key)
        self.redis.expire(pending_key, 3600)

        return True, stats

    def on_job_start(self, user_id: str, priority: str):
        self.redis.incr(f"exec:fair:{user_id}:active")
        self.redis.decr(f"exec:fair:{user_id}:pending:{priority}")
        self.redis.expire(f"exec:fair:{user_id}:active", 300)

    def on_job_complete(self, user_id: str, priority: str):
        del priority
        active = int(self.redis.get(f"exec:fair:{user_id}:active") or 0)
        if active > 0:
            self.redis.decr(f"exec:fair:{user_id}:active")


scheduler = FairnessScheduler()
