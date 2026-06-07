"""Comment-specific DRF permissions."""

from __future__ import annotations

from rest_framework.permissions import BasePermission

from apps.workspaces.models import WorkspaceMember
from core.permissions import (
    EDITOR_ROLES,
    _get_workspace_id_from_object,
    _get_workspace_id_from_view,
    get_user_workspace_role,
)


class IsCommentAuthor(BasePermission):
    def has_object_permission(self, request, view, obj) -> bool:
        return obj.author_id is not None and obj.author_id == request.user.id


class CanResolveComment(BasePermission):
    def has_object_permission(self, request, view, obj) -> bool:
        workspace_id = _get_workspace_id_from_object(obj)
        if workspace_id is None:
            return False
        role = get_user_workspace_role(request.user, workspace_id, request)
        return role in EDITOR_ROLES


class CanCreateComment(BasePermission):
    def has_permission(self, request, view) -> bool:
        workspace_id = _get_workspace_id_from_view(view)
        if workspace_id is None:
            return False
        role = get_user_workspace_role(request.user, workspace_id, request)
        return role in EDITOR_ROLES


class IsCommentAuthorOrWorkspaceOwner(BasePermission):
    def has_object_permission(self, request, view, obj) -> bool:
        if obj.author_id is not None and obj.author_id == request.user.id:
            return True

        workspace_id = _get_workspace_id_from_object(obj)
        if workspace_id is None:
            return False
        role = get_user_workspace_role(request.user, workspace_id, request)
        return role == WorkspaceMember.ROLE_OWNER
