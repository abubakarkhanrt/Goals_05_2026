"""Tests for LLM routing and rule fallback (no live Ollama/cloud required)."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import AsyncMock, patch

from code.llm_config import ROUTE_LLM, ROUTE_OLLAMA, ROUTE_RULES, llm_backend, ollama_enabled
from code.scoring import build_rules_assessment


class TestOllamaConfig(unittest.TestCase):
    def test_ollama_disabled_by_conftest(self):
        self.assertFalse(ollama_enabled())

    def test_ollama_enabled_when_set(self):
        with patch.dict(os.environ, {"USE_OLLAMA": "true"}):
            self.assertTrue(ollama_enabled())

    def test_llm_backend_local_entry_point(self):
        with patch.dict(os.environ, {"TRANSCRIPT_LLM_BACKEND": "local", "USE_OLLAMA": "true"}, clear=False):
            self.assertEqual(llm_backend(), "local")

    def test_llm_backend_cloud_without_key_falls_back_to_rules(self):
        with patch.dict(
            os.environ,
            {"TRANSCRIPT_LLM_BACKEND": "cloud", "USE_OLLAMA": "false", "GOOGLE_API_KEY": ""},
            clear=False,
        ):
            self.assertEqual(llm_backend(), "rules")

    def test_llm_backend_cloud_with_key(self):
        with patch.dict(
            os.environ,
            {"TRANSCRIPT_LLM_BACKEND": "cloud", "GOOGLE_API_KEY": "test-key"},
            clear=False,
        ):
            self.assertEqual(llm_backend(), "cloud")


class TestAssessmentGate(unittest.TestCase):
    def test_gate_routes_to_rules_when_ollama_off(self):
        from code.agent import _assessment_backend_gate

        event = _assessment_backend_gate(
            "code/pdf/x.pdf",
            math_result={"success": True},
            spatial_result={"success": True},
        )
        self.assertEqual(event.actions.route, ROUTE_RULES)

    def test_gate_routes_to_llm_when_local_enabled(self):
        from code.agent import _assessment_backend_gate

        with patch.dict(
            os.environ,
            {"TRANSCRIPT_LLM_BACKEND": "local", "USE_OLLAMA": "true"},
            clear=False,
        ):
            event = _assessment_backend_gate(
                "code/pdf/x.pdf",
                math_result={"success": True},
                spatial_result={"success": True},
            )
        self.assertEqual(event.actions.route, ROUTE_LLM)
        self.assertEqual(event.actions.route, ROUTE_OLLAMA)
        payload = json.loads(event.output)
        self.assertIn("math_verification", payload)
        self.assertEqual(payload.get("llm_backend"), "local")


class TestLlmFallback(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_to_rules_when_local_llm_raises(self):
        from code.agent import _llm_assess_with_fallback

        with patch.dict(os.environ, {"TRANSCRIPT_LLM_BACKEND": "local", "USE_OLLAMA": "true"}, clear=False):
            with patch(
                "code.llm_client.assess_transcript",
                new_callable=AsyncMock,
                side_effect=ConnectionError("ollama not running"),
            ):
                event = await _llm_assess_with_fallback(
                    "code/pdf/x.pdf",
                    math_result={"success": False, "flags": ["x"]},
                    spatial_result={"success": True, "alignment_ok": True, "font_ok": True},
                )
        body = event.message if isinstance(event.message, str) else str(event.message or "")
        self.assertIn("Ollama unavailable", body)
        self.assertIn("risk_level", body)


class TestModelCommand(unittest.IsolatedAsyncioTestCase):
    async def test_model_command_shows_local_ollama(self):
        from code.commands.handlers.introspection import ModelCommand
        from code.commands.parser import ParsedCommand
        from code.runtime.context import CommandContext
        from code.runtime.session import reset_runtime_session

        with patch.dict(
            os.environ,
            {"TRANSCRIPT_LLM_BACKEND": "local", "USE_OLLAMA": "true", "OLLAMA_MODEL": "ollama/gemma4:26b"},
            clear=False,
        ):
            cmd = ModelCommand()
            out = await cmd.execute(
                CommandContext(adk_context=None, runtime=reset_runtime_session(), project_root="."),
                ParsedCommand(name="model"),
            )
        self.assertIn("local", out.lower())
        self.assertIn("ollama", out.lower())
        self.assertIn("gemma4", out.lower())

    async def test_model_command_unknown_typo(self):
        from code.commands.dispatcher import CommandDispatcher
        from code.runtime.context import CommandContext
        from code.runtime.session import reset_runtime_session

        dispatcher = CommandDispatcher()
        ctx = CommandContext(
            adk_context=None,
            runtime=reset_runtime_session(),
            project_root=".",
        )
        result = await dispatcher.execute_line("/modl", ctx)
        self.assertIn("/model", result.output)


class TestRulesScoring(unittest.TestCase):
    def test_high_risk_on_math_fail(self):
        a = build_rules_assessment(
            "t.pdf",
            math_result={"success": False},
            spatial_result={"success": True},
        )
        self.assertEqual(a.risk_level, "High Risk")
