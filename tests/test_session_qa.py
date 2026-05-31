"""Tests for session Q&A intent routing and answers."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from code.intent import classify_turn, extract_pdf_path, is_qa_intent
from code.llm_config import ROUTE_QA
from code.middleware.slash_commands import ROUTE_LOCAL, ROUTE_VERIFY
from code.runtime.session import get_runtime_session, reset_runtime_session
from code.session_qa import answer_with_rules, build_qa_context


class TestIntent(unittest.TestCase):
    def test_extract_pdf_path(self):
        self.assertEqual(
            extract_pdf_path("Explain code/pdf/sample.pdf credit sum"),
            "code/pdf/sample.pdf",
        )

    def test_bare_pdf_is_verify_not_qa(self):
        self.assertFalse(is_qa_intent("code/pdf/sample.pdf"))

    def test_explain_is_qa(self):
        self.assertTrue(is_qa_intent("Explain the credit sum"))

    def test_how_compute_is_qa(self):
        self.assertTrue(is_qa_intent("How did you compute 24.0?"))

    def test_verify_overrides_generic_qa(self):
        self.assertFalse(is_qa_intent("Verify code/pdf/sample.pdf"))

    def test_classify_need_pdf_without_cache(self):
        self.assertEqual(
            classify_turn("How did you compute 24.0?", has_cached_verification=False),
            "need_pdf",
        )

    def test_classify_qa_with_cache(self):
        self.assertEqual(
            classify_turn("How did you compute 24.0?", has_cached_verification=True),
            "qa",
        )

    def test_classify_verify_bare_path(self):
        self.assertEqual(
            classify_turn("code/pdf/sample.pdf", has_cached_verification=False),
            "verify",
        )


class TestSessionQARules(unittest.TestCase):
    def test_rules_answer_includes_credit_detail(self):
        context = build_qa_context(
            "code/pdf/x.pdf",
            {"credit_sum_detail": "sum=24.0 from 4 courses", "flags": []},
            {"success": True, "flags": []},
        )
        answer = answer_with_rules("How did you compute 24.0?", context)
        self.assertIn("24.0", answer)
        self.assertIn("credit_sum_detail", answer)


class TestWorkflowQARouting(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        reset_runtime_session()

    async def test_gate_routes_qa_with_cache_no_pdf_in_message(self):
        from code.agent import _workflow_input_gate

        runtime = get_runtime_session()
        runtime.save_verification(
            "code/pdf/cached.pdf",
            {"credit_sum_detail": "24.0", "flags": []},
            {"success": True, "flags": []},
        )

        ctx = MagicMock()
        ctx.user_content = "How did you compute 24.0?"

        with patch("code.transcript_math.verify_transcript_math") as mock_math:
            event = await _workflow_input_gate(ctx)
            self.assertEqual(event.actions.route, ROUTE_QA)
            mock_math.assert_not_called()
            self.assertEqual(
                event.actions.state_delta.get("math_result"),
                runtime.last_math_result,
            )

    async def test_gate_routes_explain_with_path_as_qa_refresh(self):
        from code.agent import _workflow_input_gate

        ctx = MagicMock()
        ctx.user_content = "Explain the credit sum for code/pdf/new.pdf"

        with patch("code.transcript_math.verify_transcript_math") as mock_math:
            event = await _workflow_input_gate(ctx)
            self.assertEqual(event.actions.route, ROUTE_VERIFY)
            self.assertEqual(
                event.actions.state_delta.get("session_mode"), "qa_refresh"
            )
            self.assertEqual(event.output, "code/pdf/new.pdf")
            mock_math.assert_not_called()

    async def test_gate_routes_bare_pdf_as_verify(self):
        from code.agent import _workflow_input_gate

        ctx = MagicMock()
        ctx.user_content = "code/pdf/sample.pdf"

        event = await _workflow_input_gate(ctx)
        self.assertEqual(event.actions.route, ROUTE_VERIFY)

    async def test_gate_need_pdf_routes_local(self):
        from code.agent import _workflow_input_gate

        ctx = MagicMock()
        ctx.user_content = "Explain the credit sum"

        event = await _workflow_input_gate(ctx)
        self.assertEqual(event.actions.route, ROUTE_LOCAL)
        self.assertIn("No transcript in session", str(event.message))

    async def test_session_qa_answer_rules_mode(self):
        from code.agent import _session_qa_answer

        event = await _session_qa_answer(
            "code/pdf/x.pdf",
            {"credit_sum_detail": "total credits = 24.0", "flags": []},
            {"success": True, "flags": []},
            user_question="How did you compute 24.0?",
        )
        self.assertIn("24.0", str(event.message))
        self.assertTrue(event.output.get("qa"))

    async def test_post_tools_router_qa_refresh_skips_assessment(self):
        from code.agent import _post_tools_router

        math = {"credit_sum_detail": "24.0", "flags": []}
        spatial = {"success": True, "flags": []}
        event = _post_tools_router(
            "code/pdf/x.pdf",
            math,
            spatial,
            session_mode="qa_refresh",
            user_question="Explain the credit sum",
        )
        self.assertEqual(event.actions.route, ROUTE_QA)
        self.assertTrue(get_runtime_session().has_verification_cache())

    async def test_post_tools_router_verify_goes_to_rules(self):
        from code.agent import _post_tools_router

        event = _post_tools_router(
            "code/pdf/x.pdf",
            {"flags": []},
            {"success": True, "flags": []},
            session_mode="verify",
        )
        self.assertIn(event.actions.route, ("rules", "ollama"))


if __name__ == "__main__":
    unittest.main()
