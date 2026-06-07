"""Celery tasks for 3-tier CRDT persistence (Redis → OperationLog → snapshot)."""

from __future__ import annotations

import base64
import time

import redis as sync_redis
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.metrics import (
    crdt_compaction_duration_seconds,
    crdt_ops_compacted_total,
    execution_queue_depth,
    ws_ban_active,
)
from core.logging import log_compaction, log_compaction_error


def get_sync_redis():
    return sync_redis.from_url(settings.REDIS_URL, decode_responses=True)


@shared_task(
    name="crdt.flush_operations",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def flush_operations_to_db(self, file_id: str):
    """
    Warm path: drain Redis buffer → bulk insert OperationLog rows.
    Runs every YJS_FLUSH_INTERVAL_SEC or when buffer hits YJS_FLUSH_OP_THRESHOLD.
    """
    redis_client = get_sync_redis()
    buffer_key = f"file:{file_id}:updates"
    updates = redis_client.lrange(buffer_key, 0, -1)

    if not updates:
        redis_client.delete(f"file:{file_id}:flush_scheduled")
        return

    current_version = int(redis_client.get(f"file:{file_id}:version") or 0)
    base_version = current_version - len(updates)

    from apps.files.models import OperationLog

    try:
        with transaction.atomic():
            op_logs = [
                OperationLog(
                    file_id=file_id,
                    operation_json={"update": update},
                    vector_clock=base_version + index + 1,
                )
                for index, update in enumerate(updates)
            ]
            OperationLog.objects.bulk_create(op_logs, ignore_conflicts=False)
            redis_client.ltrim(buffer_key, len(updates), -1)
    except Exception as exc:
        raise self.retry(exc=exc) from exc

    redis_client.delete(f"file:{file_id}:flush_scheduled")

    op_count = int(redis_client.get(f"file:{file_id}:op_count") or 0)
    compact_threshold = settings.YJS_COMPACT_OP_THRESHOLD

    if op_count >= compact_threshold:
        compact_snapshot.apply_async(args=[file_id], queue="crdt.persist")


@shared_task(
    name="crdt.compact_snapshot",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def compact_snapshot(self, file_id: str):
    """
    Cold path: merge OperationLog → yjs_snapshot in PostgreSQL.
    Idempotent: keyed on file_id + current checkpoint version.
    """
    del self

    from apps.files.models import File, FileVersion, OperationLog

    redis_client = get_sync_redis()
    start_time = time.monotonic()
    ops_count = 0

    try:
        with crdt_compaction_duration_seconds.time():
            with transaction.atomic():
                try:
                    file_obj = File.objects.select_for_update().get(id=file_id)
                except File.DoesNotExist:
                    return

                checkpoint = file_obj.compaction_checkpoint_version
                server_version = int(redis_client.get(f"file:{file_id}:version") or checkpoint)

                if server_version <= checkpoint:
                    return

                ops = list(
                    OperationLog.objects.filter(
                        file_id=file_id,
                        vector_clock__gt=checkpoint,
                    ).order_by("vector_clock")
                )
                redis_ops = redis_client.lrange(f"file:{file_id}:updates", 0, -1)

                if not ops and not redis_ops:
                    return

                ops_count = len(ops) + len(redis_ops)
                existing_snapshot = bytes(file_obj.yjs_snapshot) if file_obj.yjs_snapshot else b""
                op_binaries = []

                for op in ops:
                    update_b64 = op.operation_json.get("update", "")
                    if update_b64:
                        op_binaries.append(base64.b64decode(update_b64))

                for update_b64 in redis_ops:
                    try:
                        op_binaries.append(base64.b64decode(update_b64))
                    except Exception:
                        continue

                new_snapshot = existing_snapshot
                for binary in op_binaries:
                    new_snapshot = new_snapshot + binary  # TODO: replace with ypy merge

                file_obj.yjs_snapshot = new_snapshot
                file_obj.yjs_state_version = server_version
                file_obj.compaction_checkpoint_version = server_version
                file_obj.last_compacted_at = timezone.now()
                file_obj.save(
                    update_fields=[
                        "yjs_snapshot",
                        "yjs_state_version",
                        "compaction_checkpoint_version",
                        "last_compacted_at",
                    ]
                )

                OperationLog.objects.filter(
                    file_id=file_id,
                    vector_clock__lte=server_version,
                ).delete()

                if redis_ops:
                    redis_client.ltrim(f"file:{file_id}:updates", len(redis_ops), -1)

                redis_client.set(f"file:{file_id}:op_count", 0)

                if file_obj.content:
                    FileVersion.objects.create(
                        file=file_obj,
                        snapshot=file_obj.content,
                        created_by=None,
                        source=FileVersion.SOURCE_COMPACTION,
                        branch_name="main",
                        label=f"Auto checkpoint v{server_version}",
                    )

        if ops_count:
            crdt_ops_compacted_total.inc(ops_count)
            duration_ms = int((time.monotonic() - start_time) * 1000)
            log_compaction(
                file_id=file_id,
                ops_compacted=ops_count,
                duration_ms=duration_ms,
                checkpoint_version=server_version,
            )

    except Exception as exc:
        log_compaction_error(
            file_id=file_id,
            error_type=type(exc).__name__,
            message=str(exc),
        )
        raise


@shared_task(name="crdt.idle_compact")
def idle_compact(file_id: str):
    """Triggered when last editor leaves file."""
    redis_client = get_sync_redis()
    editors = redis_client.scard(f"file:{file_id}:editors")
    if editors == 0:
        compact_snapshot.apply_async(args=[file_id], queue="crdt.persist")


@shared_task(name="crdt.flush_all_active")
def flush_all_active_files():
    """Beat-triggered fallback: flush all files with non-empty Redis buffers."""
    redis_client = get_sync_redis()
    for key in redis_client.scan_iter("file:*:updates"):
        parts = key.split(":")
        if len(parts) < 3:
            continue
        file_id = parts[1]
        if redis_client.llen(key) > 0:
            flush_operations_to_db.apply_async(args=[file_id], queue="crdt.persist")


@shared_task(name="tasks.sample_queue_depth")
def sample_queue_depth():
    """Sample Celery queue lengths and update Prometheus gauges."""
    redis_client = get_sync_redis()
    for queue_name, metric_label in [
        (settings.EXEC_HIGH_QUEUE, "execution.high"),
        (settings.EXEC_LOW_QUEUE, "execution.low"),
        ("crdt.persist", "crdt.persist"),
    ]:
        depth = redis_client.llen(queue_name)
        execution_queue_depth.labels(metric_label).set(depth)

    ban_count = sum(1 for _ in redis_client.scan_iter("ws:ban:*", count=100))
    ws_ban_active.set(ban_count)
