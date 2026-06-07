"""Channels middleware for WebSocket authentication."""

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser

from apps.users.jwt_utils import decode_token
from apps.users.models import User


@database_sync_to_async
def _load_user(user_id: str):
    try:
        return User.objects.get(id=user_id, is_active=True)
    except User.DoesNotExist:
        return AnonymousUser()


def _extract_token(scope) -> str | None:
    query_string = scope.get("query_string", b"").decode()
    params = parse_qs(query_string)
    token = params.get("token", [None])[0]
    return token or None


class JWTAuthMiddlewareStack:
    """
    Channels middleware that extracts JWT from query string and
    attaches authenticated user to scope before consumer receives it.

    Reads token from: ?token=<jwt> in WebSocket URL
    Sets scope['user'] to authenticated User or AnonymousUser
    Does NOT reject here — consumer's connect() enforces auth
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        scope["user"] = AnonymousUser()
        token = _extract_token(scope)

        if token:
            try:
                payload = decode_token(token)
                if payload.get("type") == "access":
                    scope["user"] = await _load_user(payload["user_id"])
                    scope["jwt_exp"] = payload.get("exp")
            except Exception:
                scope["user"] = AnonymousUser()

        await self.inner(scope, receive, send)
