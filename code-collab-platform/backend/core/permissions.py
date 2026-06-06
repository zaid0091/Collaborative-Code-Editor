"""Workspace-scoped permission helpers and DRF permission classes."""

from __future__ import annotations

from uuid import UUID

from rest_framework.permissions import BasePermission

from apps.files.models import File
from apps.workspaces.models import Project, Workspace, WorkspaceMember

EDITOR_ROLES = {WorkspaceMember.ROLE_OWNER, WorkspaceMember.ROLE_EDITOR}
OWNER_ROLES = {WorkspaceMember.ROLE_OWNER}


def get_user_workspace_role(user, workspace_id, request=None) -> str | None:
    """Return the member role string, or None if not a member. Caches per request."""
    if not user or not getattr(user, "is_authenticated", False):
        return None

    cache_key = str(workspace_id)
    if request is not None:
        cache = getattr(request, "_workspace_role_cache", None)
        if cache is None:
            cache = {}
            request._workspace_role_cache = cache
        if cache_key in cache:
            return cache[cache_key]

    try:
        role = WorkspaceMember.objects.get(
            user=user,
            workspace_id=workspace_id,
        ).role
    except WorkspaceMember.DoesNotExist:
        role = None

    if request is not None:
        request._workspace_role_cache[cache_key] = role

    return role


def get_file_workspace_id(file_id) -> UUID | None:
    """Traverse File → Project → Workspace and return the workspace id."""
    try:
        return (
            File.objects.select_related("project__workspace").get(id=file_id).project.workspace_id
        )
    except File.DoesNotExist:
        return None


def _get_workspace_id_from_view(view) -> UUID | None:
    workspace_id = getattr(view, "workspace_id", None)
    if workspace_id is not None:
        return workspace_id

    kwargs = getattr(view, "kwargs", None) or {}
    for key in ("workspace_id", "workspace_pk", "pk"):
        if key in kwargs:
            return kwargs[key]
    return None


def _get_workspace_id_from_object(obj) -> UUID | None:
    if isinstance(obj, Workspace):
        return obj.id
    if isinstance(obj, WorkspaceMember):
        return obj.workspace_id
    if isinstance(obj, Project):
        return obj.workspace_id
    if isinstance(obj, File):
        return obj.project.workspace_id

    workspace = getattr(obj, "workspace", None)
    if workspace is not None:
        return getattr(workspace, "id", workspace)

    workspace_id = getattr(obj, "workspace_id", None)
    if workspace_id is not None:
        return workspace_id

    project = getattr(obj, "project", None)
    if project is not None:
        return getattr(project, "workspace_id", None)

    file_obj = getattr(obj, "file", None)
    if file_obj is not None and hasattr(file_obj, "project"):
        return file_obj.project.workspace_id

    return None


class IsWorkspaceMember(BasePermission):
    """Requires the user to be any member of the workspace.

    The view must set ``workspace_id`` or pass it via URL kwargs.
    """

    def has_permission(self, request, view) -> bool:
        workspace_id = _get_workspace_id_from_view(view)
        if workspace_id is None:
            return False
        return get_user_workspace_role(request.user, workspace_id, request) is not None

    def has_object_permission(self, request, view, obj) -> bool:
        workspace_id = _get_workspace_id_from_object(obj)
        if workspace_id is None:
            return False
        return get_user_workspace_role(request.user, workspace_id, request) is not None


class IsWorkspaceEditor(IsWorkspaceMember):
    """Role must be owner or editor."""

    def has_permission(self, request, view) -> bool:
        workspace_id = _get_workspace_id_from_view(view)
        if workspace_id is None:
            return False
        role = get_user_workspace_role(request.user, workspace_id, request)
        return role in EDITOR_ROLES

    def has_object_permission(self, request, view, obj) -> bool:
        workspace_id = _get_workspace_id_from_object(obj)
        if workspace_id is None:
            return False
        role = get_user_workspace_role(request.user, workspace_id, request)
        return role in EDITOR_ROLES


class IsWorkspaceOwner(IsWorkspaceMember):
    """Role must be owner only."""

    def has_permission(self, request, view) -> bool:
        workspace_id = _get_workspace_id_from_view(view)
        if workspace_id is None:
            return False
        role = get_user_workspace_role(request.user, workspace_id, request)
        return role in OWNER_ROLES

    def has_object_permission(self, request, view, obj) -> bool:
        workspace_id = _get_workspace_id_from_object(obj)
        if workspace_id is None:
            return False
        role = get_user_workspace_role(request.user, workspace_id, request)
        return role in OWNER_ROLES
