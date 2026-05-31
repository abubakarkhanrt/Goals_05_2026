"""Tests for local slash-command parsing, dispatch, and workflow interception."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import AsyncMock, patch

from code.commands.dispatcher import CommandDispatcher
from code.commands.parser import parse_slash_command
from code.commands.registry import build_default_registry
from code.middleware.slash_commands import SlashCommandInterceptor, try_intercept_slash_command
from code.runtime.context import CommandContext
from code.runtime.session import reset_runtime_session


class TestSlashParser(unittest.TestCase):
    def test_parse_simple(self):
        p = parse_slash_command("/help")
        assert p is not None
        self.assertEqual(p.name, "help")
        self.assertEqual(p.args, [])

    def test_parse_args_and_flags(self):
        p = parse_slash_command('/history 5 --verbose')
        assert p is not None
        self.assertEqual(p.name, "history")
        self.assertEqual(p.args, ["5"])
        self.assertEqual(p.flags.get("verbose"), True)

    def test_non_slash_returns_none(self):
        self.assertIsNone(parse_slash_command("verify pdf at foo.pdf"))

    def test_debug_subcommand_style(self):
        p = parse_slash_command("/debug on")
        assert p is not None
        self.assertEqual(p.name, "debug")
        self.assertEqual(p.args, ["on"])


class TestDispatcher(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        reset_runtime_session()

    async def test_help_command(self):
        dispatcher = CommandDispatcher(build_default_registry())
        ctx = CommandContext(adk_context=None, runtime=reset_runtime_session(), project_root=".")
        result = await dispatcher.execute_line("/help", ctx)
        self.assertTrue(result.handled)
        self.assertIn("/help", result.output)
        self.assertIn("/tools", result.output)

    async def test_unknown_suggests_typo(self):
        dispatcher = CommandDispatcher(build_default_registry())
        ctx = CommandContext(adk_context=None, runtime=reset_runtime_session(), project_root=".")
        result = await dispatcher.execute_line("/histroy", ctx)
        self.assertTrue(result.handled)
        self.assertIn("Did you mean", result.output)
        self.assertIn("/history", result.output)

    async def test_exit_raises_system_exit_in_cli(self):
        dispatcher = CommandDispatcher(build_default_registry())
        ctx = CommandContext(
            adk_context=object(),
            runtime=reset_runtime_session(),
            project_root=".",
        )
        with patch.object(sys, "argv", ["adk", "run", "code"]):
            with self.assertRaises(SystemExit):
                await dispatcher.execute_line("/exit", ctx)


class TestInterceptor(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        reset_runtime_session()

    async def test_intercept_slash_does_not_require_llm(self):
        with patch("code.transcript_math.verify_transcript_math") as mock_math:
            result = await try_intercept_slash_command("/tools")
            self.assertIsNotNone(result)
            assert result is not None
            self.assertTrue(result.handled)
            self.assertIn("verify_transcript_math", result.output)
            mock_math.assert_not_called()

    async def test_non_slash_not_handled(self):
        result = await try_intercept_slash_command("hello world")
        self.assertIsNone(result)


class TestWorkflowGate(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        reset_runtime_session()

    async def test_gate_routes_slash_locally(self):
        from unittest.mock import MagicMock

        from code.agent import _workflow_input_gate
        from code.middleware.slash_commands import ROUTE_LOCAL

        ctx = MagicMock()
        ctx.user_content = "/help"

        with patch("code.transcript_math.verify_transcript_math") as mock_math:
            event = await _workflow_input_gate(ctx)
            self.assertEqual(event.actions.route, ROUTE_LOCAL)
            mock_math.assert_not_called()
            self.assertIn("help", str(event.message or event.content or "").lower())


if __name__ == "__main__":
    unittest.main()
