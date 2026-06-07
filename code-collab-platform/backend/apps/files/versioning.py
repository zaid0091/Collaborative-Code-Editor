"""File version snapshot creation and history helpers (Section 5.2.1)."""

from __future__ import annotations

from django.utils import timezone

from apps.files.models import File, FileBranch, FileVersion


def create_snapshot(
    file_id: str,
    user_id: str,
    label: str = "",
    source: str = FileVersion.SOURCE_MANUAL,
) -> FileVersion:
    """
    Create a FileVersion from current File.content.
    Also triggers compaction to align CRDT state with snapshot.
    """
    file = File.objects.get(id=file_id)

    branch, _ = FileBranch.objects.get_or_create(
        file=file,
        is_default=True,
        defaults={"name": "main", "created_by_id": user_id},
    )

    last_version = (
        FileVersion.objects.filter(file=file, branch_name=branch.name)
        .order_by("-created_at")
        .first()
    )

    version = FileVersion.objects.create(
        file=file,
        parent_version=last_version,
        branch_name=branch.name,
        snapshot=file.content,
        created_by_id=user_id,
        label=label or f"Checkpoint {timezone.now().strftime('%Y-%m-%d %H:%M')}",
        source=source,
    )

    branch.head_version = version
    branch.save(update_fields=["head_version"])

    from tasks.persist_updates import compact_snapshot

    compact_snapshot.apply_async(args=[str(file_id)], queue="crdt.persist")

    return version


def get_version_ancestors(version_id: str, max_depth: int = 50) -> list[FileVersion]:
    """Walk parent chain to build version history list."""
    ancestors: list[FileVersion] = []
    current_id: str | None = version_id
    depth = 0

    while current_id and depth < max_depth:
        try:
            version = FileVersion.objects.select_related("created_by").get(id=current_id)
        except FileVersion.DoesNotExist:
            break

        ancestors.append(version)
        current_id = str(version.parent_version_id) if version.parent_version_id else None
        depth += 1

    return ancestors


def find_merge_base(version_a_id: str, version_b_id: str) -> FileVersion | None:
    """Find lowest common ancestor of two versions by walking parent chains."""

    def ancestors_set(version_id: str) -> set[str]:
        visited: set[str] = set()
        current_id: str | None = version_id
        while current_id:
            visited.add(current_id)
            try:
                version = FileVersion.objects.get(id=current_id)
            except FileVersion.DoesNotExist:
                break
            current_id = str(version.parent_version_id) if version.parent_version_id else None
        return visited

    ancestors_a = ancestors_set(version_a_id)
    current_id: str | None = version_b_id

    while current_id:
        if current_id in ancestors_a:
            try:
                return FileVersion.objects.get(id=current_id)
            except FileVersion.DoesNotExist:
                return None
        try:
            version = FileVersion.objects.get(id=current_id)
        except FileVersion.DoesNotExist:
            break
        current_id = str(version.parent_version_id) if version.parent_version_id else None

    return None
