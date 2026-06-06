"""Health check endpoint."""

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        checks = {}

        try:
            from django.db import connection

            connection.ensure_connection()
            checks["database"] = "ok"
        except Exception as exc:
            checks["database"] = f"error: {exc}"

        try:
            from django.core.cache import cache

            cache.set("health_check", "1", 5)
            checks["redis"] = "ok"
        except Exception as exc:
            checks["redis"] = f"error: {exc}"

        all_ok = all(value == "ok" for value in checks.values())
        return Response(
            {"status": "healthy" if all_ok else "degraded", "checks": checks},
            status=200 if all_ok else 503,
        )
