"""Celery task for sandboxed code execution."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.core.metrics import execution_duration_seconds
from apps.execution.scheduler import scheduler
from core.logging import log_execution_complete, log_execution_start

EXECUTION_IMAGE = os.environ.get("EXECUTOR_IMAGE", "code-collab-executor:latest")
TIMEOUT_SEC = int(os.environ.get("EXECUTION_TIMEOUT_SEC", 5))
MEMORY_MB = int(os.environ.get("EXECUTION_MEMORY_MB", 256))

SECCOMP_PATH = Path(settings.BASE_DIR).parent / "docker" / "executor" / "seccomp.json"


def _runtime_language(language: str) -> str:
    if language == "typescript":
        return "javascript"
    return language


@shared_task(name="execution.run_code", bind=True, max_retries=0)
def run_code(self, job_id: str):
    from apps.execution.models import ExecutionJob

    worker_id = getattr(self.request, "hostname", "unknown")

    try:
        job = ExecutionJob.objects.get(id=job_id)
    except ExecutionJob.DoesNotExist:
        return

    job.status = ExecutionJob.STATUS_RUNNING
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at"])

    scheduler.on_job_start(str(job.user_id), job.priority)
    log_execution_start(
        job_id=job.id,
        user_id=job.user_id,
        worker_id=worker_id,
    )

    try:
        seccomp_arg = f"seccomp={SECCOMP_PATH.resolve()}"
        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=10m",
            "--tmpfs",
            "/run:rw,noexec,nosuid,nodev,size=1m",
            "--security-opt",
            "no-new-privileges:true",
            "--security-opt",
            seccomp_arg,
            "--cap-drop",
            "ALL",
            "--user",
            "65534:65534",
            "--pids-limit",
            "64",
            "--memory",
            f"{MEMORY_MB}m",
            "--memory-swap",
            f"{MEMORY_MB}m",
            "--cpus",
            "0.5",
            "--ulimit",
            "nofile=64:64",
            "--init",
            "-i",
            EXECUTION_IMAGE,
        ]

        payload = json.dumps(
            {
                "language": _runtime_language(job.language),
                "code": job.code,
            }
        )

        result = subprocess.run(
            docker_cmd,
            input=payload,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SEC + 2,
        )

        output = json.loads(result.stdout) if result.stdout.strip() else {}

        job.stdout = output.get("stdout", "")
        job.stderr = output.get("stderr", result.stderr[:4096])
        job.exit_code = output.get("exit_code", result.returncode)
        job.duration_ms = output.get("duration_ms", 0)
        job.status = ExecutionJob.STATUS_COMPLETED

    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "kill", f"exec_{job_id}"], capture_output=True)
        job.status = ExecutionJob.STATUS_TIMEOUT
        job.stderr = f"Execution timed out after {TIMEOUT_SEC}s"
        job.exit_code = -1

    except Exception as exc:
        job.status = ExecutionJob.STATUS_FAILED
        job.stderr = f"Execution error: {type(exc).__name__}"
        job.exit_code = -1

    finally:
        scheduler.on_job_complete(str(job.user_id), job.priority)
        log_execution_complete(
            job_id=job.id,
            user_id=job.user_id,
            status=job.status,
            duration_ms=job.duration_ms,
            exit_code=job.exit_code,
        )
        execution_duration_seconds.labels(job.language, job.status).observe(
            (job.duration_ms or 0) / 1000
        )
        job.save(update_fields=["status", "stdout", "stderr", "exit_code", "duration_ms"])
