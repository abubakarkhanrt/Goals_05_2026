"""Dispatch parsed slash commands to handlers."""

from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass

from ..runtime.context import CommandContext
from .parser import ParsedCommand, parse_slash_command
from .registry import CommandRegistry, build_default_registry

logger = logging.getLogger(__name__)


@dataclass
class DispatchResult:
    handled: bool
    output: str
    command_name: str | None = None
    exit_requested: bool = False


class CommandDispatcher:
    def __init__(self, registry: CommandRegistry | None = None) -> None:
        self.registry = registry or build_default_registry()

    async def execute_line(self, line: str, context: CommandContext) -> DispatchResult:
        parsed = parse_slash_command(line)
        if parsed is None:
            return DispatchResult(handled=False, output="")

        if not parsed.name:
            return DispatchResult(
                handled=True,
                output="Empty command. Try /help",
                command_name="",
            )

        logger.info("[LOCAL COMMAND] /%s", parsed.name)
        command = self.registry.get(parsed.name)
        if command is None:
            return DispatchResult(
                handled=True,
                output=self._unknown_message(parsed.name),
                command_name=parsed.name,
            )

        try:
            output = await command.execute(context, parsed)
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001 — surface to developer in CLI
            logger.exception("[LOCAL COMMAND] /%s failed", parsed.name)
            return DispatchResult(
                handled=True,
                output=f"Command /{parsed.name} failed: {exc}",
                command_name=parsed.name,
            )

        exit_requested = parsed.name == "exit"
        return DispatchResult(
            handled=True,
            output=output,
            command_name=parsed.name,
            exit_requested=exit_requested,
        )

    def _unknown_message(self, name: str) -> str:
        names = self.registry.names()
        suggestions = difflib.get_close_matches(name, names, n=3, cutoff=0.5)
        msg = f"Unknown command: /{name}"
        if suggestions:
            msg += "\nDid you mean: " + ", ".join(f"/{s}" for s in suggestions) + "?"
        else:
            msg += "\nType /help for available commands."
        return msg
