"""Tests for SQLite verification store."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from code.db.store import VerificationStore, close_verification_store, get_verification_store, reset_verification_store


class TestVerificationStore(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self._db_path = Path(self._tmpdir.name) / "test.db"
        self._store: VerificationStore | None = None

    def tearDown(self) -> None:
        if self._store is not None:
            self._store.close()
        close_verification_store()
        self._tmpdir.cleanup()

    def test_save_and_get_latest(self) -> None:
        self._store = VerificationStore(self._db_path)
        store = self._store
        store.save_verification(
            "sess-1",
            "code/pdf/sample.pdf",
            {"success": True, "credit_sum_ok": True},
            {"success": True, "alignment_ok": True},
            {"risk_level": "Auto-Approve", "legitimacy_score": 0.9},
            pdf_image_paths=["/tmp/page-001.png"],
        )
        record = store.get_latest("sess-1")
        assert record is not None
        self.assertEqual(record.pdf_path, "code/pdf/sample.pdf")
        self.assertTrue(record.math_result["success"])
        self.assertEqual(record.assessment["risk_level"], "Auto-Approve")
        self.assertEqual(record.pdf_image_paths, ["/tmp/page-001.png"])

    def test_clear_session(self) -> None:
        self._store = VerificationStore(self._db_path)
        store = self._store
        store.save_verification(
            "sess-2",
            "x.pdf",
            {"success": True},
            {"success": True},
        )
        deleted = store.clear_session("sess-2")
        self.assertEqual(deleted, 1)
        self.assertIsNone(store.get_latest("sess-2"))

    def test_runtime_session_persists_when_db_enabled(self) -> None:
        from code.runtime.session import reset_runtime_session

        with patch.dict(
            os.environ,
            {"AGENT_DB_ENABLED": "true", "AGENT_DB_PATH": str(self._db_path)},
            clear=False,
        ):
            reset_verification_store(self._db_path)
            self._store = get_verification_store()
            runtime = reset_runtime_session()
            runtime.save_verification(
                "code/pdf/a.pdf",
                {"success": True},
                {"success": True},
                {"risk_level": "Manual Review"},
            )
            runtime.clear_verification_cache()
            self.assertFalse(runtime._memory_has_verification_cache())
            self.assertTrue(runtime.load_verification_from_db())
            self.assertEqual(runtime.last_assessment["risk_level"], "Manual Review")

    def test_messages_tool_runs_and_llm_calls(self) -> None:
        self._store = VerificationStore(self._db_path)
        store = self._store
        store.save_message("sess-3", "user", "Verify sample.pdf", local_only=False)
        store.save_message("sess-3", "assistant", "Risk: Auto-Approve", local_only=False)
        store.save_tool_run(
            "sess-3",
            "verify_transcript_math",
            pdf_path="sample.pdf",
            result={"success": True},
            duration_ms=12.5,
        )
        store.save_llm_call(
            "sess-3",
            "assess",
            model="ollama/gemma4:26b",
            backend="local",
            duration_s=42.1,
            image_count=2,
        )
        self.assertEqual(len(store.list_messages("sess-3")), 2)
        self.assertEqual(len(store.list_tool_runs("sess-3")), 1)
        self.assertEqual(len(store.list_llm_calls("sess-3")), 1)

    def test_list_verifications_shows_all_runs(self) -> None:
        self._store = VerificationStore(self._db_path)
        store = self._store
        store.save_verification(
            "sess-4",
            "a.pdf",
            {"success": True},
            {"success": True},
            {"risk_level": "Auto-Approve", "legitimacy_score": 0.95},
        )
        store.save_verification(
            "sess-4",
            "b.pdf",
            {"success": True},
            {"success": True},
            {"risk_level": "Manual Review", "legitimacy_score": 0.55},
        )
        runs = store.list_verifications("sess-4", limit=10)
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0].risk_level, "Manual Review")
        self.assertEqual(runs[1].risk_level, "Auto-Approve")

    def test_clear_session_removes_all_tables(self) -> None:
        self._store = VerificationStore(self._db_path)
        store = self._store
        store.save_verification("sess-5", "x.pdf", {"success": True}, {"success": True})
        store.save_message("sess-5", "user", "hi")
        store.save_tool_run("sess-5", "verify_transcript_math", result={"success": True})
        store.save_llm_call("sess-5", "qa", status="success")
        deleted = store.clear_session("sess-5")
        self.assertGreaterEqual(deleted, 4)
        self.assertIsNone(store.get_latest("sess-5"))
        self.assertEqual(store.list_messages("sess-5"), [])

    def test_runtime_persists_messages(self) -> None:
        from code.runtime.session import reset_runtime_session

        with patch.dict(
            os.environ,
            {"AGENT_DB_ENABLED": "true", "AGENT_DB_PATH": str(self._db_path)},
            clear=False,
        ):
            reset_verification_store(self._db_path)
            self._store = get_verification_store()
            runtime = reset_runtime_session()
            runtime.record_user("Verify the transcript")
            runtime.record_assistant("Done.")
            msgs = get_verification_store().list_messages(runtime.session_id)
            self.assertEqual(len(msgs), 2)
            self.assertEqual(msgs[0].role, "user")
            self.assertEqual(msgs[1].role, "assistant")


class TestDbMetrics(unittest.TestCase):
    def test_track_db_records_when_enabled(self) -> None:
        with patch.dict(os.environ, {"AGENT_METRICS_ENABLED": "true"}, clear=False):
            from code.observability.metrics import track_db

            with track_db("unit_test"):
                pass


if __name__ == "__main__":
    unittest.main()
