from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ViewSet

from apps.users.models import User
from apps.workspaces.models import Project, Workspace, WorkspaceMember
from apps.workspaces.serializers import (
    ProjectSerializer,
    WorkspaceMemberCreateSerializer,
    WorkspaceMemberSerializer,
    WorkspaceMemberUpdateSerializer,
    WorkspaceSerializer,
)
from core.permissions import (
    IsWorkspaceEditor,
    IsWorkspaceMember,
    IsWorkspaceOwner,
    get_user_workspace_role,
)


class WorkspaceViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = WorkspaceSerializer

    def get_queryset(self):
        return (
            Workspace.objects.filter(members__user=self.request.user)
            .select_related("owner")
            .distinct()
            .order_by("-created_at")
        )

    def perform_create(self, serializer):
        workspace = serializer.save(owner=self.request.user)
        WorkspaceMember.objects.create(
            workspace=workspace,
            user=self.request.user,
            role=WorkspaceMember.ROLE_OWNER,
        )

    def destroy(self, request, *args, **kwargs):
        workspace = self.get_object()
        role = get_user_workspace_role(request.user, workspace.id, request)
        if role != WorkspaceMember.ROLE_OWNER:
            raise PermissionDenied("Only workspace owners can delete a workspace.")
        return super().destroy(request, *args, **kwargs)


class WorkspaceMemberViewSet(ViewSet):
    permission_classes = [IsAuthenticated, IsWorkspaceOwner]

    def initial(self, request, *args, **kwargs):
        self.workspace_id = kwargs.get("workspace_pk")
        super().initial(request, *args, **kwargs)

    def _get_workspace(self):
        return get_object_or_404(Workspace, pk=self.kwargs["workspace_pk"])

    def _owner_count(self, workspace):
        return WorkspaceMember.objects.filter(
            workspace=workspace,
            role=WorkspaceMember.ROLE_OWNER,
        ).count()

    def list(self, request, workspace_pk=None):
        workspace = self._get_workspace()
        members = workspace.members.select_related("user").order_by("joined_at")
        serializer = WorkspaceMemberSerializer(members, many=True)
        return Response(serializer.data)

    def create(self, request, workspace_pk=None):
        workspace = self._get_workspace()
        serializer = WorkspaceMemberCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"].lower()
        role = serializer.validated_data["role"]

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist as exc:
            raise NotFound("User with this email was not found.") from exc

        if WorkspaceMember.objects.filter(workspace=workspace, user=user).exists():
            raise ValidationError("User is already a member of this workspace.")

        member = WorkspaceMember.objects.create(
            workspace=workspace,
            user=user,
            role=role,
        )
        return Response(
            WorkspaceMemberSerializer(member).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, workspace_pk=None, pk=None):
        workspace = self._get_workspace()
        member = get_object_or_404(
            WorkspaceMember.objects.select_related("user"),
            pk=pk,
            workspace=workspace,
        )

        serializer = WorkspaceMemberUpdateSerializer(
            member,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        new_role = serializer.validated_data.get("role", member.role)

        if (
            member.role == WorkspaceMember.ROLE_OWNER
            and new_role != WorkspaceMember.ROLE_OWNER
            and self._owner_count(workspace) <= 1
        ):
            raise ValidationError("Cannot demote the last workspace owner.")

        serializer.save()
        return Response(WorkspaceMemberSerializer(member).data)

    def destroy(self, request, workspace_pk=None, pk=None):
        workspace = self._get_workspace()
        member = get_object_or_404(WorkspaceMember, pk=pk, workspace=workspace)

        if member.role == WorkspaceMember.ROLE_OWNER and self._owner_count(workspace) <= 1:
            raise ValidationError("Cannot remove the last workspace owner.")

        member.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated, IsWorkspaceMember]
    serializer_class = ProjectSerializer

    def initial(self, request, *args, **kwargs):
        self.workspace_id = kwargs.get("workspace_pk")
        super().initial(request, *args, **kwargs)

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAuthenticated(), IsWorkspaceEditor()]
        return [IsAuthenticated(), IsWorkspaceMember()]

    def get_queryset(self):
        return Project.objects.filter(
            workspace_id=self.kwargs["workspace_pk"],
        ).order_by("-created_at")

    def perform_create(self, serializer):
        workspace = get_object_or_404(Workspace, pk=self.kwargs["workspace_pk"])
        serializer.save(workspace=workspace, created_by=self.request.user)
