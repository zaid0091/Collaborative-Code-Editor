import asyncio
import base64
from unittest.mock import patch

import pytest
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser
from django.test.utils import override_settings

from apps.collaboration.consumers import CollaborationConsumer
from apps.files.models import File
from apps.users.models import User
from apps.workspaces.models import Project, Workspace, WorkspaceMember

CHANNEL_LAYERS = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
}


@pytest.fixture(autouse=True)
def mock_celery_apply(monkeypatch):
    monkeypatch.setattr(
        "tasks.persist_updates.flush_operations_to_db.apply_async",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "tasks.persist_updates.idle_compact.apply_async",
        lambda *args, **kwargs: None,
    )


@pytest.fixture
def async_redis():
    from apps.collaboration.tests.fake_async_redis import FakeAsyncRedis

    client = FakeAsyncRedis()
    CollaborationConsumer._redis_override = client
    yield client
    CollaborationConsumer._redis_override = None


@pytest.fixture
def owner(db):
    return User.objects.create_user(
        email="owner@example.com",
        display_name="Owner",
        password="SecurePass123!",
    )


@pytest.fixture
def stranger(db):
    return User.objects.create_user(
        email="stranger@example.com",
        display_name="Stranger",
        password="SecurePass123!",
    )


@pytest.fixture
def collab_file(owner):
    workspace = Workspace.objects.create(name="Collab WS", owner=owner)
    WorkspaceMember.objects.create(
        workspace=workspace,
        user=owner,
        role=WorkspaceMember.ROLE_OWNER,
    )
    project = Project.objects.create(
        workspace=workspace,
        name="Collab Project",
        created_by=owner,
    )
    file_obj = File.objects.create(
        project=project,
        path="main.py",
        content='print("hello")',
    )
    return file_obj


def build_communicator(user, file_obj):
    communicator = WebsocketCommunicator(
        CollaborationConsumer.as_asgi(),
        f"/ws/collab/{file_obj.id}/",
    )
    communicator.scope["url_route"] = {"kwargs": {"file_id": str(file_obj.id)}}
    communicator.scope["user"] = user
    return communicator


async def drain_initial_messages(communicator):
    await asyncio.sleep(0.05)
    messages = []
    while len(messages) < 3:
        try:
            messages.append(await asyncio.wait_for(communicator.receive_json_from(), timeout=0.3))
        except TimeoutError:
            break
    return messages


@override_settings(CHANNEL_LAYERS=CHANNEL_LAYERS)
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_connect_rejects_anonymous_user(async_redis, collab_file):
    communicator = build_communicator(AnonymousUser(), collab_file)

    connected, _close_code = await communicator.connect()

    assert connected is False
    await communicator.disconnect()


@override_settings(CHANNEL_LAYERS=CHANNEL_LAYERS)
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_connect_rejects_non_member(async_redis, collab_file, stranger):
    communicator = build_communicator(stranger, collab_file)

    connected, _close_code = await communicator.connect()

    assert connected is False
    await communicator.disconnect()


@override_settings(CHANNEL_LAYERS=CHANNEL_LAYERS)
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_connect_accepts_workspace_member(async_redis, collab_file, owner):
    communicator = build_communicator(owner, collab_file)

    connected, _close_code = await communicator.connect()

    assert connected is True
    messages = await drain_initial_messages(communicator)
    message_types = {message["type"] for message in messages}
    assert "server_version" in message_types
    assert "user_joined" in message_types

    editors = await async_redis.scard(f"file:{collab_file.id}:editors")
    assert editors == 1

    await communicator.disconnect()


@override_settings(CHANNEL_LAYERS=CHANNEL_LAYERS)
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_update_message_appends_to_redis_buffer(async_redis, collab_file, owner):
    communicator = build_communicator(owner, collab_file)
    await communicator.connect()
    await drain_initial_messages(communicator)

    update_b64 = base64.b64encode(b"fake-yjs-update").decode()
    await communicator.send_json_to({"type": "update", "update": update_b64})

    ack = await communicator.receive_json_from()
    assert ack["type"] == "ack"
    assert ack["version"] == 1

    buffered = await async_redis.lrange(f"file:{collab_file.id}:updates", 0, -1)
    assert buffered == [update_b64]

    await communicator.disconnect()


@override_settings(CHANNEL_LAYERS=CHANNEL_LAYERS)
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_update_message_broadcasts_to_group(async_redis, collab_file, owner):
    communicator_a = build_communicator(owner, collab_file)
    communicator_b = build_communicator(owner, collab_file)

    await communicator_a.connect()
    await drain_initial_messages(communicator_a)
    await communicator_b.connect()
    await drain_initial_messages(communicator_b)
    await communicator_a.receive_json_from()  # user_joined for B on A

    update_b64 = base64.b64encode(b"broadcast-me").decode()
    await communicator_a.send_json_to({"type": "update", "update": update_b64})
    await communicator_a.receive_json_from()  # ack

    received = await communicator_b.receive_json_from()
    assert received == {"type": "update", "update": update_b64}

    await communicator_a.disconnect()
    await communicator_b.disconnect()


@override_settings(CHANNEL_LAYERS=CHANNEL_LAYERS)
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_update_sender_does_not_receive_own_broadcast(async_redis, collab_file, owner):
    communicator = build_communicator(owner, collab_file)
    await communicator.connect()
    await drain_initial_messages(communicator)

    update_b64 = base64.b64encode(b"self-filter").decode()
    await communicator.send_json_to({"type": "update", "update": update_b64})
    ack = await communicator.receive_json_from()
    assert ack["type"] == "ack"

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(communicator.receive_json_from(), timeout=0.2)

    await communicator.disconnect()


@override_settings(CHANNEL_LAYERS=CHANNEL_LAYERS)
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_oversized_update_closes_connection_1009(async_redis, collab_file, owner):
    communicator = build_communicator(owner, collab_file)
    await communicator.connect()
    await drain_initial_messages(communicator)

    oversized = base64.b64encode(b"x" * (512 * 1024 + 1)).decode()
    await communicator.send_json_to({"type": "update", "update": oversized})

    _close_code, _close_reason = await communicator.receive_output(timeout=1)
    await communicator.disconnect()


@override_settings(CHANNEL_LAYERS=CHANNEL_LAYERS)
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_ping_receives_pong(async_redis, collab_file, owner):
    communicator = build_communicator(owner, collab_file)
    await communicator.connect()
    await drain_initial_messages(communicator)

    await communicator.send_json_to({"type": "ping"})
    response = await communicator.receive_json_from()
    assert response == {"type": "pong"}

    await communicator.disconnect()


@override_settings(CHANNEL_LAYERS=CHANNEL_LAYERS)
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_disconnect_removes_user_from_editors_set(async_redis, collab_file, owner):
    communicator = build_communicator(owner, collab_file)
    await communicator.connect()
    await drain_initial_messages(communicator)

    assert await async_redis.scard(f"file:{collab_file.id}:editors") == 1

    await communicator.disconnect()

    assert await async_redis.scard(f"file:{collab_file.id}:editors") == 0


@override_settings(CHANNEL_LAYERS=CHANNEL_LAYERS)
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_last_editor_disconnect_triggers_idle_compact(async_redis, collab_file, owner):
    communicator = build_communicator(owner, collab_file)
    await communicator.connect()
    await drain_initial_messages(communicator)

    with patch("tasks.persist_updates.idle_compact.apply_async") as mock_apply:
        await communicator.disconnect()
        mock_apply.assert_called_once_with(
            args=[str(collab_file.id)],
            queue="crdt.persist",
            countdown=30,
        )
