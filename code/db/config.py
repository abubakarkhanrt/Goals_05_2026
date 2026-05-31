"""SQLite configuration for verification persistence."""

from __future__ import annotations

import os
from pathlib import Path


def db_enabled() -> bool:
    return os.environ.get("AGENT_DB_ENABLED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def db_path() -> Path:
    raw = os.environ.get("AGENT_DB_PATH", "code/.data/transcript_agent.db").strip()
    return Path(raw)
