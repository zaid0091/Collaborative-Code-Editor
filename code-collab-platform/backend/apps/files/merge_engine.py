"""3-way merge engine using Patience diff for conflict detection."""

from __future__ import annotations

import uuid

from apps.files.diff_engine import _patience_diff
from apps.files.models import File, FileVersion, MergeJob
from apps.files.versioning import create_snapshot, find_merge_base


def three_way_diff(base_text: str, ours_text: str, theirs_text: str) -> dict:
    """
    Compute 3-way merge using Patience diff.

    Returns auto_merged text, conflict hunks, and has_conflicts flag.
    """
    base_lines = base_text.splitlines()
    ours_diff = _patience_diff(base_text, ours_text)
    theirs_diff = _patience_diff(base_text, theirs_text)

    ours_changes = _build_change_map(ours_diff["hunks"])
    theirs_changes = _build_change_map(theirs_diff["hunks"])

    conflicts: list[dict] = []
    merged_lines: list[str] = []

    max_line = max(len(base_lines), len(ours_text.splitlines()), len(theirs_text.splitlines()))

    index = 0
    while index < max_line:
        ours_change = ours_changes.get(index)
        theirs_change = theirs_changes.get(index)

        if ours_change and theirs_change:
            conflict_id = str(uuid.uuid4())[:8]
            base_slice = "\n".join(base_lines[index : index + ours_change["length"]])
            ours_slice = ours_change["text"]
            theirs_slice = theirs_change["text"]

            conflicts.append(
                {
                    "hunk_id": conflict_id,
                    "base": base_slice,
                    "ours": ours_slice,
                    "theirs": theirs_slice,
                    "line_range": {
                        "start": index + 1,
                        "end": index + ours_change["length"],
                    },
                }
            )

            merged_lines.extend(
                [
                    "<<<<<<< current",
                    *ours_slice.splitlines(),
                    "=======",
                    *theirs_slice.splitlines(),
                    ">>>>>>> incoming",
                ]
            )
            index += ours_change["length"]
        elif ours_change:
            merged_lines.extend(ours_change["text"].splitlines())
            index += ours_change["length"]
        elif theirs_change:
            merged_lines.extend(theirs_change["text"].splitlines())
            index += theirs_change["length"]
        else:
            if index < len(base_lines):
                merged_lines.append(base_lines[index])
            index += 1

    return {
        "auto_merged": "\n".join(merged_lines),
        "conflicts": conflicts,
        "has_conflicts": len(conflicts) > 0,
    }


def _build_change_map(hunks: list[dict]) -> dict[int, dict]:
    """Map base line index → changed region metadata."""
    changes: dict[int, dict] = {}
    for hunk in hunks:
        removed = [line["content"] for line in hunk["lines"] if line["type"] == "-"]
        added = [line["content"] for line in hunk["lines"] if line["type"] == "+"]
        if removed or added:
            changes[hunk["start_line"] - 1] = {
                "length": len(removed) or 1,
                "text": "\n".join(added),
            }
    return changes


def preview_merge(
    file_id: str,
    source_version_id: str,
    target_version_id: str | None = None,
) -> dict:
    """3-way merge preview between source version and current file content."""
    file = File.objects.get(id=file_id)
    source_version = FileVersion.objects.get(id=source_version_id)

    if target_version_id:
        merge_base = find_merge_base(source_version_id, target_version_id)
    else:
        merge_base = (
            FileVersion.objects.filter(file=file, source=FileVersion.SOURCE_COMPACTION)
            .order_by("-created_at")
            .first()
        )

    base_text = merge_base.snapshot if merge_base else ""
    ours_text = file.content
    theirs_text = source_version.snapshot

    return three_way_diff(base_text, ours_text, theirs_text)


def _conflict_block(conflict: dict) -> str:
    return (
        f"<<<<<<< current\n{conflict['ours']}\n=======\n" f"{conflict['theirs']}\n>>>>>>> incoming"
    )


def apply_resolutions(
    file_id: str,
    resolutions: list[dict],
    merge_job_id: str,
    user_id: str,
) -> FileVersion:
    """Apply per-hunk conflict resolutions and create a merged FileVersion."""
    merge_job = MergeJob.objects.get(id=merge_job_id)
    file = File.objects.get(id=file_id)

    preview = preview_merge(file_id, str(merge_job.base_version_id))
    merged_text = preview["auto_merged"]
    resolution_map = {resolution["hunk_id"]: resolution for resolution in resolutions}
    conflicts = merge_job.conflict_hunks or preview["conflicts"]

    for conflict in conflicts:
        resolution = resolution_map.get(conflict["hunk_id"])
        if not resolution:
            continue

        choice = resolution["choice"]
        if choice == "ours":
            replacement = conflict["ours"]
        elif choice == "theirs":
            replacement = conflict["theirs"]
        else:
            replacement = resolution.get("custom_text", conflict["ours"])

        merged_text = merged_text.replace(_conflict_block(conflict), replacement, 1)

    file.content = merged_text
    file.save(update_fields=["content", "byte_size", "line_count", "updated_at"])

    version = create_snapshot(
        file_id,
        user_id,
        label="Merged",
        source=FileVersion.SOURCE_RESTORE,
    )

    merge_job.status = MergeJob.STATUS_COMPLETED
    merge_job.resolutions = {resolution["hunk_id"]: resolution for resolution in resolutions}
    merge_job.merged_by_id = user_id
    merge_job.save(update_fields=["status", "resolutions", "merged_by"])

    return version
