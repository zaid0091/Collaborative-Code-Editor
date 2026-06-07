"""Structured logging helpers (Section 11)."""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


def sanitize_for_log(text: str, max_chars: int = 200) -> str:
    """Truncate long strings; never log beyond max_chars."""
    if text is None:
        return ""
    if len(text) > max_chars:
        return text[:max_chars] + f"...[truncated, total={len(text)}]"
    return text


def log_ws_connect(user_id, file_id, session_id, node_id):
    logger.info(
        "ws.connect",
        user_id=str(user_id),
        file_id=str(file_id),
        session_id=session_id,
        node_id=node_id,
    )


def log_ws_disconnect(user_id, file_id, session_id, reason, duration_sec):
    logger.info(
        "ws.disconnect",
        user_id=str(user_id),
        file_id=str(file_id),
        session_id=session_id,
        reason=reason,
        duration_sec=duration_sec,
    )


def log_ws_abuse(user_id, session_id, violation_type, strike_count, action):
    logger.warning(
        "ws.abuse",
        user_id=str(user_id),
        session_id=session_id,
        violation_type=violation_type,
        strike_count=strike_count,
        action=action,
    )


def log_execution_enqueue(job_id, user_id, language, queue, source):
    logger.info(
        "execution.enqueue",
        job_id=str(job_id),
        user_id=str(user_id),
        language=language,
        queue=queue,
        source=source,
    )


def log_execution_start(job_id, user_id, worker_id):
    logger.info(
        "execution.start",
        job_id=str(job_id),
        user_id=str(user_id),
        worker_id=worker_id,
    )


def log_execution_complete(job_id, user_id, status, duration_ms, exit_code):
    logger.info(
        "execution.complete",
        job_id=str(job_id),
        user_id=str(user_id),
        status=status,
        duration_ms=duration_ms,
        exit_code=exit_code,
    )


def log_execution_reject(user_id, reason, active_count, pending_count):
    logger.warning(
        "execution.fairness_reject",
        user_id=str(user_id),
        reason=reason,
        active=active_count,
        pending=pending_count,
    )


def log_compaction(file_id, ops_compacted, duration_ms, checkpoint_version):
    logger.info(
        "crdt.compact",
        file_id=str(file_id),
        ops_compacted=ops_compacted,
        duration_ms=duration_ms,
        checkpoint_version=checkpoint_version,
    )


def log_compaction_error(file_id, error_type, message):
    logger.error(
        "crdt.compact_error",
        file_id=str(file_id),
        error_type=error_type,
        message=sanitize_for_log(message),
    )
