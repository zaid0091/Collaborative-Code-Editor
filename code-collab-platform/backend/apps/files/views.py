from django.shortcuts import get_object_or_404
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.files.models import File
from apps.files.serializers import FileMetaSerializer, FileSerializer, FileTreeSerializer
from apps.workspaces.models import Project
from core.permissions import (
    IsWorkspaceEditor,
    IsWorkspaceMember,
    get_file_workspace_id,
)


def get_workspace_id_for_file(file_obj: File):
    return file_obj.project.workspace_id


class FileViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated, IsWorkspaceMember]
    serializer_class = FileSerializer

    def initial(self, request, *args, **kwargs):
        self.workspace_id = self._resolve_workspace_id(request, kwargs)
        super().initial(request, *args, **kwargs)

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [IsAuthenticated(), IsWorkspaceEditor()]
        return [IsAuthenticated(), IsWorkspaceMember()]

    def _resolve_workspace_id(self, request, kwargs):
        if kwargs.get("pk"):
            return get_file_workspace_id(kwargs["pk"])

        project_id = None
        if self.action == "list":
            project_id = request.query_params.get("project_id")
        elif self.action == "create":
            project_id = request.data.get("project")

        if not project_id:
            return None

        try:
            return Project.objects.values_list("workspace_id", flat=True).get(pk=project_id)
        except (Project.DoesNotExist, ValueError, TypeError):
            return None

    def get_queryset(self):
        queryset = File.objects.select_related("project__workspace")

        project_id = self.request.query_params.get("project_id")
        if self.action == "list":
            if not project_id:
                return queryset.none()
            queryset = queryset.filter(project_id=project_id)

        return queryset.order_by("path")

    def get_serializer_class(self):
        if self.action == "list":
            return FileTreeSerializer
        if self.action == "retrieve":
            return FileSerializer
        return FileSerializer

    def list(self, request, *args, **kwargs):
        if not request.query_params.get("project_id"):
            raise ValidationError({"project_id": "This query parameter is required."})
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        project_id = self.request.data.get("project")
        project = get_object_or_404(Project.objects.select_related("workspace"), pk=project_id)
        self.workspace_id = project.workspace_id

        path = serializer.validated_data.get("path")
        if File.objects.filter(project=project, path=path).exists():
            raise ValidationError({"path": "A file with this path already exists in the project."})

        serializer.save(project=project)

    def perform_update(self, serializer):
        path = serializer.validated_data.get("path")
        if path is not None:
            file_obj = self.get_object()
            if (
                File.objects.filter(project=file_obj.project, path=path)
                .exclude(pk=file_obj.pk)
                .exists()
            ):
                raise ValidationError(
                    {"path": "A file with this path already exists in the project."}
                )
        serializer.save()

    @action(detail=True, methods=["get"], url_path="meta")
    def meta(self, request, pk=None):
        file_obj = self.get_object()
        data = FileMetaSerializer(file_obj).data
        data["tier"] = file_obj.tier
        return Response(data)
