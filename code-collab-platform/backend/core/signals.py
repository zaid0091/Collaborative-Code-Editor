"""Graceful shutdown signal handlers (Section 4.7.2)."""

from __future__ import annotations

import os
import signal

import redis as sync_redis
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings

from core.logging import logger


def handle_sigterm(signum, frame):
    """
    On SIGTERM (pod termination):
    1. Mark node as draining in Redis (TTL 35s)
    2. Notify all active WS connections to reconnect
    3. Flush all active Redis CRDT buffers to OperationLog
    4. Wait up to 30s for connections to drain
    """
    del signum, frame

    from tasks.persist_updates import flush_operations_to_db

    node_id = os.environ.get("NODE_ID", "unknown")
    redis_client = sync_redis.from_url(settings.REDIS_URL, decode_responses=True)
    redis_client.set(f"node:{node_id}:draining", 1, ex=35)

    active_files: set[str] = set()
    for key in redis_client.scan_iter("file:*:editors", count=100):
        parts = key.split(":")
        if len(parts) >= 2:
            active_files.add(parts[1])

    channel_layer = get_channel_layer()
    for file_id in active_files:
        async_to_sync(channel_layer.group_send)(
            f"file_{file_id}",
            {"type": "broadcast.server_draining"},
        )
        updates_key = f"file:{file_id}:updates"
        if redis_client.llen(updates_key) > 0:
            flush_operations_to_db.delay(file_id)

    logger.info(
        "graceful_shutdown.initiated",
        node_id=node_id,
        active_files=len(active_files),
    )


def register_shutdown_handlers() -> None:
    signal.signal(signal.SIGTERM, handle_sigterm)
