"""Tests for get_current_datetime and verify_transcript_dates."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from code.transcript_dates import (
    extract_dates_from_text,
    get_current_datetime,
    verify_transcript_dates,
)


class TestGetCurrentDatetime(unittest.TestCase):
    def test_returns_utc_reference(self):
        ref = datetime(2026, 5, 30, 15, 30, tzinfo=timezone.utc)
        result = get_current_datetime(reference=ref)
        self.assertTrue(result["success"])
        self.assertEqual(result["reference_date"], "2026-05-30")
        self.assertEqual(result["timezone"], "UTC")
        self.assertIn("2026-05-30T15:30:00", result["reference_datetime"])


class TestExtractDatesFromText(unittest.TestCase):
    def test_finds_multiple_formats(self):
        text = "Issued 05/15/2024. Graduation May 20, 2025. ID 2024-01-10."
        found = extract_dates_from_text(text)
        parsed = {item["parsed_date"] for item in found}
        self.assertIn("2024-05-15", parsed)
        self.assertIn("2025-05-20", parsed)
        self.assertIn("2024-01-10", parsed)

    def test_flags_future_relative_to_reference(self):
        ref = datetime(2026, 5, 30, tzinfo=timezone.utc)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            path = tmp.name
        try:
            with patch("code.transcript_dates._extract_pdf_text") as mock_text:
                mock_text.return_value = "Degree awarded 07/01/2027 and printed 03/10/2024."
                result = verify_transcript_dates(path, reference=ref)
        finally:
            Path(path).unlink(missing_ok=True)

        self.assertTrue(result["success"])
        self.assertFalse(result["dates_ok"])
        self.assertEqual(len(result["future_dates"]), 1)
        self.assertEqual(result["future_dates"][0]["parsed_date"], "2027-07-01")
        self.assertTrue(any("Future date" in f for f in result["flags"]))

    def test_all_dates_in_past_ok(self):
        ref = datetime(2026, 5, 30, tzinfo=timezone.utc)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            path = tmp.name
        try:
            with patch("code.transcript_dates._extract_pdf_text") as mock_text:
                mock_text.return_value = "Issued 05/15/2024. Printed 01/02/2025."
                result = verify_transcript_dates(path, reference=ref)
        finally:
            Path(path).unlink(missing_ok=True)

        self.assertTrue(result["dates_ok"])
        self.assertEqual(result["future_dates"], [])


if __name__ == "__main__":
    unittest.main()
