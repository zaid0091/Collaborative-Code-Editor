import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.files.models import File
from apps.users.jwt_utils import generate_access_token
from apps.users.models import User
from apps.workspaces.models import Project, Workspace, WorkspaceMember


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="alice@example.com",
        display_name="Alice",
        password="SecurePass123!",
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        email="bob@example.com",
        display_name="Bob",
        password="SecurePass123!",
    )


@pytest.fixture
def auth_client(api_client, user):
    token = generate_access_token(user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return api_client


@pytest.fixture
def workspace(user):
    ws = Workspace.objects.create(name="Alice Workspace", owner=user)
    WorkspaceMember.objects.create(
        workspace=ws,
        user=user,
        role=WorkspaceMember.ROLE_OWNER,
    )
    return ws


@pytest.fixture
def other_workspace(other_user):
    ws = Workspace.objects.create(name="Bob Workspace", owner=other_user)
    WorkspaceMember.objects.create(
        workspace=ws,
        user=other_user,
        role=WorkspaceMember.ROLE_OWNER,
    )
    return ws


@pytest.fixture
def project(workspace, user):
    return Project.objects.create(
        workspace=workspace,
        name="Main Project",
        created_by=user,
    )


@pytest.fixture
def viewer_client(api_client, workspace, db):
    viewer = User.objects.create_user(
        email="viewer@example.com",
        display_name="Viewer",
        password="SecurePass123!",
    )
    WorkspaceMember.objects.create(
        workspace=workspace,
        user=viewer,
        role=WorkspaceMember.ROLE_VIEWER,
    )
    token = generate_access_token(viewer)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return api_client


def test_list_workspaces_returns_only_user_workspaces(
    auth_client, user, workspace, other_workspace
):
    response = auth_client.get(reverse("workspaces:workspace-list"))

    assert response.status_code == status.HTTP_200_OK
    workspace_ids = {item["id"] for item in response.data}
    assert str(workspace.id) in workspace_ids
    assert str(other_workspace.id) not in workspace_ids


def test_create_workspace_auto_creates_owner_member(auth_client, user):
    response = auth_client.post(
        reverse("workspaces:workspace-list"),
        {"name": "New Workspace"},
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    workspace = Workspace.objects.get(id=response.data["id"])
    member = WorkspaceMember.objects.get(workspace=workspace, user=user)
    assert member.role == WorkspaceMember.ROLE_OWNER


def test_non_member_cannot_list_files(auth_client, other_user, project):
    token = generate_access_token(other_user)
    auth_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    response = auth_client.get(
        reverse("files:file-list"),
        {"project_id": str(project.id)},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["error"] is True


def test_viewer_cannot_create_file(viewer_client, project):
    response = viewer_client.post(
        reverse("files:file-list"),
        {"project": str(project.id), "path": "blocked.py", "content": ""},
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["error"] is True


def test_file_path_rejects_path_traversal(auth_client, project):
    response = auth_client.post(
        reverse("files:file-list"),
        {"project": str(project.id), "path": "../secret.py", "content": ""},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["error"] is True


def test_file_meta_returns_correct_tier(auth_client, project):
    file_obj = File.objects.create(
        project=project,
        path="large.txt",
        content="x" * 600_000,
    )

    response = auth_client.get(reverse("files:file-meta", kwargs={"pk": file_obj.id}))

    assert response.status_code == status.HTTP_200_OK
    assert response.data["tier"] == File.TIER_OPTIMIZED
    assert response.data["byte_size"] == file_obj.byte_size
