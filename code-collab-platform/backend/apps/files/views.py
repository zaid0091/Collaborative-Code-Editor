from django.shortcuts import get_object_or_404
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.files.models import File, FileBranch, FileVersion, MergeJob
from apps.files.serializers import (
    FileBranchSerializer,
    FileMetaSerializer,
    FileSerializer,
    FileTreeSerializer,
    FileVersionDetailSerializer,
    FileVersionSerializer,
)
from apps.workspaces.models import Project
from core.permissions import (
    IsWorkspaceEditor,
    IsWorkspaceMember,
    get_file_workspace_id,
)


# SECURITY AUDIT: permission confirmed — IsAuthenticated + IsWorkspaceMember/Editor;
# queryset scoped to request.user workspace memberships.
class FileViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated, IsWorkspaceMember]
    serializer_class = FileSerializer

    def initial(self, request, *args, **kwargs):
        self.workspace_id = self._resolve_workspace_id(request, kwargs)
        super().initial(request, *args, **kwargs)

    def get_permissions(self):
        editor_actions = (
            "create",
            "update",
            "partial_update",
            "destroy",
            "merge_preview",
            "merge_resolve",
            "restore_version",
        )
        if self.action in editor_actions:
            return [IsAuthenticated(), IsWorkspaceEditor()]
        if self.action == "versions" and self.request.method == "POST":
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
        queryset = (
            File.objects.select_related("project__workspace")
            .filter(project__workspace__members__user=self.request.user)
            .distinct()
        )

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

    @action(detail=True, methods=["get", "post"], url_path="versions")
    def versions(self, request, pk=None):
        """GET/POST /api/files/{id}/versions/"""
        file_obj = self.get_object()

        if request.method == "POST":
            label = request.data.get("label", "")
            from apps.files.versioning import create_snapshot

            version = create_snapshot(str(file_obj.id), str(request.user.id), label=label)
            return Response(FileVersionDetailSerializer(version).data, status=201)

        branch = request.query_params.get("branch", "main")
        version_qs = (
            FileVersion.objects.filter(file=file_obj, branch_name=branch)
            .select_related("created_by")
            .order_by("-created_at")[:50]
        )
        return Response(FileVersionSerializer(version_qs, many=True).data)

    @action(
        detail=True,
        methods=["get"],
        url_path=r"versions/(?P<version_id>[0-9a-f-]{36})",
    )
    def get_version(self, request, pk=None, version_id=None):
        """GET /api/files/{id}/versions/{version_id}/"""
        version = get_object_or_404(FileVersion, id=version_id, file_id=pk)
        return Response(FileVersionDetailSerializer(version).data)

    @action(detail=True, methods=["get"], url_path="branches")
    def list_branches(self, request, pk=None):
        """GET /api/files/{id}/branches/"""
        file_obj = self.get_object()
        branches = FileBranch.objects.filter(file=file_obj).order_by("-created_at")
        return Response(FileBranchSerializer(branches, many=True).data)

    @action(detail=True, methods=["get"], url_path="diff")
    def diff(self, request, pk=None):
        """GET /api/files/{id}/diff/?from=&to=&algorithm=myers|patience"""
        from_id = request.query_params.get("from")
        to_id = request.query_params.get("to")
        algorithm = request.query_params.get("algorithm", "myers")

        if algorithm not in ("myers", "patience"):
            return Response({"error": "algorithm must be myers or patience"}, status=400)

        file_obj = self.get_object()

        from_version = (
            get_object_or_404(FileVersion, id=from_id, file=file_obj) if from_id else None
        )
        to_version = get_object_or_404(FileVersion, id=to_id, file=file_obj) if to_id else None

        base_text = from_version.snapshot if from_version else ""
        new_text = to_version.snapshot if to_version else file_obj.content

        from apps.files.diff_engine import DiffTooLargeError, compute_diff

        try:
            result = compute_diff(
                base_text,
                new_text,
                algorithm=algorithm,
                file_id=str(file_obj.id),
                v1=from_id,
                v2=to_id,
            )
            return Response(result)
        except DiffTooLargeError:
            return Response({"error": "File too large for sync diff"}, status=413)

    @action(detail=True, methods=["post"], url_path="merge/preview")
    def merge_preview(self, request, pk=None):
        """POST /api/files/{id}/merge/preview/"""
        source_version_id = request.data.get("source_version_id")
        target_version_id = request.data.get("target_version_id")

        if not source_version_id:
            return Response({"error": "source_version_id required"}, status=400)

        from apps.files.merge_engine import preview_merge

        result = preview_merge(str(pk), source_version_id, target_version_id)
        return Response(result)

    @action(detail=True, methods=["post"], url_path="merge/resolve")
    def merge_resolve(self, request, pk=None):
        """POST /api/files/{id}/merge/resolve/"""
        resolutions = request.data.get("resolutions", [])
        merge_job_id = request.data.get("merge_job_id")

        if not merge_job_id:
            return Response({"error": "merge_job_id required"}, status=400)

        from apps.files.merge_engine import apply_resolutions

        version = apply_resolutions(str(pk), resolutions, merge_job_id, str(request.user.id))
        return Response(FileVersionDetailSerializer(version).data, status=201)

    @action(
        detail=True,
        methods=["post"],
        url_path=r"restore/(?P<version_id>[0-9a-f-]{36})",
    )
    def restore_version(self, request, pk=None, version_id=None):
        """POST /api/files/{id}/restore/{version_id}/"""
        strategy = request.data.get("strategy", "manual")
        file_obj = self.get_object()
        target_version = get_object_or_404(FileVersion, id=version_id, file=file_obj)

        if strategy == "ours":
            return Response({"message": "restore cancelled, kept current"})

        from apps.files.merge_engine import preview_merge

        preview = preview_merge(str(file_obj.id), version_id)

        if not preview["has_conflicts"] or strategy == "theirs":
            file_obj.content = target_version.snapshot
            file_obj.save(update_fields=["content", "byte_size", "line_count", "updated_at"])
            from apps.files.versioning import create_snapshot

            version = create_snapshot(
                str(file_obj.id),
                str(request.user.id),
                label=f"Restored from {target_version.label}",
                source=FileVersion.SOURCE_RESTORE,
            )
            return Response(FileVersionDetailSerializer(version).data, status=201)

        merge_job = MergeJob.objects.create(
            file=file_obj,
            base_version=target_version,
            status=MergeJob.STATUS_CONFLICT,
            conflict_hunks=preview["conflicts"],
        )

        return Response(
            {
                "has_conflicts": True,
                "merge_job_id": str(merge_job.id),
                "conflicts": preview["conflicts"],
                "auto_merged": preview["auto_merged"],
            },
            status=200,
        )
