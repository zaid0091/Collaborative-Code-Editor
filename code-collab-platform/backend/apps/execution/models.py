import uuid

from django.conf import settings
from django.db import models

from apps.files.models import File


class ExecutionJob(models.Model):
    PRIORITY_HIGH = "high"
    PRIORITY_LOW = "low"

    PRIORITY = [
        (PRIORITY_HIGH, "High"),
        (PRIORITY_LOW, "Low"),
    ]

    SOURCE_UI_RUN = "ui_run"
    SOURCE_UI_REPL = "ui_repl"
    SOURCE_BACKGROUND_TEST = "background_test"
    SOURCE_AI_ANALYSIS = "ai_analysis"
    SOURCE_WEBHOOK_CI = "webhook_ci"

    SOURCE = [
        (SOURCE_UI_RUN, "UI Run"),
        (SOURCE_UI_REPL, "UI REPL"),
        (SOURCE_BACKGROUND_TEST, "Background Test"),
        (SOURCE_AI_ANALYSIS, "AI Analysis"),
        (SOURCE_WEBHOOK_CI, "Webhook CI"),
    ]

    STATUS_QUEUED = "queued"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_TIMEOUT = "timeout"
    STATUS_REJECTED = "rejected"

    STATUS = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_RUNNING, "Running"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_TIMEOUT, "Timeout"),
        (STATUS_REJECTED, "Rejected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="execution_jobs",
    )
    file = models.ForeignKey(
        File,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="execution_jobs",
    )
    code = models.TextField()
    language = models.CharField(max_length=50)
    priority = models.CharField(max_length=10, choices=PRIORITY, default=PRIORITY_HIGH)
    source = models.CharField(max_length=20, choices=SOURCE, default=SOURCE_UI_RUN)
    status = models.CharField(max_length=20, choices=STATUS, default=STATUS_QUEUED)
    stdout = models.TextField(blank=True, default="")
    stderr = models.TextField(blank=True, default="")
    exit_code = models.IntegerField(null=True, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)
    queued_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "status", "priority", "queued_at"]),
        ]

    def __str__(self) -> str:
        return f"ExecutionJob {self.id} ({self.status})"
