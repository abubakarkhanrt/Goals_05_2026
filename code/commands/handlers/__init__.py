"""All slash command handler implementations."""

from __future__ import annotations

from .control import DebugCommand, ExitCommand, ReloadCommand
from .help import HelpCommand
from .introspection import (
    AgentsCommand,
    ConfigCommand,
    ModelCommand,
    PromptsCommand,
    ToolsCommand,
)
from .session_cmds import (
    AssessmentsCommand,
    AuditCommand,
    ClearCommand,
    HistoryCommand,
    MemoryCommand,
    SessionCommand,
)


def build_all_handlers():
    return [
        HelpCommand(),
        ToolsCommand(),
        AgentsCommand(),
        PromptsCommand(),
        MemoryCommand(),
        SessionCommand(),
        ConfigCommand(),
        ModelCommand(),
        HistoryCommand(),
        AssessmentsCommand(),
        AuditCommand(),
        ClearCommand(),
        ReloadCommand(),
        DebugCommand(),
        ExitCommand(),
    ]
