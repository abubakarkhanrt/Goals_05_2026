"""
Unit tests for Phase 3: transcript_spatial (Eyes / spatial tool).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from code.transcript_spatial import (
    verify_transcript_spatial,
    _is_grade_like_text,
    _font_base_family,
    _check_grade_alignment,
    _check_gpa_degree_fonts,
    ALIGNMENT_TOLERANCE_PX,
    FONT_SIZE_TOLERANCE_PT,
)


class TestGradeLikeText:
    def test_letter_grades(self):
        assert _is_grade_like_text("A") is True
        assert _is_grade_like_text("A-") is True
        assert _is_grade_like_text("B+") is True
        assert _is_grade_like_text("F") is True

    def test_numeric_grades(self):
        assert _is_grade_like_text("96") is True
        assert _is_grade_like_text("3.5") is True
        assert _is_grade_like_text("87") is True

    def test_not_grade(self):
        assert _is_grade_like_text("") is False
        assert _is_grade_like_text("English I") is False
        assert _is_grade_like_text("12345") is False  # too long
        assert _is_grade_like_text("AB") is False


class TestFontBaseFamily:
    def test_strips_bold_italic(self):
        assert _font_base_family("Times-Bold") == "Times"
        assert _font_base_family("Times-Roman") == "Times"
        assert _font_base_family("Helvetica-Oblique") == "Helvetica"

    def test_unchanged_when_no_suffix(self):
        assert _font_base_family("Arial") == "Arial"
        assert _font_base_family("") == ""


class TestCheckGradeAlignment:
    def test_aligned(self):
        # Same x within tolerance
        spans = [
            {"bbox": (100.0, 10, 110, 20), "text": "A"},
            {"bbox": (100.0, 30, 110, 40), "text": "B"},
            {"bbox": (102.0, 50, 112, 60), "text": "A-"},
        ]
        ok, detail, flags = _check_grade_alignment(spans)
        assert ok is True
        assert not flags

    def test_misaligned(self):
        spans = [
            {"bbox": (100.0, 10, 110, 20), "text": "A"},
            {"bbox": (200.0, 30, 210, 40), "text": "B"},  # different column
        ]
        ok, detail, flags = _check_grade_alignment(spans)
        assert ok is False
        assert any("alignment" in f.lower() for f in flags)

    def test_fewer_than_two_skipped(self):
        spans = [{"bbox": (100.0, 10, 110, 20), "text": "A"}]
        ok, detail, flags = _check_grade_alignment(spans)
        assert ok is True
        assert "skipped" in detail.lower()


class TestCheckGpaDegreeFonts:
    def test_no_key_phrase_skipped(self):
        spans = [{"text": "Some text", "font": "Times", "size": 11.0}]
        ok, detail, flags = _check_gpa_degree_fonts(spans)
        assert ok is True
        assert "skipped" in detail.lower()

    def test_bold_same_family_not_flagged(self):
        # GPA in Times-Bold, rest in Times-Roman -> same base family
        spans = [
            {"text": "GPA: 3.5", "font": "Times-Bold", "size": 11.0},
            {"text": "Other", "font": "Times-Roman", "size": 11.0},
            {"text": "More", "font": "Times-Roman", "size": 11.0},
        ]
        ok, detail, flags = _check_gpa_degree_fonts(spans)
        assert ok is True
        assert not any("font" in f.lower() for f in flags)


class TestVerifyTranscriptSpatial:
    def test_missing_file(self):
        result = verify_transcript_spatial("/nonexistent/path/file.pdf")
        assert result["success"] is False
        assert "not found" in (result.get("error") or "").lower()
        assert result["summary"]

    def test_result_structure(self):
        result = verify_transcript_spatial("/nonexistent/file.pdf")
        assert "success" in result
        assert "error" in result
        assert "alignment_ok" in result
        assert "font_ok" in result
        assert "flags" in result
        assert "summary" in result
