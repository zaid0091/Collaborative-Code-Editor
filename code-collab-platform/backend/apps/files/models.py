import hashlib
import uuid
from pathlib import PurePosixPath

from django.conf import settings
from django.db import models

from apps.workspaces.models import Project

LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".html": "html",
    ".css": "css",
    ".json": "json",
    ".md": "markdown",
}


class File(models.Model):
    TIER_STANDARD = "standard"
    TIER_OPTIMIZED = "optimized"
    TIER_VIRTUALIZED = "virtualized"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="files",
    )
    path = models.CharField(max_length=1000)
    content = models.TextField(blank=True, default="")
    language = models.CharField(max_length=50, blank=True, default="")
    yjs_state_version = models.PositiveIntegerField(default=0)
    compaction_checkpoint_version = models.PositiveIntegerField(default=0)
    yjs_snapshot = models.BinaryField(null=True, blank=True)
    last_compacted_at = models.DateTimeField(null=True, blank=True)
    line_count = models.PositiveIntegerField(default=0)
    byte_size = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("project", "path")]
        indexes = [models.Index(fields=["project", "path"])]

    def save(self, *args, **kwargs):
        extension = PurePosixPath(self.path).suffix.lower()
        detected_language = LANGUAGE_BY_EXTENSION.get(extension)
        if detected_language:
            self.language = detected_language

        content = self.content or ""
        self.byte_size = len(content.encode("utf-8"))
        self.line_count = content.count("\n") + 1 if content else 0
        super().save(*args, **kwargs)

    @property
    def tier(self) -> str:
        if self.byte_size < 524_288:
            return self.TIER_STANDARD
        if self.byte_size < 2_097_152:
            return self.TIER_OPTIMIZED
        return self.TIER_VIRTUALIZED

    def __str__(self) -> str:
        return self.path


class FileVersion(models.Model):
    SOURCE_MANUAL = "manual"
    SOURCE_AUTO = "auto"
    SOURCE_COMPACTION = "compaction"
    SOURCE_RESTORE = "restore"

    SOURCE_CHOICES = [
        (SOURCE_MANUAL, "Manual"),
        (SOURCE_AUTO, "Auto"),
        (SOURCE_COMPACTION, "Compaction"),
        (SOURCE_RESTORE, "Restore"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.ForeignKey(
        File,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    parent_version = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )
    merge_base_version = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="merge_children",
    )
    branch_name = models.CharField(max_length=200, default="main")
    snapshot = models.TextField()
    snapshot_hash = models.CharField(max_length=64, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="file_versions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    label = models.CharField(max_length=200, blank=True, default="")
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default=SOURCE_MANUAL,
    )

    class Meta:
        indexes = [models.Index(fields=["file", "-created_at"])]

    def save(self, *args, **kwargs):
        self.snapshot_hash = hashlib.sha256(self.snapshot.encode()).hexdigest()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.file.path} @ {self.created_at}"


class FileBranch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.ForeignKey(
        File,
        on_delete=models.CASCADE,
        related_name="branches",
    )
    name = models.CharField(max_length=200)
    head_version = models.ForeignKey(
        FileVersion,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="branch_heads",
    )
    created_from_version = models.ForeignKey(
        FileVersion,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="spawned_branches",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="file_branches",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        unique_together = [("file", "name")]

    def __str__(self) -> str:
        return f"{self.file.path}:{self.name}"


class OperationLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    file = models.ForeignKey(
        File,
        on_delete=models.CASCADE,
        related_name="operation_logs",
        db_index=False,
    )
    operation_json = models.JSONField()
    vector_clock = models.BigIntegerField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["file", "vector_clock"])]

    def __str__(self) -> str:
        return f"{self.file.path} op#{self.vector_clock}"


class MergeJob(models.Model):
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CONFLICT = "conflict"

    STATUS = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CONFLICT, "Conflict"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.ForeignKey(
        File,
        on_delete=models.CASCADE,
        related_name="merge_jobs",
    )
    source_branch = models.ForeignKey(
        FileBranch,
        null=True,
        on_delete=models.SET_NULL,
        related_name="source_merges",
    )
    target_branch = models.ForeignKey(
        FileBranch,
        null=True,
        on_delete=models.SET_NULL,
        related_name="target_merges",
    )
    base_version = models.ForeignKey(
        FileVersion,
        null=True,
        on_delete=models.SET_NULL,
        related_name="merge_jobs",
    )
    status = models.CharField(max_length=20, choices=STATUS, default=STATUS_PENDING)
    conflict_hunks = models.JSONField(default=list)
    resolutions = models.JSONField(default=dict)
    merged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="merge_jobs",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"MergeJob {self.id} ({self.status})"
