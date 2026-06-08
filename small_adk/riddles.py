"""Offline riddle bank loaded from riddles.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

OFFLINE_RIDDLES: list[dict[str, Any]] = json.loads(
    (Path(__file__).resolve().parent / "riddles.json").read_text(encoding="utf-8")
)
