from __future__ import annotations

from ..base import BaseCommand
from ..parser import ParsedCommand
from ..terminal import Terminal
from ...runtime.context import CommandContext
from ...runtime import introspection as intro


class ToolsCommand(BaseCommand):
    name = "tools"
    description = "List workflow verification tools"
    usage = "/tools"

    async def execute(self, context: CommandContext, parsed: ParsedCommand) -> str:
        term = Terminal()
        rows = [[r["name"], r["description"]] for r in intro.workflow_tools()]
        return "\n".join(
            [
                term.heading("Registered tools (workflow nodes)"),
                term.table(["Tool", "Description"], rows),
            ]
        )


class AgentsCommand(BaseCommand):
    name = "agents"
    description = "Show loaded root agent / workflow"
    usage = "/agents"

    async def execute(self, context: CommandContext, parsed: ParsedCommand) -> str:
        term = Terminal()
        rows = [
            [r["name"], r["type"], r["description"]]
            for r in intro.workflow_agents(context.root_agent)
        ]
        return "\n".join(
            [
                term.heading("Agents"),
                term.table(["Name", "Type", "Description"], rows),
            ]
        )


class PromptsCommand(BaseCommand):
    name = "prompts"
    description = "Show system / instruction context (truncated)"
    usage = "/prompts [--lines N]"

    async def execute(self, context: CommandContext, parsed: ParsedCommand) -> str:
        term = Terminal()
        max_lines = 40
        if "lines" in parsed.flags:
            try:
                max_lines = int(str(parsed.flags["lines"]))
            except ValueError:
                pass
        elif parsed.args and parsed.args[0].isdigit():
            max_lines = int(parsed.args[0])

        blocks: list[str] = [
            "Transcript Risk Assessor — deterministic ADK 2.x Workflow.",
            "No Gemini system prompt is active in the default pipeline.",
            "Decision logic lives in code/agent.py (_score_and_summarize).",
            "User-facing banner is printed at import time.",
        ]
        text = "\n".join(blocks)
        lines = text.splitlines()
        if len(lines) > max_lines:
            lines = lines[:max_lines] + [f"... ({len(lines) - max_lines} more lines truncated)"]
        return "\n".join([term.heading("Prompts / instructions"), *lines])


class ConfigCommand(BaseCommand):
    name = "config"
    description = "Show runtime configuration"
    usage = "/config"

    async def execute(self, context: CommandContext, parsed: ParsedCommand) -> str:
        term = Terminal()
        rows = [[k, v] for k, v in intro.runtime_config()]
        rows.append(["debug (local)", str(context.runtime.debug_enabled)])
        return "\n".join(
            [
                term.heading("Runtime configuration"),
                term.muted("Tip: /model for active local vs cloud model details"),
                term.table(["Key", "Value"], rows),
            ]
        )


class ModelCommand(BaseCommand):
    name = "model"
    description = "Show active model and local vs cloud deployment"
    aliases = ("models", "llm")
    usage = "/model"

    async def execute(self, context: CommandContext, parsed: ParsedCommand) -> str:
        term = Terminal()
        info = intro.model_info()
        active = info["active_assessment"]
        lines = [
            term.heading("Model"),
            term.table(
                ["Role", "Deployment", "Provider", "Model"],
                intro.model_info_rows(),
            ),
            "",
            term.success(
                f"Active assessment: {active['deployment']} / {active['provider']} / {active['model']}"
            ),
        ]
        cloud = info["cloud_configured"]
        if cloud.get("configured"):
            lines.append(
                term.muted(
                    f"Cloud credentials present ({cloud['provider']}) but not used unless you add Gemini steps."
                )
            )
        else:
            lines.append(term.muted("No cloud model configured for this pipeline."))
        return "\n".join(lines)
