import threading
import uuid

import structlog
from django.contrib.auth.models import AnonymousUser

from apps.users.jwt_utils import decode_token
from apps.users.models import User

_correlation_local = threading.local()


def get_correlation_id() -> str | None:
    return getattr(_correlation_local, "correlation_id", None)


def bind_correlation_id(correlation_id: str) -> None:
    _correlation_local.correlation_id = correlation_id
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(correlation_id=correlation_id)


class CorrelationIDMiddleware:
    """Propagate X-Request-ID / generate correlation ID for structured logs."""

    HEADER = "X-Request-ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.META.get("HTTP_X_REQUEST_ID", "")
        if incoming:
            try:
                correlation_id = str(uuid.UUID(incoming))
            except ValueError:
                correlation_id = str(uuid.uuid4())
        else:
            correlation_id = str(uuid.uuid4())

        bind_correlation_id(correlation_id)
        request.correlation_id = correlation_id

        response = self.get_response(request)
        response[self.HEADER] = correlation_id
        return response


class JWTAuthMiddleware:
    """
    Attach authenticated user from Bearer JWT when present.
    Does not return 401 — DRF permission classes handle authorization.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.user = AnonymousUser()
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")

        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            if token:
                try:
                    payload = decode_token(token)
                    if payload.get("type") == "access":
                        request.user = (
                            User.objects.filter(
                                id=payload["user_id"],
                                is_active=True,
                            ).first()
                            or AnonymousUser()
                        )
                except Exception:
                    request.user = AnonymousUser()

        return self.get_response(request)
