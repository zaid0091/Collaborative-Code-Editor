"""Line-level diff engine: Myers (display) and Patience (merge/conflicts)."""

from __future__ import annotations

import json
import os
from typing import Literal

import redis
from diff_match_patch import diff_match_patch

Algorithm = Literal["myers", "patience"]

CACHE_TTL = 600
LARGE_FILE_BYTES = 512 * 1024


class DiffTooLargeError(Exception):
    """Raised when synchronous diff exceeds the size limit."""


def get_cache_key(file_id: str, v1: str | None, v2: str | None, algo: str) -> str:
    return f"diff:cache:{file_id}:{v1}:{v2}:{algo}"


def compute_diff(
    base_text: str,
    new_text: str,
    algorithm: Algorithm = "myers",
    file_id: str | None = None,
    v1: str | None = None,
    v2: str | None = None,
) -> dict:
    """
    Compute line-level diff between two text versions.

    Returns hunk list plus stats; caches by file/version pair when ids provided.
    """
    if len(base_text.encode()) > LARGE_FILE_BYTES or len(new_text.encode()) > LARGE_FILE_BYTES:
        raise DiffTooLargeError("File too large for synchronous diff. Use async endpoint.")

    cache_key = None
    if file_id and v1 and v2:
        redis_client = _get_redis()
        cache_key = get_cache_key(file_id, v1, v2, algorithm)
        cached = redis_client.get(cache_key)
        if cached:
            return json.loads(cached)

    if algorithm == "myers":
        result = _myers_diff(base_text, new_text)
    else:
        result = _patience_diff(base_text, new_text)

    result["algorithm"] = algorithm
    result["from_version"] = v1
    result["to_version"] = v2

    if cache_key:
        redis_client = _get_redis()
        redis_client.setex(cache_key, CACHE_TTL, json.dumps(result))

    return result


def _myers_diff(base_text: str, new_text: str) -> dict:
    """Myers diff via diff-match-patch, converted to line-level hunks."""
    dmp = diff_match_patch()

    a, b, line_array = dmp.diff_linesToChars(base_text, new_text)
    diffs = dmp.diff_main(a, b, False)
    dmp.diff_cleanupSemantic(diffs)
    dmp.diff_charsToLines(diffs, line_array)

    hunks: list[dict] = []
    stats = {"added": 0, "removed": 0, "unchanged": 0}

    current_hunk = None
    line_num = 1

    for op, text in diffs:
        lines = text.splitlines(keepends=True)
        if not lines and text:
            lines = [text]

        for line in lines:
            line_type = {-1: "-", 0: " ", 1: "+"}[op]

            if line_type != " ":
                if current_hunk is None:
                    current_hunk = {
                        "start_line": line_num,
                        "length": 0,
                        "lines": [],
                    }
                current_hunk["lines"].append({"type": line_type, "content": line.rstrip("\n\r")})
                current_hunk["length"] += 1
            else:
                if current_hunk:
                    hunks.append(current_hunk)
                    current_hunk = None
                line_num += 1

            if line_type == "+":
                stats["added"] += 1
            elif line_type == "-":
                stats["removed"] += 1
            else:
                stats["unchanged"] += 1

    if current_hunk:
        hunks.append(current_hunk)

    return {"hunks": hunks, "stats": stats}


def _patience_diff(base_text: str, new_text: str) -> dict:
    """Patience diff: unique-line anchors, better for moved blocks."""
    base_lines = base_text.splitlines()
    new_lines = new_text.splitlines()

    common = _patience_lcs(base_lines, new_lines)

    hunks: list[dict] = []
    stats = {"added": 0, "removed": 0, "unchanged": 0}

    base_idx = 0
    new_idx = 0
    current_hunk = None

    for base_match, new_match in common:
        while base_idx < base_match:
            if current_hunk is None:
                current_hunk = {"start_line": base_idx + 1, "length": 0, "lines": []}
            current_hunk["lines"].append({"type": "-", "content": base_lines[base_idx]})
            current_hunk["length"] += 1
            stats["removed"] += 1
            base_idx += 1

        while new_idx < new_match:
            if current_hunk is None:
                current_hunk = {"start_line": base_idx + 1, "length": 0, "lines": []}
            current_hunk["lines"].append({"type": "+", "content": new_lines[new_idx]})
            current_hunk["length"] += 1
            stats["added"] += 1
            new_idx += 1

        if current_hunk:
            hunks.append(current_hunk)
            current_hunk = None

        stats["unchanged"] += 1
        base_idx += 1
        new_idx += 1

    while base_idx < len(base_lines):
        if current_hunk is None:
            current_hunk = {"start_line": base_idx + 1, "length": 0, "lines": []}
        current_hunk["lines"].append({"type": "-", "content": base_lines[base_idx]})
        current_hunk["length"] += 1
        stats["removed"] += 1
        base_idx += 1

    while new_idx < len(new_lines):
        if current_hunk is None:
            current_hunk = {"start_line": base_idx + 1, "length": 0, "lines": []}
        current_hunk["lines"].append({"type": "+", "content": new_lines[new_idx]})
        current_hunk["length"] += 1
        stats["added"] += 1
        new_idx += 1

    if current_hunk:
        hunks.append(current_hunk)

    return {"hunks": hunks, "stats": stats}


def _patience_lcs(a_lines: list[str], b_lines: list[str]) -> list[tuple[int, int]]:
    """Patience LCS on uniquely matching lines."""
    a_count: dict[str, list[int]] = {}
    b_count: dict[str, list[int]] = {}

    for index, line in enumerate(a_lines):
        a_count.setdefault(line, []).append(index)
    for index, line in enumerate(b_lines):
        b_count.setdefault(line, []).append(index)

    unique_matches: list[tuple[int, int]] = []
    for line, a_indices in a_count.items():
        b_indices = b_count.get(line)
        if b_indices and len(a_indices) == 1 and len(b_indices) == 1:
            unique_matches.append((a_indices[0], b_indices[0]))

    unique_matches.sort()

    piles: list[list[tuple[int, int]]] = []
    back_pointers: dict[tuple[int, int], tuple[int, int]] = {}

    for pair in unique_matches:
        low = 0
        hi = len(piles)
        while low < hi:
            mid = (low + hi) // 2
            if piles[mid][-1][1] < pair[1]:
                low = mid + 1
            else:
                hi = mid

        if low == len(piles):
            piles.append([])
        piles[low].append(pair)
        if low > 0:
            back_pointers[pair] = piles[low - 1][-1]

    if not piles:
        return []

    result: list[tuple[int, int]] = []
    current = piles[-1][-1]
    while current:
        result.append(current)
        current = back_pointers.get(current)

    result.reverse()
    return result


def _get_redis():
    try:
        from django.conf import settings

        url = settings.REDIS_URL
    except Exception:
        url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    return redis.from_url(url, decode_responses=True)
