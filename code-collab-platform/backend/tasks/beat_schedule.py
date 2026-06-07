"""Celery beat schedule for CRDT persistence and housekeeping."""

CELERY_BEAT_SCHEDULE = {
    "heartbeat": {
        "task": "tasks.worker_tasks.heartbeat",
        "schedule": 60.0,
    },
    "periodic-compaction-check": {
        "task": "crdt.flush_all_active",
        "schedule": 30.0,
    },
    "sample-queue-depth": {
        "task": "tasks.sample_queue_depth",
        "schedule": 15.0,
    },
}
