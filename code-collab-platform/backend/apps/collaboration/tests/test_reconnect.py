import asyncio
import base64
import socket
from unittest.mock import AsyncMock, patch

import pytest
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.test.utils import override_settings

from apps.collaboration import lifecycle, sync_engine
from apps.collaboration.consumers import CollaborationConsumer
from apps.collaboration.tests.fake_async_redis import FakeAsyncRedis
from apps.files.models import File, OperationLog
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
    client = FakeAsyncRedis()
    CollaborationConsumer._redis_override = client
    sync_engine._redis_override = client
    lifecycle._redis_override = client
    yield client
    CollaborationConsumer._redis_override = None
    sync_engine._redis_override = None
    lifecycle._redis_override = None


@pytest.fixture
def owner(db):
    return User.objects.create_user(
        email="reconnect@example.com",
        display_name="Reconnect User",
        password="SecurePass123!",
    )


@pytest.fixture
def collab_file(owner):
    workspace = Workspace.objects.create(name="Reconnect WS", owner=owner)
    WorkspaceMember.objects.create(
        workspace=workspace,
        user=owner,
        role=WorkspaceMember.ROLE_OWNER,
    )
    project = Project.objects.create(
        workspace=workspace,
        name="Reconnect Project",
        created_by=owner,
    )
    return File.objects.create(
        project=project,
        path="main.py",
        content='print("hello")',
    )


@pytest.fixture
def stale_file(collab_file):
    collab_file.yjs_snapshot = b"snapshot-bytes"
    collab_file.compaction_checkpoint_version = 5
    collab_file.save(update_fields=["yjs_snapshot", "compaction_checkpoint_version"])
    return collab_file


@pytest.fixture
def recent_file(collab_file):
    collab_file.compaction_checkpoint_version = 5
    collab_file.save(update_fields=["compaction_checkpoint_version"])
    OperationLog.objects.create(
        file=collab_file,
        operation_json={"update": "recent-op"},
        vector_clock=6,
    )
    return collab_file


@pytest.fixture
def buffered_file(collab_file):
    collab_file.compaction_checkpoint_version = 3
    collab_file.save(update_fields=["compaction_checkpoint_version"])
    OperationLog.objects.create(
        file=collab_file,
        operation_json={"update": "pg-op"},
        vector_clock=4,
    )
    return collab_file


@pytest.fixture
def oplog_file(collab_file):
    collab_file.compaction_checkpoint_version = 2
    collab_file.save(update_fields=["compaction_checkpoint_version"])
    OperationLog.objects.create(
        file=collab_file,
        operation_json={"update": "op-3"},
        vector_clock=3,
    )
    OperationLog.objects.create(
        file=collab_file,
        operation_json={"update": "op-4"},
        vector_clock=4,
    )
    return collab_file


@pytest.fixture
def cross_node_file(collab_file):
    collab_file.compaction_checkpoint_version = 3
    collab_file.save(update_fields=["compaction_checkpoint_version"])
    OperationLog.objects.create(
        file=collab_file,
        operation_json={"update": "pg-op"},
        vector_clock=4,
    )
    return collab_file


def build_communicator(user, file_obj):
    communicator = WebsocketCommunicator(
        CollaborationConsumer.as_asgi(),
        f"/ws/collab/{file_obj.id}/",
    )
    communicator.scope["url_route"] = {"kwargs": {"file_id": str(file_obj.id)}}
    communicator.scope["user"] = user
    return communicator


async def connect_and_drain(communicator):
    connected, _close_code = await communicator.connect()
    assert connected is True
    await asyncio.sleep(0.05)
    messages = []
    while len(messages) < 3:
        try:
            messages.append(await asyncio.wait_for(communicator.receive_json_from(), timeout=0.3))
        except TimeoutError:
            break
    return messages


async def send_sync_request(communicator, last_known_version):
    await communicator.send_json_to(
        {
            "type": "sync_request",
            "last_known_version": last_known_version,
            "client_state_vector": None,
        }
    )
    sync_response = await communicator.receive_json_from()
    sync_complete = await communicator.receive_json_from()
    return sync_response, sync_complete


@override_settings(CHANNEL_LAYERS=CHANNEL_LAYERS)
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_sync_request_returns_full_snapshot_when_client_version_is_none(
    async_redis,
    owner,
    stale_file,
):
    """Section 4.7.3 — cold reconnect: client has no version, receives compaction snapshot."""
    file_id = str(stale_file.id)
    async_redis.values[f"file:{file_id}:version"] = "7"

    communicator = build_communicator(owner, stale_file)
    await connect_and_drain(communicator)

    sync_response, sync_complete = await send_sync_request(communicator, None)

    assert sync_response["type"] == "sync_response"
    assert sync_response["snapshot"] == base64.b64encode(b"snapshot-bytes").decode()
    assert sync_response["missing_from_version"] == 5
    assert sync_complete == {"type": "sync_complete", "server_version": 7}

    await communicator.disconnect()


@override_settings(CHANNEL_LAYERS=CHANNEL_LAYERS)
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_sync_request_returns_delta_when_client_version_recent(
    async_redis,
    owner,
    recent_file,
):
    """Section 4.7.3 — warm reconnect: recent client receives delta only, no snapshot."""
    file_id = str(recent_file.id)
    async_redis.values[f"file:{file_id}:version"] = "6"

    communicator = build_communicator(owner, recent_file)
    await connect_and_drain(communicator)

    sync_response, sync_complete = await send_sync_request(communicator, 5)

    assert sync_response["snapshot"] is None
    assert sync_response["delta_updates"] == ["recent-op"]
    assert sync_complete["server_version"] == 6

    await communicator.disconnect()


