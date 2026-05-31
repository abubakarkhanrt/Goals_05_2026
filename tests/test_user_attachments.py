"""Tests for ADK web PDF attachment resolution."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from code.user_attachments import resolve_pdf_from_user_content


class TestUserAttachments(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self._session_id = "attach-test-session"

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    async def test_inline_pdf_upload_saved_to_session_cache(self) -> None:
        pdf_bytes = b"%PDF-1.4 test"
        user_content = MagicMock()
        user_content.parts = [
            {"text": "verify transcript"},
            {
                "inline_data": {
                    "mime_type": "application/pdf",
                    "display_name": "sample.pdf",
                    "data": pdf_bytes,
                }
            },
        ]

        with patch("code.user_attachments.session_cache_root") as mock_root:
            mock_root.return_value = Path(self._tmpdir.name)
            path = await resolve_pdf_from_user_content(
                user_content, session_id=self._session_id
            )

        self.assertIsNotNone(path)
        assert path is not None
        self.assertTrue(Path(path).is_file())
        self.assertEqual(Path(path).read_bytes(), pdf_bytes)

    async def test_gate_routes_verify_with_attached_pdf(self) -> None:
        from code.agent import _workflow_input_gate
        from code.middleware.slash_commands import ROUTE_VERIFY
        from code.runtime.session import reset_runtime_session

        reset_runtime_session()
        pdf_bytes = b"%PDF-1.4 attached"
        ctx = MagicMock()
        ctx.user_content = MagicMock()
        ctx.user_content.parts = [
            {"text": "verify transcript"},
            {
                "inline_data": {
                    "mime_type": "application/pdf",
                    "display_name": "sample.pdf",
                    "data": pdf_bytes,
                }
            },
        ]

        with patch("code.user_attachments.session_cache_root") as mock_root:
            mock_root.return_value = Path(self._tmpdir.name)
            with patch("code.transcript_math.verify_transcript_math") as mock_math:
                event = await _workflow_input_gate(ctx)

        self.assertEqual(event.actions.route, ROUTE_VERIFY)
        self.assertIsNotNone(event.output)
        mock_math.assert_not_called()


if __name__ == "__main__":
    unittest.main()
