import base64
from unittest.mock import patch

import pytest

from apps.collaboration import sync_engine
from apps.collaboration.sync_engine import build_sync_response
from apps.collaboration.tests.fake_async_redis import FakeAsyncRedis
from apps.files.models import File, FileVersion, OperationLog
from apps.users.models import User
from apps.workspaces.models import Project, Workspace, WorkspaceMember
from tasks.persist_updates import (
    compact_snapshot,
    flush_operations_to_db,
    idle_compact,
)


@pytest.fixture
def sync_redis(monkeypatch):
    import fakeredis

    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("tasks.persist_updates.get_sync_redis", lambda: client)
    return client


@pytest.fixture
def async_redis(monkeypatch):
    client = FakeAsyncRedis()
    sync_engine._redis_override = client
    yield client
    sync_engine._redis_override = None


@pytest.fixture
def owner(db):
    return User.objects.create_user(
        email="owner@example.com",
        display_name="Owner",
        password="SecurePass123!",
    )


@pytest.fixture
def file_obj(owner):
    workspace = Workspace.objects.create(name="Persist WS", owner=owner)
    WorkspaceMember.objects.create(
        workspace=workspace,
        user=owner,
        role=WorkspaceMember.ROLE_OWNER,
    )
    project = Project.objects.create(
        workspace=workspace,
        name="Persist Project",
        created_by=owner,
    )
    return File.objects.create(
        project=project,
        path="main.py",
        content='print("hello")',
    )


def test_flush_moves_redis_buffer_to_operation_log(sync_redis, file_obj):
    file_id = str(file_obj.id)
    sync_redis.rpush(f"file:{file_id}:updates", "upd1", "upd2")
    sync_redis.set(f"file:{file_id}:version", 2)

    flush_operations_to_db(file_id)

    logs = OperationLog.objects.filter(file_id=file_id).order_by("vector_clock")
    assert logs.count() == 2
    assert logs[0].operation_json["update"] == "upd1"
    assert logs[0].vector_clock == 1
    assert logs[1].operation_json["update"] == "upd2"
    assert logs[1].vector_clock == 2


def test_flush_empty_buffer_does_nothing(sync_redis, file_obj):
    file_id = str(file_obj.id)
    sync_redis.set(f"file:{file_id}:flush_scheduled", 1)

    flush_operations_to_db(file_id)

    assert OperationLog.objects.filter(file_id=file_id).count() == 0
    assert sync_redis.exists(f"file:{file_id}:flush_scheduled") == 0


def test_flush_trims_redis_after_insert(sync_redis, file_obj):
    file_id = str(file_obj.id)
    buffer_key = f"file:{file_id}:updates"
    sync_redis.rpush(buffer_key, "a", "b")
    sync_redis.set(f"file:{file_id}:version", 2)

    flush_operations_to_db(file_id)

    assert sync_redis.llen(buffer_key) == 0


def test_compact_merges_oplogs_into_snapshot(sync_redis, file_obj):
    file_id = str(file_obj.id)
    delta = base64.b64encode(b"+delta").decode()
    file_obj.yjs_snapshot = b"base"
    file_obj.compaction_checkpoint_version = 0
    file_obj.save(update_fields=["yjs_snapshot", "compaction_checkpoint_version"])

    OperationLog.objects.create(
        file=file_obj,
        operation_json={"update": delta},
        vector_clock=1,
    )
    sync_redis.set(f"file:{file_id}:version", 1)

    compact_snapshot(file_id)

    file_obj.refresh_from_db()
    assert file_obj.yjs_snapshot == b"base+delta"


def test_compact_deletes_oplogs_up_to_checkpoint(sync_redis, file_obj):
    file_id = str(file_obj.id)
    update = base64.b64encode(b"x").decode()
    OperationLog.objects.create(
        file=file_obj,
        operation_json={"update": update},
        vector_clock=1,
    )
    sync_redis.set(f"file:{file_id}:version", 1)

    compact_snapshot(file_id)

    assert OperationLog.objects.filter(file_id=file_id).count() == 0
    file_obj.refresh_from_db()
    assert file_obj.compaction_checkpoint_version == 1


