"""Celery worker tasks — placeholders for queue wiring."""

from celery import shared_task


@shared_task(name="tasks.worker_tasks.heartbeat")
def heartbeat() -> str:
    return "ok"


@shared_task(name="tasks.worker_tasks.persist_updates")
def persist_updates(file_id: str) -> str:
    raise NotImplementedError("CRDT persist task not yet implemented")


@shared_task(name="tasks.worker_tasks.compact_snapshot")
def compact_snapshot(file_id: str) -> str:
    raise NotImplementedError("CRDT compaction task not yet implemented")


@shared_task(name="tasks.worker_tasks.run_code")
def run_code(job_id: str) -> str:
    raise NotImplementedError("Code execution task not yet implemented")


@shared_task(name="tasks.worker_tasks.run_ai_analysis")
def run_ai_analysis(job_id: str) -> str:
    raise NotImplementedError("AI analysis task not yet implemented")
