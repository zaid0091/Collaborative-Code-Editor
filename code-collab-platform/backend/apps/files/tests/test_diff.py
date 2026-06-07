import json
from unittest.mock import patch

import fakeredis
import pytest

from apps.files.diff_engine import (
    DiffTooLargeError,
    compute_diff,
    get_cache_key,
)
from apps.files.merge_engine import apply_resolutions, three_way_diff
from apps.files.models import File, FileVersion, MergeJob
from apps.users.models import User
from apps.workspaces.models import Project, Workspace, WorkspaceMember


@pytest.fixture
def fake_diff_redis():
    client = fakeredis.FakeRedis(decode_responses=True)
    with patch("apps.files.diff_engine._get_redis", lambda: client):
        yield client
    client.flushall()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="diff@example.com",
        display_name="Diff User",
        password="SecurePass123!",
    )


@pytest.fixture
def file_obj(db, user):
    workspace = Workspace.objects.create(name="Diff WS", owner=user)
    WorkspaceMember.objects.create(
        workspace=workspace,
        user=user,
        role=WorkspaceMember.ROLE_OWNER,
    )
    project = Project.objects.create(workspace=workspace, name="Diff Project", created_by=user)
    return File.objects.create(project=project, path="diff.py", content="alpha\nbeta\ngamma")


def test_myers_diff_detects_addition():
    result = compute_diff("alpha\nbeta", "alpha\nbeta\nnewline", algorithm="myers")

    assert result["stats"]["added"] >= 1
    assert any(line["type"] == "+" for hunk in result["hunks"] for line in hunk["lines"])


def test_myers_diff_detects_deletion():
    result = compute_diff("alpha\nbeta\ngamma", "alpha\nbeta", algorithm="myers")

    assert result["stats"]["removed"] >= 1
    assert any(line["type"] == "-" for hunk in result["hunks"] for line in hunk["lines"])


def test_myers_diff_detects_modification():
    result = compute_diff("alpha\nbeta\ngamma", "alpha\nBETA\ngamma", algorithm="myers")

    assert result["stats"]["added"] >= 1
    assert result["stats"]["removed"] >= 1


def test_patience_diff_handles_moved_block():
    base = "HEADER\nblockA\nblockB\nblockC\nFOOTER"
    moved = "HEADER\nblockB\nblockC\nblockA\nFOOTER"

    result = compute_diff(base, moved, algorithm="patience")

    assert result["stats"]["added"] >= 1
    assert result["stats"]["removed"] >= 1
    assert result["hunks"]


def test_three_way_diff_auto_merges_non_conflicting():
    base = "A\nB\nC"
    ours = "A\nB2\nC"
    theirs = "A\nB\nC\nD"

    result = three_way_diff(base, ours, theirs)

    assert result["has_conflicts"] is False
    assert "B2" in result["auto_merged"]
    assert "D" in result["auto_merged"]


def test_three_way_diff_detects_conflict_on_same_region():
    base = "A\nB\nC"
    ours = "A\nOUR\nC"
    theirs = "A\nTHEIR\nC"

    result = three_way_diff(base, ours, theirs)

    assert result["has_conflicts"] is True
    assert len(result["conflicts"]) == 1
    assert result["conflicts"][0]["ours"] == "OUR"
    assert result["conflicts"][0]["theirs"] == "THEIR"


def test_three_way_diff_returns_conflict_markers():
    result = three_way_diff("A\nB\nC", "A\nOUR\nC", "A\nTHEIR\nC")

    assert "<<<<<<< current" in result["auto_merged"]
    assert "=======" in result["auto_merged"]
    assert ">>>>>>> incoming" in result["auto_merged"]


