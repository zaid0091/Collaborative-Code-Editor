"""Graceful shutdown and node lifecycle helpers for collaboration WebSockets."""

from __future__ import annotations

import redis.asyncio as aioredis
from django.conf import settings

_redis_override = None


async def get_redis_client():
    if _redis_override is not None:
        return _redis_override

    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def mark_node_draining(node_id: str, redis_client):
    """Called by PreStop hook or SIGTERM handler."""
    await redis_client.set(f"node:{node_id}:draining", 1, ex=60)


async def flush_active_buffers_on_shutdown(node_id: str):
    """
    On graceful shutdown: flush all non-empty Redis update buffers to OperationLog.

    Called before pod termination.
    """
    del node_id  # reserved for per-node connection scoping in a future iteration

    from tasks.persist_updates import flush_operations_to_db

    redis_client = await get_redis_client()
    try:
        async for key in redis_client.scan_iter("file:*:updates"):
            parts = key.split(":")
            if len(parts) < 3:
                continue
            file_id = parts[1]
            length = await redis_client.llen(key)
            if length > 0:
                flush_operations_to_db.apply_async(args=[file_id], queue="crdt.persist")
    finally:
        await redis_client.aclose()
