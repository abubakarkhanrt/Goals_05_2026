"""
Unit tests for Phase 2: transcript_math (Calculator tool).
"""

import pytest

# Import from code package (run tests from project root: pytest tests/ or python -m pytest tests/)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from code.transcript_math import (
    GRADE_POINTS,
    verify_transcript_math,
    _parse_float,
    _parse_grade,
    _is_likely_course_code,
    _find_column_indices,
)


class TestParseHelpers:
    def test_parse_float_valid(self):
        assert _parse_float("3.5") == 3.5
        assert _parse_float("0") == 0.0
        assert _parse_float("  2.0  ") == 2.0
        assert _parse_float("1,5") == 1.5  # comma as decimal

    def test_parse_float_invalid(self):
        assert _parse_float("") is None
        assert _parse_float("abc") is None
        assert _parse_float(None) is None

    def test_parse_grade_letter(self):
        assert _parse_grade("A") == "A"
        assert _parse_grade("a-") == "A-"
        assert _parse_grade("B+") == "B+"
        assert _parse_grade("F") == "F"

    def test_parse_grade_invalid(self):
        assert _parse_grade("P") is None  # Pass
        assert _parse_grade("W") is None  # Withdraw
        assert _parse_grade("") is None
        assert _parse_grade("96") is None  # numeric not in GRADE_POINTS as key

    def test_is_likely_course_code_true(self):
        assert _is_likely_course_code("CS101") is True
        assert _is_likely_course_code("English I") is True
        assert _is_likely_course_code("MATH201") is True

    def test_is_likely_course_code_false(self):
        assert _is_likely_course_code("0") is False
        assert _is_likely_course_code("1.00") is False
        assert _is_likely_course_code("") is False


class TestColumnDetection:
    def test_find_column_indices_by_header(self):
        headers = ["Course", "Credits", "Grade"]
        col_map = _find_column_indices(headers, None)
        assert col_map is not None
        assert col_map["course"] == 0
        assert col_map["credit"] == 1
        assert col_map["grade"] == 2

    def test_find_column_indices_aliases(self):
        headers = ["Subject", "Cr", "Gr"]
        col_map = _find_column_indices(headers, None)
        assert col_map is not None
        assert col_map["course"] == 0
        assert col_map["credit"] == 1
        assert col_map["grade"] == 2

    def test_find_column_indices_missing_returns_none(self):
        assert _find_column_indices(["Foo", "Bar"], None) is None
        assert _find_column_indices(["Course", "Credits"], None) is None


class TestGpaGradePoints:
    def test_grade_points_scale(self):
        assert GRADE_POINTS["A"] == 4.0
        assert GRADE_POINTS["A-"] == 3.7
        assert GRADE_POINTS["B"] == 3.0
        assert GRADE_POINTS["F"] == 0.0


class TestVerifyTranscriptMath:
    def test_missing_file(self):
        result = verify_transcript_math("/nonexistent/path/to/file.pdf")
        assert result["success"] is False
        assert "not found" in (result.get("error") or "").lower()
        assert result["summary"]

    def test_result_structure(self):
        result = verify_transcript_math("/nonexistent/file.pdf")
        assert "success" in result
        assert "error" in result
        assert "flags" in result
        assert "credit_sum_ok" in result
        assert "gpa_ok" in result
        assert "logical_ok" in result
        assert "summary" in result
