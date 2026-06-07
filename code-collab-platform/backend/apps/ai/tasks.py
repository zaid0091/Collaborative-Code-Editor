"""Celery tasks for AI analysis on execution.low queue."""

from __future__ import annotations

import asyncio
import json
import os

import redis
from celery import shared_task

from apps.execution.scheduler import scheduler


def _redis_client():
    try:
        from django.conf import settings

        return redis.from_url(settings.REDIS_URL, decode_responses=True)
    except Exception:
        return redis.from_url(
            os.environ.get("REDIS_URL", "redis://redis:6379/0"), decode_responses=True
        )


@shared_task(name="ai.detect_bugs", bind=True)
def detect_bugs_task(
    self,
    job_id: str,
    user_id: str,
    code: str,
    language: str,
    file_id: str | None = None,
):
    """Run bug detection via AI provider; store result in Redis for polling."""
    del self, file_id
    redis_client = _redis_client()
    scheduler.on_job_start(user_id, "low")

    try:
        from apps.ai.services import get_provider, strip_secrets

        clean_code = strip_secrets(code)

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a code review assistant. Identify bugs, security issues, "
                    "and code quality problems. Return a JSON array of issues with fields: "
                    '{line: int|null, severity: "error"|"warning"|"info", '
                    "message: str, suggestion: str}"
                ),
            },
            {
                "role": "user",
                "content": f"Review this {language} code:\n```\n{clean_code}\n```",
            },
        ]

        provider = get_provider()
        loop = asyncio.new_event_loop()
        try:
            response = loop.run_until_complete(provider.complete(messages, max_tokens=800))
        finally:
            loop.close()

        try:
            issues = json.loads(response)
        except json.JSONDecodeError:
            issues = [
                {
                    "line": None,
                    "severity": "info",
                    "message": response,
                    "suggestion": "",
                }
            ]

        result = {"issues": issues, "language": language}
        redis_client.setex(f"ai:bugs:{job_id}", 3600, json.dumps(result))

    except Exception as exc:
        redis_client.setex(
            f"ai:bugs:{job_id}",
            3600,
            json.dumps({"error": str(exc), "issues": []}),
        )

    finally:
        scheduler.on_job_complete(user_id, "low")
