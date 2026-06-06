from unittest.mock import MagicMock

import pytest
from channels.testing import WebsocketCommunicator

from apps.collaboration.consumers import CollaborationConsumer
from apps.collaboration.tests.fake_async_redis import FakeAsyncRedis
from apps.collaboration.ws_abuse import WSAbuseGuard
from apps.files.models import File
from apps.users.models import User
from apps.workspaces.models import Project, Workspace, WorkspaceMember


@pytest.fixture
def async_redis():
    client = FakeAsyncRedis()
    CollaborationConsumer._redis_override = client
    yield client
    CollaborationConsumer._redis_override = None


@pytest.fixture
def guard(async_redis):
    return WSAbuseGuard(async_redis)


@pytest.fixture
def owner(db):
    return User.objects.create_user(
        email="abuse@example.com",
        display_name="Abuse Tester",
        password="SecurePass123!",
    )


@pytest.fixture
def collab_file(owner):
    workspace = Workspace.objects.create(name="Abuse WS", owner=owner)
    WorkspaceMember.objects.create(
        workspace=workspace,
        user=owner,
        role=WorkspaceMember.ROLE_OWNER,
    )
    project = Project.objects.create(
        workspace=workspace,
        name="Abuse Project",
        created_by=owner,
    )
    return File.objects.create(
        project=project,
        path="abuse.py",
        content='print("abuse")',
    )


@pytest.mark.asyncio
async def test_allow_within_limits(guard):
    session_id = "session-allow"

    for _ in range(5):
        result = await guard.check(session_id, "user-1", "update")
        assert result == "allow"

    for _ in range(5):
        result = await guard.check(session_id, "user-1", "awareness")
        assert result == "allow"


@pytest.mark.asyncio
async def test_warn_on_soft_exceed(guard):
    session_id = "session-warn"

    for _ in range(30):
        assert await guard.check(session_id, "user-1", "update") == "allow"

    assert await guard.check(session_id, "user-1", "update") == "warn"


@pytest.mark.asyncio
async def test_drop_on_awareness_exceed(guard):
    session_id = "session-drop"

    for _ in range(20):
        assert await guard.check(session_id, "user-1", "awareness") == "allow"

    assert await guard.check(session_id, "user-1", "awareness") == "drop"


@pytest.mark.asyncio
async def test_disconnect_on_total_burst_exceed(guard):
    session_id = "session-burst"

    for index in range(1, 101):
        result = await guard.check(session_id, "user-1", "unknown")
        if index <= 60:
            assert result == "allow"
        else:
            assert result == "warn"

    assert await guard.check(session_id, "user-1", "unknown") == "disconnect"


@pytest.mark.asyncio
async def test_record_violation_increments_strikes(guard, async_redis):
    result = await guard.record_violation("user-42", "session-1", "message_rate_exceeded")

    assert result["strikes"] == 1
    assert result["banned"] is False
    assert await async_redis.get("ws:abuse:user-42:strikes") == "1"
    assert await async_redis.get("ws:abuse:user-42:recent") == "1"


@pytest.mark.asyncio
async def test_three_recent_violations_triggers_ban(guard, async_redis):
    user_id = "user-ban"

    for _ in range(2):
        result = await guard.record_violation(user_id, "session-1", "message_rate_exceeded")
        assert result["banned"] is False

    result = await guard.record_violation(user_id, "session-1", "message_rate_exceeded")
    assert result["banned"] is True
    assert result["ban_duration_sec"] == 300
    assert await guard.is_banned(user_id) is True


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_banned_user_rejected_on_connect(async_redis, collab_file, owner):
    await async_redis.set(f"ws:ban:{owner.id}", 1, ex=300)

    communicator = WebsocketCommunicator(
        CollaborationConsumer.as_asgi(),
        f"/ws/collab/{collab_file.id}/",
    )
    communicator.scope["url_route"] = {"kwargs": {"file_id": str(collab_file.id)}}
    communicator.scope["user"] = owner

    connected, close_code = await communicator.connect()

    assert connected is False
    assert close_code == 4003
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_local_fallback_used_when_redis_unavailable():
    broken_redis = MagicMock()
    broken_redis.pipeline.side_effect = ConnectionError("redis down")
    guard = WSAbuseGuard(broken_redis)
    session_id = "session-fallback"

    for _ in range(30):
        assert guard._check_local_fallback(session_id, "update") == "allow"

    assert guard._check_local_fallback(session_id, "update") == "warn"

    guard._local_counts.clear()
    for _ in range(20):
        assert guard._check_local_fallback(session_id, "awareness") == "allow"

    assert guard._check_local_fallback(session_id, "awareness") == "drop"


@pytest.mark.asyncio
async def test_update_messages_counted_separately_from_awareness(guard):
    session_id = "session-separate"

    for _ in range(30):
        assert await guard.check(session_id, "user-1", "update") == "allow"

    for _ in range(20):
        assert await guard.check(session_id, "user-1", "awareness") == "allow"

    assert await guard.check(session_id, "user-1", "update") == "warn"
    assert await guard.check(session_id, "user-1", "awareness") == "drop"
