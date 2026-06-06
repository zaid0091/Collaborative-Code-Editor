from django.contrib.auth.models import AnonymousUser

from apps.users.jwt_utils import decode_token
from apps.users.models import User


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
