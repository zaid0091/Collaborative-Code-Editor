"""Sync engine for reconnecting clients — merges PG snapshot, OperationLog, and Redis buffer."""

from __future__ import annotations

import base64

import redis.asyncio as aioredis
from channels.db import database_sync_to_async
from django.conf import settings

_redis_override = None


async def build_sync_response(
    file_id: str,
    last_known_version: int | None,
    client_state_vector: str | None,
) -> dict:
    """
    Assemble the sync_response payload for a reconnecting client.

    Sources merged in order:
    1. File.yjs_snapshot (PG) — compaction base
    2. OperationLog rows since compaction_checkpoint_version (PG)
    3. Redis file:{file_id}:updates buffer (not yet flushed to PG)
    """
    del client_state_vector  # reserved for future state-vector diffing

    redis_client = await get_redis()
    server_version = int(await redis_client.get(f"file:{file_id}:version") or 0)

    file_obj = await load_file(file_id)
    if file_obj is None:
        return {"error": "file_not_found"}

    checkpoint = file_obj.compaction_checkpoint_version
    snapshot_b64 = None
    delta_updates: list[str] = []
    missing_from = last_known_version or 0

    client_is_stale = last_known_version is None or last_known_version < checkpoint

    if client_is_stale:
        if file_obj.yjs_snapshot:
            snapshot_b64 = base64.b64encode(bytes(file_obj.yjs_snapshot)).decode()
        missing_from = checkpoint

    op_log_updates = await load_oplog_since(file_id, missing_from)
    delta_updates.extend(op_log_updates)

    redis_buffer = await redis_client.lrange(f"file:{file_id}:updates", 0, -1)
    delta_updates.extend(redis_buffer)

    return {
        "server_version": server_version,
        "snapshot": snapshot_b64,
        "delta_updates": delta_updates,
        "missing_from_version": missing_from,
    }


@database_sync_to_async
def load_file(file_id):
    from apps.files.models import File

    try:
        return File.objects.get(id=file_id)
    except File.DoesNotExist:
        return None


@database_sync_to_async
def load_oplog_since(file_id, from_version: int) -> list[str]:
    from apps.files.models import OperationLog

    logs = (
        OperationLog.objects.filter(
            file_id=file_id,
            vector_clock__gt=from_version,
        )
        .order_by("vector_clock")
        .values_list("operation_json", flat=True)
    )
    return [entry["update"] for entry in logs if isinstance(entry, dict) and "update" in entry]


async def get_redis():
    if _redis_override is not None:
        return _redis_override

    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)
