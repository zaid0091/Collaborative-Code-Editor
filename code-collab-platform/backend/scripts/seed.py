#!/usr/bin/env python
"""Idempotent development seed data."""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

import django

django.setup()

from apps.files.models import File  # noqa: E402
from apps.users.models import User  # noqa: E402
from apps.workspaces.models import Project, Workspace, WorkspaceMember  # noqa: E402


def main() -> None:
    dev_user, created = User.objects.get_or_create(
        email="dev@test.com",
        defaults={
            "display_name": "Dev User",
        },
    )
    if created:
        dev_user.set_password("password123")
        dev_user.save(update_fields=["password"])
    elif not dev_user.check_password("password123"):
        dev_user.set_password("password123")
        dev_user.save(update_fields=["password"])

    workspace, _ = Workspace.objects.get_or_create(
        slug="test-workspace-seed",
        defaults={
            "name": "Test Workspace",
            "owner": dev_user,
        },
    )
    if workspace.name != "Test Workspace" or workspace.owner_id != dev_user.id:
        workspace.name = "Test Workspace"
        workspace.owner = dev_user
        workspace.save(update_fields=["name", "owner"])

    WorkspaceMember.objects.get_or_create(
        workspace=workspace,
        user=dev_user,
        defaults={"role": WorkspaceMember.ROLE_OWNER},
    )

    project, _ = Project.objects.get_or_create(
        workspace=workspace,
        name="Sample Project",
        defaults={"created_by": dev_user},
    )

    File.objects.get_or_create(
        project=project,
        path="main.py",
        defaults={
            "content": 'print("Hello World")',
            "language": "python",
        },
    )

    File.objects.get_or_create(
        project=project,
        path="utils.js",
        defaults={
            "content": 'console.log("hello")',
            "language": "javascript",
        },
    )

    print("Seed complete: dev@test.com / password123")


if __name__ == "__main__":
    main()