@override_settings(CHANNEL_LAYERS=CHANNEL_LAYERS)
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_sync_request_includes_redis_buffer_in_delta(
    async_redis,
    owner,
    buffered_file,
):
    """Section 4.7.3 — reconnect merges unflushed Redis hot-buffer ops into delta."""
    file_id = str(buffered_file.id)
    async_redis.values[f"file:{file_id}:version"] = "5"
    async_redis.lists[f"file:{file_id}:updates"] = ["buffer-op"]

    communicator = build_communicator(owner, buffered_file)
    await connect_and_drain(communicator)

    sync_response, _sync_complete = await send_sync_request(communicator, 3)

    assert sync_response["delta_updates"] == ["pg-op", "buffer-op"]

    await communicator.disconnect()


@override_settings(CHANNEL_LAYERS=CHANNEL_LAYERS)
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_sync_request_includes_oplog_delta_since_last_version(
    async_redis,
    owner,
    oplog_file,
):
    """Section 4.7.3 — reconnect replays OperationLog entries since client version."""
    file_id = str(oplog_file.id)
    async_redis.values[f"file:{file_id}:version"] = "4"

    communicator = build_communicator(owner, oplog_file)
    await connect_and_drain(communicator)

    sync_response, _sync_complete = await send_sync_request(communicator, 2)

    assert sync_response["delta_updates"] == ["op-3", "op-4"]

    await communicator.disconnect()


@override_settings(CHANNEL_LAYERS=CHANNEL_LAYERS)
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_sync_complete_message_sent_after_sync_response(
    async_redis,
    owner,
    recent_file,
):
    """Section 4.7.1 — sync_complete ack follows sync_response in reconnect handshake."""
    file_id = str(recent_file.id)
    async_redis.values[f"file:{file_id}:version"] = "6"

    communicator = build_communicator(owner, recent_file)
    await connect_and_drain(communicator)

    sync_response, sync_complete = await send_sync_request(communicator, 5)

    assert sync_response["type"] == "sync_response"
    assert sync_complete["type"] == "sync_complete"
    assert sync_complete["server_version"] == sync_response["server_version"]

    await communicator.disconnect()


@override_settings(CHANNEL_LAYERS=CHANNEL_LAYERS)
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_heartbeat_timeout_closes_connection(async_redis, owner, collab_file):
    """Section 4.7.2 — silent client is disconnected after HEARTBEAT_TIMEOUT_SEC."""
    communicator = build_communicator(owner, collab_file)

    with patch.object(CollaborationConsumer, "HEARTBEAT_TIMEOUT_SEC", 0):
        with patch("apps.collaboration.consumers.asyncio.sleep", new=AsyncMock()):
            connected, _close_code = await communicator.connect()
            assert connected is True
            await asyncio.sleep(0.05)

            close_event = None
            for _ in range(5):
                event = await communicator.receive_output(timeout=1)
                if event["type"] == "websocket.close":
                    close_event = event
                    break

            assert close_event is not None
            assert close_event["code"] == 4002

    await communicator.disconnect()


@override_settings(CHANNEL_LAYERS=CHANNEL_LAYERS)
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_server_draining_message_sent_to_connected_clients(
    async_redis,
    owner,
    collab_file,
):
    """Section 4.7.2 — graceful drain notifies connected clients before shutdown."""
    communicator = build_communicator(owner, collab_file)
    await connect_and_drain(communicator)

    channel_layer = get_channel_layer()
    await channel_layer.group_send(
        f"file_{collab_file.id}",
        {"type": "broadcast.server_draining"},
    )

    draining_message = await communicator.receive_json_from()
    assert draining_message["type"] == "server_draining"
    assert "message" in draining_message
    close_event = await communicator.receive_output(timeout=1)
    assert close_event["type"] == "websocket.close"
    assert close_event["code"] == 4010

    await communicator.disconnect()


@override_settings(CHANNEL_LAYERS=CHANNEL_LAYERS)
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_reconnecting_client_on_different_node_gets_correct_state(
    async_redis,
    owner,
    cross_node_file,
):
    """Section 4.7.3 — cross-node reconnect reads shared Redis/PG state after prior session ends."""
    file_id = str(cross_node_file.id)
    async_redis.values[f"file:{file_id}:version"] = "5"
    async_redis.lists[f"file:{file_id}:updates"] = ["buffer-op"]

    first = build_communicator(owner, cross_node_file)
    await connect_and_drain(first)
    await first.disconnect()

    second = build_communicator(owner, cross_node_file)
    await connect_and_drain(second)

    sync_response, sync_complete = await send_sync_request(second, 3)

    assert sync_response["delta_updates"] == ["pg-op", "buffer-op"]
    assert sync_complete["server_version"] == 5

    await second.disconnect()


@override_settings(CHANNEL_LAYERS=CHANNEL_LAYERS)
@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_connect_rejected_when_node_is_draining(async_redis, owner, collab_file):
    """Section 4.7.2 — new connections rejected while node is draining."""
    node_key = f"node:{socket.gethostname()}:draining"
    async_redis.values[node_key] = "1"

    communicator = build_communicator(owner, collab_file)
    connected, _close_code = await communicator.connect()

    assert connected is True
    draining_message = await communicator.receive_json_from()
    assert draining_message["type"] == "server_draining"
    assert "message" in draining_message
    close_event = await communicator.receive_output(timeout=1)
    assert close_event["code"] == 4010

    await communicator.disconnect()