def test_compact_resets_op_counter(sync_redis, file_obj):
    file_id = str(file_obj.id)
    update = base64.b64encode(b"x").decode()
    OperationLog.objects.create(
        file=file_obj,
        operation_json={"update": update},
        vector_clock=1,
    )
    sync_redis.set(f"file:{file_id}:version", 1)
    sync_redis.set(f"file:{file_id}:op_count", 250)

    compact_snapshot(file_id)

    assert int(sync_redis.get(f"file:{file_id}:op_count") or 0) == 0


def test_compact_creates_auto_file_version(sync_redis, file_obj):
    file_id = str(file_obj.id)
    update = base64.b64encode(b"x").decode()
    OperationLog.objects.create(
        file=file_obj,
        operation_json={"update": update},
        vector_clock=1,
    )
    sync_redis.set(f"file:{file_id}:version", 1)

    compact_snapshot(file_id)

    version = FileVersion.objects.get(file=file_obj)
    assert version.source == FileVersion.SOURCE_COMPACTION
    assert "Auto checkpoint v1" in version.label


def test_idle_compact_skips_if_editors_present(sync_redis, file_obj):
    file_id = str(file_obj.id)
    sync_redis.sadd(f"file:{file_id}:editors", "user-1")

    with patch("tasks.persist_updates.compact_snapshot.apply_async") as mock_apply:
        idle_compact(file_id)
        mock_apply.assert_not_called()


@pytest.fixture
def stale_sync_file(file_obj):
    file_obj.yjs_snapshot = b"snapshot-bytes"
    file_obj.compaction_checkpoint_version = 5
    file_obj.save(update_fields=["yjs_snapshot", "compaction_checkpoint_version"])
    return file_obj


@pytest.fixture
def recent_sync_file(file_obj):
    file_obj.compaction_checkpoint_version = 5
    file_obj.save(update_fields=["compaction_checkpoint_version"])
    OperationLog.objects.create(
        file=file_obj,
        operation_json={"update": "recent-op"},
        vector_clock=6,
    )
    return file_obj


@pytest.fixture
def buffered_sync_file(file_obj):
    file_obj.compaction_checkpoint_version = 3
    file_obj.save(update_fields=["compaction_checkpoint_version"])
    OperationLog.objects.create(
        file=file_obj,
        operation_json={"update": "pg-op"},
        vector_clock=4,
    )
    return file_obj


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_build_sync_response_returns_full_snapshot_for_stale_client(
    async_redis,
    stale_sync_file,
):
    file_id = str(stale_sync_file.id)
    async_redis.values[f"file:{file_id}:version"] = "7"

    response = await build_sync_response(file_id, last_known_version=2, client_state_vector=None)

    assert response["server_version"] == 7
    assert response["snapshot"] == base64.b64encode(b"snapshot-bytes").decode()
    assert response["missing_from_version"] == 5


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_build_sync_response_returns_only_delta_for_recent_client(
    async_redis,
    recent_sync_file,
):
    file_id = str(recent_sync_file.id)
    async_redis.values[f"file:{file_id}:version"] = "6"

    response = await build_sync_response(file_id, last_known_version=5, client_state_vector=None)

    assert response["snapshot"] is None
    assert response["missing_from_version"] == 5
    assert response["delta_updates"] == ["recent-op"]


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_build_sync_response_includes_redis_buffer_in_delta(
    async_redis,
    buffered_sync_file,
):
    file_id = str(buffered_sync_file.id)
    async_redis.values[f"file:{file_id}:version"] = "5"
    async_redis.lists[f"file:{file_id}:updates"] = ["buffer-op"]

    response = await build_sync_response(file_id, last_known_version=3, client_state_vector=None)

    assert response["delta_updates"] == ["pg-op", "buffer-op"]
