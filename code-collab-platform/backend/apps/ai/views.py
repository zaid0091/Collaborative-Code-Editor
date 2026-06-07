"""AI API views."""

from __future__ import annotations

import asyncio
import json
import uuid

import redis
from django.conf import settings
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai.rate_limit import check_and_consume_tokens, get_usage
from apps.ai.services import get_provider, strip_secrets
from apps.execution.scheduler import scheduler


def _redis_client():
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


# SECURITY AUDIT: permission confirmed — IsAuthenticated; secrets stripped before provider call.
class InlineCompleteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        context = request.data.get("code_context", "")
        language = request.data.get("language", "python")

        estimated = len(context) // 4 + 100
        if not check_and_consume_tokens(str(request.user.id), estimated):
            return Response({"error": "Daily token budget exceeded"}, status=429)

        clean_context = strip_secrets(context)

        messages = [
            {
                "role": "system",
                "content": (
                    f"You are a code completion assistant for {language}. "
                    "Complete the code at the cursor position. "
                    "Return only the completion text, no explanation."
                ),
            },
            {
                "role": "user",
                "content": f"Complete this {language} code:\n{clean_context}",
            },
        ]

        provider = get_provider()
        suggestion = asyncio.run(provider.complete(messages, max_tokens=200))

        return Response({"suggestion": suggestion})


# SECURITY AUDIT: permission confirmed — IsAuthenticated; secrets stripped before provider call.
class ExplainSelectionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        selected_code = request.data.get("selected_code", "")
        language = request.data.get("language", "python")

        if not check_and_consume_tokens(str(request.user.id), len(selected_code) // 4 + 100):
            return Response({"error": "Daily token budget exceeded"}, status=429)

        clean_code = strip_secrets(selected_code)

        messages = [
            {"role": "system", "content": "Explain code clearly and concisely."},
            {
                "role": "user",
                "content": f"Explain this {language} code:\n```\n{clean_code}\n```",
            },
        ]

        provider = get_provider()
        explanation = asyncio.run(provider.complete(messages, max_tokens=400))

        return Response({"explanation": explanation})


# SECURITY AUDIT: permission confirmed — IsAuthenticated; job ownership stored in Redis meta key.
class DetectBugsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        code = request.data.get("code", "")
        language = request.data.get("language", "python")
        file_id = request.data.get("file_id")

        if not check_and_consume_tokens(str(request.user.id), len(code) // 4 + 200):
            return Response({"error": "Daily token budget exceeded"}, status=429)

        allowed, stats = scheduler.check_and_reserve(str(request.user.id), "low")
        if not allowed:
            return Response(
                {
                    "error": "Too many concurrent AI jobs",
                    "retry_after_sec": stats.get("retry_after_sec", 30),
                },
                status=429,
            )

        from apps.ai.tasks import detect_bugs_task

        job_id = str(uuid.uuid4())
        redis_client = _redis_client()
        redis_client.setex(
            f"ai:bugs:meta:{job_id}",
            3600,
            json.dumps({"user_id": str(request.user.id)}),
        )
        detect_bugs_task.apply_async(
            args=[job_id, str(request.user.id), code, language, file_id],
            queue="execution.low",
            priority=1,
        )

        return Response({"job_id": job_id}, status=202)


# SECURITY AUDIT: permission confirmed — IsAuthenticated; result access limited to job owner.
class DetectBugsResultView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, job_id):
        redis_client = _redis_client()
        meta_raw = redis_client.get(f"ai:bugs:meta:{job_id}")
        if meta_raw:
            meta = json.loads(meta_raw)
            if meta.get("user_id") != str(request.user.id):
                return Response({"error": "Not found"}, status=404)
        else:
            return Response({"status": "pending"})

        result = redis_client.get(f"ai:bugs:{job_id}")
        if not result:
            return Response({"status": "pending"})
        return Response({"status": "complete", **json.loads(result)})


# SECURITY AUDIT: permission confirmed — IsAuthenticated; returns caller's usage only.
class AIUsageView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_usage(str(request.user.id)))
