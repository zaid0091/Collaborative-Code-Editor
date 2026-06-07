"""Static code scanner — first jailbreak prevention layer."""

from __future__ import annotations

import re

BLOCKED_PATTERNS = [
    r"\bpip\s+install\b",
    r"\bnpm\s+install\b",
    r"\byarn\s+add\b",
    r"\bapt-get\b",
    r"\bapt\s+install\b",
    r"\bcurl\b",
    r"\bwget\b",
    r"\bfetch\s*\(",
    r"\bos\.system\s*\(",
    r"\bsubprocess\b",
    r"\bexec\s*\(",
    r"\beval\s*\(",
    r"\b__import__\s*\(",
    r"\bctypes\b",
    r"\bsocket\.",
    r'open\s*\(\s*["\']\/proc',
    r'open\s*\(\s*["\']\/etc',
    r'open\s*\(\s*["\']\/sys',
    r'shutil\.rmtree\s*\(\s*["\']\/\)',
    r"\bos\.fork\s*\(",
    r"\bpty\b",
    r"\bpty\.spawn\b",
]

COMPILED = [re.compile(pattern, re.IGNORECASE) for pattern in BLOCKED_PATTERNS]


def scan_code(code: str, language: str) -> tuple[bool, str | None]:
    """
    Returns (is_safe, reason_or_none).
    NEVER echo matched text in reason — security requirement.
    """
    del language
    if len(code.encode("utf-8")) > 64 * 1024:
        return False, "Code exceeds maximum size limit (64KB)"

    for pattern in COMPILED:
        if pattern.search(code):
            return False, "Code contains a disallowed operation"

    return True, None
