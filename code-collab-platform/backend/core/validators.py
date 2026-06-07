"""Shared input validators."""

from __future__ import annotations

from rest_framework.exceptions import ValidationError


def validate_file_path(path: str) -> None:
    """
    Reject unsafe file paths.
    Raises ValidationError with a generic message — never echo the submitted path.
    """
    if not path or ".." in path or path.startswith("/") or "\x00" in path or len(path) > 500:
        raise ValidationError("Invalid file path")
