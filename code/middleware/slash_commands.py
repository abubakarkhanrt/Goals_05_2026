"""
Intercept slash commands before workflow / tool / model execution.

Slash input is handled locally only — it is not added to model-facing history.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from google.adk import Context

from ..commands.dispatcher import CommandDispatcher, DispatchResult
from ..commands.parser import is_slash_command
from ..runtime.context import CommandContext
from ..runtime.session import get_runtime_session

logger = logging.getLogger(__name__)

# Route value consumed by Workflow graph (see agent.py).
ROUTE_LOCAL = "local"
ROUTE_VERIFY = "verify"
ROUTE_QA = "qa"
ROUTE_QA_REFRESH = "qa_refresh"


class SlashCommandInterceptor:
    """Middleware: parse and run slash commands before agent workflow."""

    def __init__(
        self,
        dispatcher: CommandDispatcher | None = None,
        project_root: Path | None = None,
    ) -> None:
        self.dispatcher = dispatcher or CommandDispatcher()
        self.project_root = project_root or Path.cwd()

    def build_context(
        self,
        adk_context: Context | None,
        root_agent: Any = None,
    ) -> CommandContext:
        if root_agent is None:
            try:
                from .. import agent as agent_module

                root_agent = getattr(agent_module, "root_agent", None)
            except Exception:  # noqa: BLE001
                root_agent = None
        return CommandContext(
            adk_context=adk_context,
            runtime=get_runtime_session(),
            project_root=self.project_root,
            root_agent=root_agent,
        )

    async def try_intercept(
        self,
        user_text: str,
        adk_context: Context | None = None,
        root_agent: Any = None,
    ) -> DispatchResult | None:
        if not is_slash_command(user_text):
            return None

        runtime = get_runtime_session()
        runtime.record_user(user_text, local_only=True)

        cmd_ctx = self.build_context(adk_context, root_agent=root_agent)
        result = await self.dispatcher.execute_line(user_text, cmd_ctx)

        if result.handled and result.output:
            runtime.record_assistant(result.output, local_only=True)

        return result


_default_interceptor: SlashCommandInterceptor | None = None


def get_slash_interceptor() -> SlashCommandInterceptor:
    global _default_interceptor
    if _default_interceptor is None:
        _default_interceptor = SlashCommandInterceptor()
    return _default_interceptor


async def try_intercept_slash_command(
    user_text: str,
    adk_context: Context | None = None,
    root_agent: Any = None,
) -> DispatchResult | None:
    return await get_slash_interceptor().try_intercept(
        user_text, adk_context=adk_context, root_agent=root_agent
    )


def try_intercept_slash_command_sync(
    user_text: str,
    adk_context: Context | None = None,
    root_agent: Any = None,
) -> DispatchResult | None:
    """Sync wrapper for workflow nodes (ADK may call sync functions)."""
    coro = try_intercept_slash_command(user_text, adk_context, root_agent)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Nested loop: run in a fresh loop (rare for ADK sync nodes)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()
