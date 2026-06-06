from urllib.parse import urlencode

import pytest
from django.contrib.auth.models import AnonymousUser

from apps.users.jwt_utils import generate_access_token
from apps.users.models import User
from config.asgi import application
from realtime.middleware import JWTAuthMiddlewareStack
from realtime.routing import websocket_urlpatterns


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="ws-user@example.com",
        display_name="WS User",
        password="SecurePass123!",
    )


def test_http_routes_to_django_app():
    assert "http" in application.application_mapping
    assert "websocket" in application.application_mapping
    assert application.application_mapping["http"] is not None


def test_ws_url_matches_collab_pattern():
    pattern = websocket_urlpatterns[0].pattern.regex
    file_id = "550e8400-e29b-41d4-a716-446655440000"

    assert pattern.match(f"ws/collab/{file_id}/")


def test_invalid_file_id_does_not_match_route():
    pattern = websocket_urlpatterns[0].pattern.regex

    assert pattern.match("ws/collab/not-a-uuid/") is None
    assert pattern.match("ws/collab/123/") is None


@pytest.mark.asyncio
@pytest.mark.django_db
async def test_jwt_middleware_sets_anonymous_user_on_missing_token():
    captured = {}

    async def inner(scope, receive, send):
        captured["user"] = scope["user"]

    middleware = JWTAuthMiddlewareStack(inner)
    scope = {"type": "websocket", "query_string": b""}

    await middleware(scope, _noop_receive, _noop_send)

    assert isinstance(captured["user"], AnonymousUser)
    assert captured["user"].is_anonymous


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_jwt_middleware_sets_user_on_valid_token(user):
    captured = {}

    async def inner(scope, receive, send):
        captured["user"] = scope["user"]

    token = generate_access_token(user)
    middleware = JWTAuthMiddlewareStack(inner)
    scope = {
        "type": "websocket",
        "query_string": urlencode({"token": token}).encode(),
    }

    await middleware(scope, _noop_receive, _noop_send)

    assert captured["user"].id == user.id
    assert captured["user"].email == user.email


async def _noop_receive():
    return {"type": "websocket.disconnect"}


async def _noop_send(_message):
    return None
