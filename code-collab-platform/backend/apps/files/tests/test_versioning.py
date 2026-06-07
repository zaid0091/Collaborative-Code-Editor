from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.files.models import File, FileBranch, FileVersion
from apps.files.versioning import create_snapshot, find_merge_base, get_version_ancestors
from apps.users.jwt_utils import generate_access_token
from apps.users.models import User
from apps.workspaces.models import Project, Workspace, WorkspaceMember


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="version@example.com",
        display_name="Version User",
        password="SecurePass123!",
    )


@pytest.fixture
def auth_client(api_client, user):
    token = generate_access_token(user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return api_client


@pytest.fixture
def workspace(user):
    ws = Workspace.objects.create(name="Version Workspace", owner=user)
    WorkspaceMember.objects.create(
        workspace=ws,
        user=user,
        role=WorkspaceMember.ROLE_OWNER,
    )
    return ws


@pytest.fixture
def project(workspace, user):
    return Project.objects.create(
        workspace=workspace,
        name="Version Project",
        created_by=user,
    )


@pytest.fixture
def file_obj(project):
    return File.objects.create(
        project=project,
        path="main.py",
        content='print("v1")',
    )


@pytest.fixture
def other_file(project):
    return File.objects.create(
        project=project,
        path="other.py",
        content='print("other")',
    )


@pytest.fixture
def mock_compact():
    with patch("tasks.persist_updates.compact_snapshot.apply_async") as mock_apply:
        yield mock_apply


@pytest.mark.django_db
def test_create_snapshot_creates_file_version(user, file_obj, mock_compact):
    version = create_snapshot(str(file_obj.id), str(user.id), label="First checkpoint")

    assert version.id is not None
    assert version.snapshot == file_obj.content
    assert version.label == "First checkpoint"
    assert version.source == FileVersion.SOURCE_MANUAL
    assert str(version.created_by_id) == str(user.id)
    mock_compact.assert_called_once_with(args=[str(file_obj.id)], queue="crdt.persist")


@pytest.mark.django_db
def test_create_snapshot_sets_parent_chain(user, file_obj, mock_compact):
    first = create_snapshot(str(file_obj.id), str(user.id), label="v1")
    file_obj.content = 'print("v2")'
    file_obj.save()
    second = create_snapshot(str(file_obj.id), str(user.id), label="v2")

    assert first.parent_version is None
    assert second.parent_version_id == first.id


@pytest.mark.django_db
def test_create_snapshot_updates_branch_head(user, file_obj, mock_compact):
    version = create_snapshot(str(file_obj.id), str(user.id))

    branch = FileBranch.objects.get(file=file_obj, is_default=True)
    assert branch.name == "main"
    assert branch.head_version_id == version.id


@pytest.mark.django_db
def test_list_versions_returns_only_file_versions(
    auth_client, user, file_obj, other_file, mock_compact
):
    create_snapshot(str(file_obj.id), str(user.id), label="target")
    create_snapshot(str(other_file.id), str(user.id), label="other")

    response = auth_client.get(reverse("files:file-versions", kwargs={"pk": file_obj.id}))

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 1
    assert response.data[0]["label"] == "target"
    assert str(response.data[0]["file"]) == str(file_obj.id)


@pytest.mark.django_db
def test_find_merge_base_finds_lca(user, file_obj, mock_compact):
    root = create_snapshot(str(file_obj.id), str(user.id), label="root")

    file_obj.content = "line 2"
    file_obj.save()
    main_tip = create_snapshot(str(file_obj.id), str(user.id), label="main-tip")

    feature_branch = FileBranch.objects.create(
        file=file_obj,
        name="feature",
        created_by=user,
        head_version=root,
        created_from_version=root,
    )
    feature_version = FileVersion.objects.create(
        file=file_obj,
        parent_version=root,
        branch_name=feature_branch.name,
        snapshot="feature change",
        created_by=user,
        label="feature-tip",
        source=FileVersion.SOURCE_MANUAL,
    )
    feature_branch.head_version = feature_version
    feature_branch.save(update_fields=["head_version"])

    merge_base = find_merge_base(str(main_tip.id), str(feature_version.id))

    assert merge_base is not None
    assert merge_base.id == root.id


@pytest.mark.django_db
def test_find_merge_base_returns_none_when_no_common_ancestor(
    user, file_obj, other_file, mock_compact
):
    version_a = create_snapshot(str(file_obj.id), str(user.id), label="a")
    version_b = create_snapshot(str(other_file.id), str(user.id), label="b")

    assert find_merge_base(str(version_a.id), str(version_b.id)) is None


@pytest.mark.django_db
def test_get_version_ancestors_walks_chain(user, file_obj, mock_compact):
    first = create_snapshot(str(file_obj.id), str(user.id), label="v1")
    file_obj.content = "v2"
    file_obj.save()
    second = create_snapshot(str(file_obj.id), str(user.id), label="v2")
    file_obj.content = "v3"
    file_obj.save()
    third = create_snapshot(str(file_obj.id), str(user.id), label="v3")

    ancestors = get_version_ancestors(str(third.id))

    assert [version.id for version in ancestors] == [third.id, second.id, first.id]
