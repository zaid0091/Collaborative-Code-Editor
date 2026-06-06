#!/usr/bin/env python
"""Seed development data — delegates to backend/scripts/seed.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

from scripts.seed import main  # noqa: E402

if __name__ == "__main__":
    main()
