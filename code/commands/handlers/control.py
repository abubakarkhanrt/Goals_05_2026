from __future__ import annotations

import importlib
import logging
import os
import sys

from ..base import BaseCommand
from ..parser import ParsedCommand
from ..terminal import Terminal
from ...runtime.context import CommandContext
from ...runtime.session import reset_runtime_session


class DebugCommand(BaseCommand):
    name = "debug"
    description = "Toggle verbose logging: /debug on | /debug off"
    usage = "/debug on|off"

    async def execute(self, context: CommandContext, parsed: ParsedCommand) -> str:
        term = Terminal()
        mode = (parsed.args[0] if parsed.args else "").lower()
        if not mode and "on" in parsed.flags:
            mode = "on"
        if not mode and "off" in parsed.flags:
            mode = "off"

        if mode not in ("on", "off"):
            return term.warning("Usage: /debug on  or  /debug off")

        enable = mode == "on"
        context.runtime.debug_enabled = enable
        os.environ["TRANSCRIPT_AGENT_VERBOSE"] = "1" if enable else "0"

        level = logging.DEBUG if enable else logging.ERROR
        for name in ("google_adk", "google", "code.commands"):
            logging.getLogger(name).setLevel(level)

        return term.success(f"Debug logging {'enabled' if enable else 'disabled'}.")


class ReloadCommand(BaseCommand):
    name = "reload"
    description = "Reload local Python modules (agent, commands)"
    usage = "/reload"

    async def execute(self, context: CommandContext, parsed: ParsedCommand) -> str:
        term = Terminal()
        modules = [
            m
            for m in list(sys.modules)
            if m.startswith("code.") and m not in ("code",)
        ]
        reloaded = []
        for name in sorted(modules, key=len, reverse=True):
            try:
                importlib.reload(sys.modules[name])
                reloaded.append(name)
            except Exception as exc:  # noqa: BLE001
                return term.error(f"Reload failed at {name}: {exc}")

        context.runtime.reload_count += 1
        return term.success(
            f"Reloaded {len(reloaded)} modules. "
            "Restart `adk run code` if root_agent graph must be rebuilt."
        )


class ExitCommand(BaseCommand):
    name = "exit"
    description = "End the interactive session"
    aliases = ("quit", "q")
    usage = "/exit"

    async def execute(self, context: CommandContext, parsed: ParsedCommand) -> str:
        term = Terminal()
        context.runtime.clear()

        if _is_adk_web_server():
            return term.success(
                "Local session cleared. "
                "In ADK web the server keeps running — start a new chat session in the UI."
            )

        msg = term.success("Exiting local session.")
        print(msg, flush=True)
        raise SystemExit(0)


def _is_adk_web_server() -> bool:
    """True for `adk web`; false for `adk run` / `adk run code` CLI."""
    return any(arg == "web" for arg in sys.argv)

