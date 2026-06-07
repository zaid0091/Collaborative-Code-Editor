"""WebSocket rate limiting and abuse protection (Section 7.6)."""

from __future__ import annotations

import os
import time
from typing import Literal

from apps.core.metrics import ws_abuse_disconnects_total, ws_ban_active
from core.logging import log_ws_abuse

AbuseAction = Literal["allow", "warn", "drop", "disconnect"]

SILENT_DROP_TYPES = frozenset({"awareness", "cursor", "ping", "sync_request", "join"})

# Limits from env vars (defaults from Section 7.6)
LIMITS: dict[str, dict] = {
    "update": {"per_sec": 30, "burst": 50},
    "awareness": {"per_sec": 20, "burst": 40},
    "cursor": {"per_sec": 20, "burst": 40},
    "sync_request": {"per_10s": 5},
    "join": {"per_10s": 5},
    "ping": {"per_60s": 4},
    "total": {"per_sec": 60, "burst": 100},
}


def _load_limits_from_settings() -> None:
    """Merge Django settings / env overrides into LIMITS."""
    try:
        from django.conf import settings

        LIMITS["update"]["per_sec"] = settings.WS_MAX_UPDATE_PER_SEC
        LIMITS["total"]["per_sec"] = settings.WS_MAX_MSG_PER_SEC
        LIMITS["total"]["burst"] = settings.WS_MAX_MSG_PER_SEC + 40
    except Exception:
        update_per_sec = int(os.environ.get("WS_MAX_UPDATE_PER_SEC", 30))
        total_per_sec = int(os.environ.get("WS_MAX_MSG_PER_SEC", 60))
        LIMITS["update"]["per_sec"] = update_per_sec
        LIMITS["total"]["per_sec"] = total_per_sec
        LIMITS["total"]["burst"] = total_per_sec + 40


_load_limits_from_settings()


class WSAbuseGuard:
    def __init__(self, redis_client):
        self.redis = redis_client
        self._local_counts: dict = {}

    async def check(self, session_id: str, user_id: str, msg_type: str) -> AbuseAction:
        """
        Check rate limits for incoming message.
        Returns: allow | warn | drop | disconnect
        """
        del user_id
        try:
            type_action = await self._check_type_limit(session_id, msg_type)
            total_action = await self._check_total_limit(session_id)

            severity = ["allow", "warn", "drop", "disconnect"]
            return severity[max(severity.index(type_action), severity.index(total_action))]
        except Exception:
            return self._check_local_fallback(session_id, msg_type)

    async def _check_type_limit(self, session_id: str, msg_type: str) -> AbuseAction:
        limits = LIMITS.get(msg_type, {})
        if not limits:
            return "allow"

        key = f"ws:rate:{session_id}:{msg_type}"
        window = 1

        if "per_10s" in limits:
            window = 10
            max_count = limits["per_10s"]
            burst = max_count
        elif "per_60s" in limits:
            window = 60
            max_count = limits["per_60s"]
            burst = max_count
        else:
            max_count = limits["per_sec"]
            burst = limits.get("burst", max_count)

        count = await self._increment_window(key, window)

        if count > burst:
            return "disconnect"
        if count > max_count:
            if msg_type in SILENT_DROP_TYPES:
                return "drop"
            return "warn"
        return "allow"

    async def _check_total_limit(self, session_id: str) -> AbuseAction:
        key = f"ws:rate:{session_id}:total"
        count = await self._increment_window(key, 1)

        total_limits = LIMITS["total"]
        try:
            from django.conf import settings

            limit = settings.WS_MAX_MSG_PER_SEC
            burst = total_limits.get("burst", limit + 40)
        except Exception:
            limit = int(os.environ.get("WS_MAX_MSG_PER_SEC", 60))
            burst = int(os.environ.get("WS_MAX_MSG_PER_SEC", 60)) * 2

        if count > burst:
            return "disconnect"
        if count > limit:
            return "warn"
        return "allow"

    async def _increment_window(self, key: str, window_sec: int) -> int:
        """Sliding window counter using Redis INCR + EXPIRE."""
        pipe = self.redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_sec)
        results = await pipe.execute()
        return results[0]

    def _check_local_fallback(self, session_id: str, msg_type: str) -> AbuseAction:
        """In-memory fallback when Redis is unavailable."""
        now = time.time()
        key = f"{session_id}:{msg_type}"
        entry = self._local_counts.get(key, {"count": 0, "window_start": now})

        if now - entry["window_start"] > 1.0:
            entry = {"count": 0, "window_start": now}

        entry["count"] += 1
        self._local_counts[key] = entry

        limit = LIMITS.get(msg_type, {}).get("per_sec", 60)
        if entry["count"] > limit * 2:
            return "disconnect"
        if entry["count"] > limit:
            if msg_type in SILENT_DROP_TYPES:
                return "drop"
            return "warn"
        return "allow"

    async def record_violation(
        self,
        user_id: str,
        session_id: str,
        reason: str,
        force_disconnect: bool = False,
    ) -> dict:
        """
        Increment user-level abuse strikes.
        Returns: {strikes, banned, ban_duration_sec?}
        """
        strikes_key = f"ws:abuse:{user_id}:strikes"
        recent_key = f"ws:abuse:{user_id}:recent"

        recent = await self.redis.incr(recent_key)
        await self.redis.expire(recent_key, 600)

        total = await self.redis.incr(strikes_key)
        await self.redis.expire(strikes_key, 86400)

        result: dict = {"strikes": total, "banned": False}

        try:
            from django.conf import settings

            max_strikes = settings.WS_ABUSE_MAX_STRIKES
            ban_min = settings.WS_ABUSE_STRIKE_BAN_MIN
        except Exception:
            max_strikes = int(os.environ.get("WS_ABUSE_MAX_STRIKES", 3))
            ban_min = int(os.environ.get("WS_ABUSE_STRIKE_BAN_MIN", 5))

        if recent >= max_strikes:
            ban_sec = ban_min * 60
            await self.redis.set(f"ws:ban:{user_id}", 1, ex=ban_sec)
            result["banned"] = True
            result["ban_duration_sec"] = ban_sec
            ws_ban_active.inc()

        if total >= 10:
            await self.redis.set(f"ws:flagged:{user_id}", 1, ex=86400)

        action = "ban" if result["banned"] else "strike"
        log_ws_abuse(user_id, session_id, reason, result["strikes"], action)

        if force_disconnect:
            ws_abuse_disconnects_total.labels(reason).inc()

        return result

    async def is_banned(self, user_id: str) -> bool:
        result = await self.redis.get(f"ws:ban:{user_id}")
        return result is not None
