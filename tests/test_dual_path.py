"""Tests for dual-path pipeline: PDF tools vs PNG for LLM."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from code.runtime.session import reset_runtime_session


class TestDualPathPipeline(unittest.TestCase):
    def setUp(self):
        reset_runtime_session()

    def test_render_pdf_for_llm_only_creates_pngs(self):
        from code.agent import _render_pdf_for_llm

        with patch("code.agent.ensure_pdf_images", return_value=["/cache/page-001.png"]) as mock_render:
            with patch("code.transcript_math.verify_transcript_math") as mock_math:
                event = _render_pdf_for_llm("code/pdf/sample.pdf")

        mock_render.assert_called_once()
        mock_math.assert_not_called()
        self.assertEqual(
            event.actions.state_delta.get("pdf_image_paths"),
            ["/cache/page-001.png"],
        )

    def test_run_math_check_only_uses_pdf(self):
        from code.agent import _run_math_check

        with patch("code.agent.ensure_pdf_images") as mock_render:
            with patch(
                "code.agent.verify_transcript_math",
                return_value={"success": True, "flags": []},
            ) as mock_math:
                event = _run_math_check("code/pdf/sample.pdf")

        mock_render.assert_not_called()
        mock_math.assert_called_once_with("code/pdf/sample.pdf")
        self.assertTrue(event.actions.state_delta.get("math_result", {}).get("success"))
        self.assertNotIn("pdf_image_paths", event.actions.state_delta or {})

    def test_run_spatial_check_only_uses_pdf(self):
        from code.agent import _run_spatial_check

        with patch(
            "code.agent.verify_transcript_spatial",
            return_value={"success": True, "flags": []},
        ) as mock_spatial:
            event = _run_spatial_check("code/pdf/sample.pdf")

        mock_spatial.assert_called_once_with("code/pdf/sample.pdf")
        self.assertTrue(event.actions.state_delta.get("spatial_result", {}).get("success"))

    def test_run_dates_check_only_uses_pdf(self):
        from code.agent import _run_dates_check

        with patch(
            "code.agent.verify_transcript_dates",
            return_value={"success": True, "dates_ok": True, "flags": []},
        ) as mock_dates:
            event = _run_dates_check("code/pdf/sample.pdf")

        mock_dates.assert_called_once_with("code/pdf/sample.pdf")
        self.assertTrue(event.actions.state_delta.get("dates_result", {}).get("dates_ok"))


if __name__ == "__main__":
    unittest.main()
