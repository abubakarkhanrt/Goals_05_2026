from __future__ import annotations

from datetime import datetime

from ..base import BaseCommand
from ..parser import ParsedCommand
from ..terminal import Terminal
from ...db.config import db_enabled
from ...runtime.context import CommandContext


def _truncate(text: str, limit: int = 2000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... ({len(text) - limit} chars truncated)"


def _parse_limit(parsed: ParsedCommand, default: int = 10) -> int:
    n = default
    if parsed.args and parsed.args[0].isdigit():
        n = int(parsed.args[0])
    elif "n" in parsed.flags:
        try:
            n = int(str(parsed.flags["n"]))
        except ValueError:
            pass
    return max(1, n)


def _format_db_time(iso_ts: str) -> str:
    try:
        return datetime.fromisoformat(iso_ts.replace("Z", "+00:00")).strftime("%H:%M:%S")
    except ValueError:
        return iso_ts[:19]


def _history_rows(context: CommandContext, n: int) -> list[tuple[str, str, str]]:
    if db_enabled():
        try:
            from ...db.store import get_verification_store

            rows = get_verification_store().list_messages(context.runtime.session_id, limit=500)
            if rows:
                selected = rows[-n:]
                return [
                    (
                        m.role + (" [local]" if m.local_only else ""),
                        _format_db_time(m.created_at),
                        m.text.replace("\n", " ")[:80],
                    )
                    for m in selected
                ]
        except Exception:
            pass

    msgs = context.runtime.messages[-n:]
    return [
        (
            m.role + (" [local]" if m.local_only else ""),
            m.timestamp.strftime("%H:%M:%S"),
            m.text.replace("\n", " ")[:80],
        )
        for m in msgs
    ]


class MemoryCommand(BaseCommand):
    name = "memory"
    description = "Summarize local + ADK session state"
    usage = "/memory"

    async def execute(self, context: CommandContext, parsed: ParsedCommand) -> str:
        term = Terminal()
        rt = context.runtime
        lines = [
            term.heading("Memory / state"),
            f"Local session id: {rt.session_id}",
            f"Local messages: {rt.message_count} ({rt.model_facing_message_count} non-slash)",
            f"Workflow runs (local counter): {rt.workflow_runs}",
        ]
        ctx = context.adk_context
        if ctx is not None:
            try:
                state = dict(ctx.state)
                if state:
                    keys = ", ".join(sorted(state.keys())[:30])
                    lines.append(f"ADK session state keys: {keys or '(empty)'}")
                else:
                    lines.append("ADK session state: (empty)")
            except Exception as exc:  # noqa: BLE001
                lines.append(f"ADK session state: (unavailable: {exc})")
        else:
            lines.append("ADK context: not attached")
        return "\n".join(lines)


class SessionCommand(BaseCommand):
    name = "session"
    description = "Show session metadata"
    usage = "/session"

    async def execute(self, context: CommandContext, parsed: ParsedCommand) -> str:
        term = Terminal()
        rt = context.runtime
        lines = [
            term.heading("Session"),
            f"Local session id: {rt.session_id}",
            f"Started: {rt.started_at.isoformat()}",
            f"Message count: {rt.message_count}",
        ]
        if rt.token_usage_hint:
            lines.append(f"Token usage (hint): {rt.token_usage_hint}")
        else:
            lines.append("Token usage: (n/a — deterministic workflow, no LLM)")

        ctx = context.adk_context
        if ctx is not None:
            try:
                lines.append(f"ADK session id: {ctx.session.id}")
                lines.append(f"Invocation id: {ctx.invocation_id}")
                lines.append(f"User id: {ctx.user_id}")
            except Exception:  # noqa: BLE001
                pass
        return "\n".join(lines)


class HistoryCommand(BaseCommand):
    name = "history"
    description = "Show recent conversation log (SQLite when enabled)"
    usage = "/history [N]"

    async def execute(self, context: CommandContext, parsed: ParsedCommand) -> str:
        term = Terminal()
        n = _parse_limit(parsed)
        rows = _history_rows(context, n)
        if not rows:
            return term.muted("No conversation history yet.")

        return "\n".join(
            [
                term.heading(f"History (last {len(rows)})"),
                term.table(["Role", "Time", "Preview"], rows),
            ]
        )


class AssessmentsCommand(BaseCommand):
    name = "assessments"
    description = "List verification/assessment runs for this session"
    usage = "/assessments [N]"

    async def execute(self, context: CommandContext, parsed: ParsedCommand) -> str:
        term = Terminal()
        n = _parse_limit(parsed)
        if not db_enabled():
            return term.warning("SQLite disabled — set AGENT_DB_ENABLED=true in code/.env")

        from ...db.store import get_verification_store

        runs = get_verification_store().list_verifications(
            context.runtime.session_id, limit=n
        )
        if not runs:
            return term.muted("No assessments stored for this session yet.")

        rows = []
        for run in runs:
            score = (
                f"{run.legitimacy_score:.2f}"
                if run.legitimacy_score is not None
                else "—"
            )
            pdf = (run.pdf_path or "—").replace("\n", " ")[:40]
            rows.append(
                [
                    _format_db_time(run.created_at),
                    run.risk_level or "—",
                    score,
                    pdf,
                ]
            )
        return "\n".join(
            [
                term.heading(f"Assessments (last {len(rows)})"),
                term.table(["Time", "Risk", "Score", "PDF"], rows),
            ]
        )


class AuditCommand(BaseCommand):
    name = "audit"
    description = "Show tool runs and LLM call audit log for this session"
    usage = "/audit [N]"

    async def execute(self, context: CommandContext, parsed: ParsedCommand) -> str:
        term = Terminal()
        n = _parse_limit(parsed)
        if not db_enabled():
            return term.warning("SQLite disabled — set AGENT_DB_ENABLED=true in code/.env")

        from ...db.store import get_verification_store

        store = get_verification_store()
        tools = store.list_tool_runs(context.runtime.session_id, limit=n)
        llms = store.list_llm_calls(context.runtime.session_id, limit=n)

        lines = [term.heading(f"Audit log (last {n} per section)")]

        if tools:
            tool_rows = [
                [
                    _format_db_time(t.created_at),
                    t.tool_name,
                    t.status,
                    f"{t.duration_ms:.0f}ms" if t.duration_ms is not None else "—",
                ]
                for t in tools
            ]
            lines.append(term.heading("Tool runs"))
            lines.append(term.table(["Time", "Tool", "Status", "Duration"], tool_rows))
        else:
            lines.append(term.muted("No tool runs logged yet."))

        if llms:
            llm_rows = [
                [
                    _format_db_time(c.created_at),
                    c.operation,
                    c.model or "—",
                    c.status + (" (fallback)" if c.fallback else ""),
                    f"{c.duration_s:.1f}s" if c.duration_s is not None else "—",
                ]
                for c in llms
            ]
            lines.append(term.heading("LLM calls"))
            lines.append(
                term.table(["Time", "Op", "Model", "Status", "Duration"], llm_rows)
            )
        else:
            lines.append(term.muted("No LLM calls logged yet."))

        return "\n".join(lines)


class ClearCommand(BaseCommand):
    name = "clear"
    description = "Clear local session history (does not erase ADK server session)"
    usage = "/clear"

    async def execute(self, context: CommandContext, parsed: ParsedCommand) -> str:
        context.runtime.clear()
        return Terminal().success("Local runtime history and session image cache cleared.")
