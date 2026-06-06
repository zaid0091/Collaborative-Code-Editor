"""Shared exception handling for DRF."""

from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def custom_exception_handler(exc, context):
    """Return standardized errors: {error: true, detail, code}."""
    response = drf_exception_handler(exc, context)

    if response is not None:
        detail = response.data
        if isinstance(detail, dict):
            if "detail" in detail and len(detail) == 1:
                message = detail["detail"]
            else:
                message = detail
        elif isinstance(detail, list):
            message = detail
        else:
            message = str(detail)

        code = _resolve_error_code(response.status_code, exc)
        response.data = {
            "error": True,
            "detail": message,
            "code": code,
        }
        return response

    detail = str(exc) if settings.DEBUG else "An unexpected error occurred."
    return Response(
        {
            "error": True,
            "detail": detail,
            "code": "internal_server_error",
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _resolve_error_code(status_code: int, exc) -> str:
    default_codes = {
        400: "bad_request",
        401: "not_authenticated",
        403: "permission_denied",
        404: "not_found",
        405: "method_not_allowed",
        409: "conflict",
        429: "throttled",
        500: "internal_server_error",
    }
    if hasattr(exc, "default_code"):
        return exc.default_code
    return default_codes.get(status_code, "error")
