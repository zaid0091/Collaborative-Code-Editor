import hashlib

import pytest
from django.db import IntegrityError

from apps.files.models import File, FileVersion
from apps.users.models import User
from apps.workspaces.models import Project, Workspace, WorkspaceMember
from core.permissions import get_user_workspace_role


@pytest.fixture
def owner(db):
    return User.objects.create_user(
        email="owner@example.com",
        display_name="Owner",
        password="SecurePass123!",
    )


@pytest.fixture
def workspace(owner):
    return Workspace.objects.create(name="Acme Corp", owner=owner)


@pytest.fixture
def project(workspace, owner):
    return Project.objects.create(
        workspace=workspace,
        name="Demo",
        created_by=owner,
    )


def test_workspace_slug_auto_generated(owner):
    workspace = Workspace.objects.create(name="My Cool Workspace", owner=owner)

    assert workspace.slug
    assert workspace.slug.startswith("my-cool-workspace-")


def test_workspace_member_unique_constraint(workspace, owner):
    WorkspaceMember.objects.create(
        workspace=workspace,
        user=owner,
        role=WorkspaceMember.ROLE_OWNER,
    )

    with pytest.raises(IntegrityError):
        WorkspaceMember.objects.create(
            workspace=workspace,
            user=owner,
            role=WorkspaceMember.ROLE_EDITOR,
        )


def test_file_tier_property_returns_correct_tier(project):
    small = File(project=project, path="small.py", content="x")
    small.byte_size = 100_000
    assert small.tier == File.TIER_STANDARD

    medium = File(project=project, path="medium.py", content="x")
    medium.byte_size = 600_000
    assert medium.tier == File.TIER_OPTIMIZED

    large = File(project=project, path="large.py", content="x")
    large.byte_size = 3_000_000
    assert large.tier == File.TIER_VIRTUALIZED


def test_file_save_calculates_byte_size_and_line_count(project):
    file_obj = File.objects.create(
        project=project,
        path="example.py",
        content="line1\nline2\nline3",
    )

    assert file_obj.language == "python"
    assert file_obj.byte_size == len(b"line1\nline2\nline3")
    assert file_obj.line_count == 3


def test_file_version_save_computes_snapshot_hash(project, owner):
    file_obj = File.objects.create(project=project, path="main.py", content="print(1)")
    snapshot = "print(1)"

    version = FileVersion.objects.create(
        file=file_obj,
        snapshot=snapshot,
        created_by=owner,
    )

    expected_hash = hashlib.sha256(snapshot.encode()).hexdigest()
    assert version.snapshot_hash == expected_hash


def test_get_user_workspace_role_returns_none_for_non_member(workspace, owner):
    stranger = User.objects.create_user(
        email="stranger@example.com",
        display_name="Stranger",
        password="SecurePass123!",
    )
    WorkspaceMember.objects.create(
        workspace=workspace,
        user=owner,
        role=WorkspaceMember.ROLE_OWNER,
    )

    assert get_user_workspace_role(stranger, workspace.id) is None
    assert get_user_workspace_role(owner, workspace.id) == WorkspaceMember.ROLE_OWNER
