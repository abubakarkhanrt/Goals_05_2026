"""Execution context passed to slash command handlers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .session import RuntimeSession

if TYPE_CHECKING:
    from google.adk import Context


@dataclass
class CommandContext:
    adk_context: Context | None
    runtime: RuntimeSession
    project_root: Path
    root_agent: Any = None
    extras: dict[str, Any] = field(default_factory=dict)