@pytest.mark.django_db
def test_apply_resolutions_ours_keeps_current(user, file_obj):
    base_version = FileVersion.objects.create(
        file=file_obj,
        snapshot="line1\nline2\nline3",
        label="base",
        source=FileVersion.SOURCE_COMPACTION,
        created_by=user,
    )
    source_version = FileVersion.objects.create(
        file=file_obj,
        snapshot="line1\ntheirs\nline3",
        label="incoming",
        source=FileVersion.SOURCE_MANUAL,
        created_by=user,
    )
    file_obj.content = "line1\nours\nline3"
    file_obj.save()

    preview = three_way_diff(base_version.snapshot, file_obj.content, source_version.snapshot)
    conflict = preview["conflicts"][0]

    merge_job = MergeJob.objects.create(
        file=file_obj,
        base_version=source_version,
        status=MergeJob.STATUS_CONFLICT,
        conflict_hunks=preview["conflicts"],
    )

    with patch("tasks.persist_updates.compact_snapshot.apply_async"):
        apply_resolutions(
            str(file_obj.id),
            [{"hunk_id": conflict["hunk_id"], "choice": "ours"}],
            str(merge_job.id),
            str(user.id),
        )

    file_obj.refresh_from_db()
    assert "ours" in file_obj.content
    assert "<<<<<<<" not in file_obj.content


@pytest.mark.django_db
def test_apply_resolutions_theirs_uses_incoming(user, file_obj):
    base_version = FileVersion.objects.create(
        file=file_obj,
        snapshot="line1\nline2\nline3",
        label="base",
        source=FileVersion.SOURCE_COMPACTION,
        created_by=user,
    )
    source_version = FileVersion.objects.create(
        file=file_obj,
        snapshot="line1\ntheirs\nline3",
        label="incoming",
        source=FileVersion.SOURCE_MANUAL,
        created_by=user,
    )
    file_obj.content = "line1\nours\nline3"
    file_obj.save()

    preview = three_way_diff(base_version.snapshot, file_obj.content, source_version.snapshot)
    conflict = preview["conflicts"][0]

    merge_job = MergeJob.objects.create(
        file=file_obj,
        base_version=source_version,
        status=MergeJob.STATUS_CONFLICT,
        conflict_hunks=preview["conflicts"],
    )

    with patch("tasks.persist_updates.compact_snapshot.apply_async"):
        apply_resolutions(
            str(file_obj.id),
            [{"hunk_id": conflict["hunk_id"], "choice": "theirs"}],
            str(merge_job.id),
            str(user.id),
        )

    file_obj.refresh_from_db()
    assert "theirs" in file_obj.content
    assert "ours" not in file_obj.content


@pytest.mark.django_db
def test_apply_resolutions_custom_uses_custom_text(user, file_obj):
    base_version = FileVersion.objects.create(
        file=file_obj,
        snapshot="line1\nline2\nline3",
        label="base",
        source=FileVersion.SOURCE_COMPACTION,
        created_by=user,
    )
    source_version = FileVersion.objects.create(
        file=file_obj,
        snapshot="line1\ntheirs\nline3",
        label="incoming",
        source=FileVersion.SOURCE_MANUAL,
        created_by=user,
    )
    file_obj.content = "line1\nours\nline3"
    file_obj.save()

    preview = three_way_diff(base_version.snapshot, file_obj.content, source_version.snapshot)
    conflict = preview["conflicts"][0]

    merge_job = MergeJob.objects.create(
        file=file_obj,
        base_version=source_version,
        status=MergeJob.STATUS_CONFLICT,
        conflict_hunks=preview["conflicts"],
    )

    with patch("tasks.persist_updates.compact_snapshot.apply_async"):
        apply_resolutions(
            str(file_obj.id),
            [
                {
                    "hunk_id": conflict["hunk_id"],
                    "choice": "custom",
                    "custom_text": "custom line",
                }
            ],
            str(merge_job.id),
            str(user.id),
        )

    file_obj.refresh_from_db()
    assert "custom line" in file_obj.content


def test_diff_result_cached_in_redis(fake_diff_redis):
    base = "one\ntwo"
    new = "one\ntwo\nthree"
    file_id = "file-123"
    v1 = "version-a"
    v2 = "version-b"

    first = compute_diff(base, new, algorithm="myers", file_id=file_id, v1=v1, v2=v2)
    cache_key = get_cache_key(file_id, v1, v2, "myers")
    cached = fake_diff_redis.get(cache_key)

    assert cached is not None
    assert json.loads(cached)["stats"] == first["stats"]

    second = compute_diff(base, new, algorithm="myers", file_id=file_id, v1=v1, v2=v2)
    assert second["stats"] == first["stats"]


def test_large_file_raises_diff_too_large_error():
    large = "x" * (512 * 1024 + 1)

    with pytest.raises(DiffTooLargeError):
        compute_diff(large, "small", algorithm="myers")
