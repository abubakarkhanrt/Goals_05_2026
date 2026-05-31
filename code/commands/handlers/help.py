from __future__ import annotations

from ..base import BaseCommand
from ..parser import ParsedCommand
from ..terminal import Terminal
from ...runtime.context import CommandContext


class HelpCommand(BaseCommand):
    name = "help"
    description = "List available local slash commands"
    aliases = ("?", "h")
    usage = "/help"

    async def execute(self, context: CommandContext, parsed: ParsedCommand) -> str:
        from ..registry import build_default_registry

        term = Terminal()
        registry = build_default_registry()
        rows = [
            [f"/{c.name}", c.description, c.usage or f"/{c.name}"]
            for c in registry.all_commands()
        ]
        lines = [
            term.heading("Local slash commands (not sent to the model)"),
            term.table(["Command", "Description", "Usage"], rows),
            "",
            term.muted("Type /help, /tools, /session, etc. Lines starting with / skip the workflow."),
        ]
        return "\n".join(lines)
