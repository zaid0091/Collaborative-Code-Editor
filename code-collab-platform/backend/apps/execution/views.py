"""Execution API views."""

from __future__ import annotations

import redis
from django.conf import settings
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.metrics import execution_fairness_rejections_total
from apps.execution.code_scanner import scan_code
from apps.execution.models import ExecutionJob
from apps.execution.scheduler import scheduler
from apps.execution.tasks import run_code
from core.logging import log_execution_enqueue, log_execution_reject
from core.permissions import get_file_workspace_id, get_user_workspace_role

SOURCE_TO_QUEUE = {
    "ui_run": "execution.high",
    "ui_repl": "execution.high",
    "background_test": "execution.low",
    "ai_analysis": "execution.low",
    "webhook_ci": "execution.low",
}

SOURCE_TO_PRIORITY = {
    "ui_run": ExecutionJob.PRIORITY_HIGH,
    "ui_repl": ExecutionJob.PRIORITY_HIGH,
    "background_test": ExecutionJob.PRIORITY_LOW,
    "ai_analysis": ExecutionJob.PRIORITY_LOW,
    "webhook_ci": ExecutionJob.PRIORITY_LOW,
}

ALLOWED_LANGUAGES = {"python", "javascript", "typescript"}


def _redis_client():
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


# SECURITY AUDIT: permission confirmed — IsAuthenticated; job results scoped to owner.
# SECURITY AUDIT gap fixed — optional file_id requires workspace membership.
class ExecuteView(APIView):
    permission_classes = [IsAuthenticated]
    MAX_CODE_LENGTH = 65536

    def post(self, request):
        code = request.data.get("code", "")
        language = request.data.get("language", "python")
        source = request.data.get("source", ExecutionJob.SOURCE_UI_RUN)
        file_id = request.data.get("file_id")

        if len(code) > self.MAX_CODE_LENGTH:
            return Response({"error": "Code payload too large"}, status=400)

        if file_id:
            workspace_id = get_file_workspace_id(file_id)
            role = get_user_workspace_role(request.user, workspace_id, request)
            if workspace_id is None or role is None:
                return Response({"error": "Not found"}, status=404)

        if language not in ALLOWED_LANGUAGES:
            return Response({"error": f"Language not supported: {language}"}, status=400)

        if source not in SOURCE_TO_QUEUE:
            source = ExecutionJob.SOURCE_UI_RUN

        is_safe, reason = scan_code(code, language)
        if not is_safe:
            return Response({"error": reason}, status=400)

        redis_client = _redis_client()
        rate_key = f"exec:rate:{request.user.id}"
        count = redis_client.incr(rate_key)
        redis_client.expire(rate_key, 60)
        if count > settings.EXECUTION_RATE_LIMIT:
            return Response(
                {"error": "Rate limit exceeded", "retry_after_sec": 60},
                status=429,
            )

        priority = SOURCE_TO_PRIORITY[source]
        allowed, stats = scheduler.check_and_reserve(str(request.user.id), priority)
        if not allowed:
            log_execution_reject(
                user_id=str(request.user.id),
                reason="concurrent_limit",
                active_count=stats.get("active", 0),
                pending_count=stats.get(f"pending_{priority}", 0),
            )
            execution_fairness_rejections_total.labels("concurrent_limit").inc()
            return Response(
                {
                    "error": "Too many concurrent jobs",
                    "retry_after_sec": stats.get("retry_after_sec", 10),
                    "active": stats["active"],
                    "pending": stats[f"pending_{priority}"],
                },
                status=429,
            )

        job = ExecutionJob.objects.create(
            user=request.user,
            file_id=file_id,
            code=code,
            language=language,
            priority=priority,
            source=source,
            status=ExecutionJob.STATUS_QUEUED,
        )

        queue = SOURCE_TO_QUEUE[source]
        celery_priority = 9 if priority == ExecutionJob.PRIORITY_HIGH else 1
        run_code.apply_async(
            args=[str(job.id)],
            queue=queue,
            priority=celery_priority,
        )

        log_execution_enqueue(
            job_id=job.id,
            user_id=request.user.id,
            language=language,
            queue=queue,
            source=source,
        )

        return Response({"job_id": str(job.id)}, status=202)


# SECURITY AUDIT: permission confirmed — IsAuthenticated; queryset filtered by user=request.user.
class ExecutionJobView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, job_id):
        try:
            job = ExecutionJob.objects.get(id=job_id, user=request.user)
        except ExecutionJob.DoesNotExist:
            return Response({"error": "Not found"}, status=404)

        redis_client = _redis_client()
        user_id = str(request.user.id)
        pending_high = int(redis_client.get(f"exec:fair:{user_id}:pending:high") or 0)
        pending_low = int(redis_client.get(f"exec:fair:{user_id}:pending:low") or 0)

        response = {
            "job_id": str(job.id),
            "status": job.status,
            "language": job.language,
            "stdout": job.stdout,
            "stderr": job.stderr,
            "exit_code": job.exit_code,
            "duration_ms": job.duration_ms,
            "queued_at": job.queued_at,
            "started_at": job.started_at,
            "priority": job.priority,
            "source": job.source,
        }

        if job.status == ExecutionJob.STATUS_QUEUED:
            response["queue_position"] = (
                pending_high if job.priority == ExecutionJob.PRIORITY_HIGH else pending_low
            )

        return Response(response)
