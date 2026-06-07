"""Comments models."""

from __future__ import annotations

import uuid

from django.db import models

from apps.files.models import File
from apps.users.models import User


class Comment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.ForeignKey(
        File,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="comments",
    )
    content = models.TextField(max_length=10000)
    line_start = models.PositiveIntegerField()
    line_end = models.PositiveIntegerField()
    col_start = models.PositiveIntegerField(null=True, blank=True)
    col_end = models.PositiveIntegerField(null=True, blank=True)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="replies",
    )
    is_resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resolved_comments",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    branch_name = models.CharField(max_length=255, default="main")

    class Meta:
        indexes = [
            models.Index(fields=["file", "line_start", "line_end"]),
            models.Index(fields=["file", "is_resolved"]),
            models.Index(fields=["author", "-created_at"]),
            models.Index(fields=["parent"]),
        ]
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Comment on {self.file_id} lines {self.line_start}-{self.line_end}"


class CommentReaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        related_name="reactions",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="comment_reactions",
    )
    emoji = models.CharField(max_length=10)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("comment", "user", "emoji")]
        indexes = [
            models.Index(fields=["comment"]),
        ]

    def __str__(self) -> str:
        return f"{self.emoji} on {self.comment_id}"
