"""
Phase 3: The "Eyes" - Spatial & Formatting Tool.
Detects visual anomalies: alignment of grade-like text and font/size consistency for key fields (GPA, Degree Conferred).
"""

import re
from pathlib import Path

import fitz  # PyMuPDF

# Pixel tolerance for grade column alignment (same x-coordinate)
ALIGNMENT_TOLERANCE_PX = 5.0
# Font size difference (pt) to flag as anomaly
FONT_SIZE_TOLERANCE_PT = 0.5

# Letter grades for alignment check (short strings that often appear in a grade column)
LETTER_GRADE_PATTERN = re.compile(
    r"^[A-F][+-]?$",
    re.IGNORECASE,
)
# Numeric grade: e.g. 3.5, 96, 87.5 (1–3 digits, optional decimal)
NUMERIC_GRADE_PATTERN = re.compile(
    r"^[0-9]{1,3}(\.[0-9]+)?$",
)


def _is_grade_like_text(text: str) -> bool:
    """Return True if text looks like a single grade (letter or numeric)."""
    if not text or len(text) > 6:
        return False
    t = text.strip()
    if LETTER_GRADE_PATTERN.match(t):
        return True
    if NUMERIC_GRADE_PATTERN.match(t):
        return True
    return False


def _extract_spans_from_pdf(pdf_path: str) -> list[dict]:
    """
    Use PyMuPDF to extract all text spans with bbox, text, font, size.
    If no spans (image-based PDF), falls back to OCR via ocr_utils.ocr_pdf_to_spans.
    Returns list of dicts: {"bbox": (x0,y0,x1,y1), "text": str, "font": str, "size": float}.
    """
    spans: list[dict] = []
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            d = page.get_text("dict", sort=False)
            blocks = d.get("blocks") or []
            for block in blocks:
                if block.get("type") != 0:  # 0 = text block
                    continue
                for line in block.get("lines") or []:
                    for span in line.get("spans") or []:
                        bbox = span.get("bbox")
                        text = (span.get("text") or "").strip()
                        font = (span.get("font") or "").strip()
                        size = span.get("size")
                        if bbox is not None and (text or font):
                            spans.append({
                                "bbox": tuple(bbox),
                                "text": text,
                                "font": font,
                                "size": float(size) if size is not None else 0.0,
                            })
        doc.close()
    except Exception:
        pass
    # OCR fallback for scanned/image PDFs
    if not spans:
        try:
            from .ocr_utils import is_ocr_available, ocr_pdf_to_spans
            if is_ocr_available():
                spans = ocr_pdf_to_spans(pdf_path)
        except Exception:
            pass
    return spans


def _check_grade_alignment(spans: list[dict]) -> tuple[bool, str, list[str]]:
    """
    Find spans that look like grades; check if their x-coordinates align (within tolerance).
    Returns (alignment_ok, detail_message, flags).
    """
    grade_spans = [s for s in spans if s.get("text") and _is_grade_like_text(s["text"])]
    if len(grade_spans) < 2:
        return True, "Fewer than two grade-like text elements found; alignment check skipped.", []

    x_positions = [s["bbox"][0] for s in grade_spans]  # x0 = left edge
    x_min, x_max = min(x_positions), max(x_positions)
    spread = x_max - x_min
    flags: list[str] = []

    if spread > ALIGNMENT_TOLERANCE_PX:
        flags.append(
            f"Grade column alignment: grades span {spread:.1f} px horizontally (tolerance {ALIGNMENT_TOLERANCE_PX} px)."
        )
        return False, (
            f"Grade-like text is misaligned: x-coordinates range {x_min:.1f}–{x_max:.1f} px "
            f"(spread {spread:.1f} px > {ALIGNMENT_TOLERANCE_PX} px). Possible manual editing."
        ), flags

    return True, (
        f"Grade-like text is aligned: x-coordinates within {ALIGNMENT_TOLERANCE_PX} px "
        f"(range {x_min:.1f}–{x_max:.1f} px)."
    ), flags


def _font_base_family(font_name: str) -> str:
    """
    Normalize font name to base family (strip Bold, Italic, Roman, etc.).
    So Times-Bold and Times-Roman are treated as same family; only flag truly different fonts.
    """
    if not font_name:
        return ""
    # Common suffixes that indicate weight/style, not a different font family
    for suffix in ("-Bold", "-Italic", "-Oblique", "-Roman", "-Regular", "-Medium", "-Light"):
        if font_name.endswith(suffix):
            return font_name[: -len(suffix)].strip()
    return font_name.strip()


def _check_gpa_degree_fonts(spans: list[dict]) -> tuple[bool, str, list[str]]:
    """
    Find spans containing 'GPA' or 'Degree Conferred'; compare font/size to rest of page.
    Bold/italic variants of the same family are not treated as suspicious (e.g. Times-Bold vs Times-Roman).
    Returns (font_ok, detail_message, flags).
    """
    key_phrases = ["gpa", "degree conferred", "degree awarded"]
    key_spans: list[dict] = []
    other_spans: list[dict] = []

    for s in spans:
        text = (s.get("text") or "").lower()
        if not text:
            continue
        if any(phrase in text for phrase in key_phrases):
            key_spans.append(s)
        else:
            other_spans.append(s)

    if not key_spans:
        return True, "No 'GPA' or 'Degree Conferred' text found; font check skipped.", []

    # Typical font/size on page (median of other spans)
    other_sizes = [s["size"] for s in other_spans if s.get("size", 0) > 0]
    other_fonts = [s["font"] for s in other_spans if s.get("font")]

    median_size = float(sorted(other_sizes)[len(other_sizes) // 2]) if len(other_sizes) > 0 else 0.0
    mode_font = (max(set(other_fonts), key=other_fonts.count) if other_fonts else "") or None
    mode_font_base = _font_base_family(mode_font) if mode_font else ""

    flags: list[str] = []
    details: list[str] = []
    size_anomaly_seen = False
    anomalous_fonts: set[str] = set()

    for s in key_spans:
        font, size = s.get("font", ""), s.get("size", 0)
        font_base = _font_base_family(font) if font else ""
        if median_size and abs(size - median_size) > FONT_SIZE_TOLERANCE_PT:
            size_anomaly_seen = True
        if mode_font_base and font_base and font_base != mode_font_base:
            anomalous_fonts.add(font)

    # One flag per anomaly type to avoid duplicate entries when many spans match "GPA" / "Degree"
    if size_anomaly_seen:
        flags.append(f"GPA/Degree text font size differs from page typical ({median_size:.1f} pt).")
        details.append(f"Size anomaly vs typical {median_size:.1f} pt.")
    if anomalous_fonts:
        fonts_str = ", ".join(sorted(anomalous_fonts))
        flags.append(f"GPA/Degree text uses different font(s): {fonts_str} vs typical '{mode_font}'.")
        details.append(f"Font anomaly: {fonts_str} vs '{mode_font}'.")

    if flags:
        return False, " ".join(details) if details else "; ".join(flags), flags
    return True, "GPA/Degree Conferred text uses same font and size as surrounding text.", []


def verify_transcript_spatial(pdf_path: str) -> dict:
    """
    Check spatial and formatting consistency of a transcript PDF.

    Uses PyMuPDF to extract text blocks with bounding-box coordinates and font metadata, then:
    - Alignment: verifies that grade-like text in a column shares the same x-coordinate (within tolerance).
    - Font/Metadata: flags if "GPA" or "Degree Conferred" text uses a different font or size than surrounding headers.

    Args:
        pdf_path (str): Path to the transcript PDF file.

    Returns:
        dict: success, error, alignment_ok, alignment_detail, font_ok, font_detail, flags, summary.
    """
    result: dict = {
        "success": False,
        "error": None,
        "flags": [],
        "alignment_ok": None,
        "alignment_detail": "",
        "font_ok": None,
        "font_detail": "",
        "summary": "",
    }

    path = Path(pdf_path)
    if not path.exists():
        result["error"] = f"File not found: {pdf_path}"
        result["summary"] = result["error"]
        return result

    try:
        spans = _extract_spans_from_pdf(pdf_path)
    except Exception as e:
        result["error"] = f"Failed to extract layout: {e}"
        result["summary"] = result["error"]
        return result

    if not spans:
        result["error"] = "No text spans extracted from PDF (possibly scanned/image)."
        result["summary"] = result["error"]
        return result

    result["success"] = True
    all_flags: list[str] = []

    # Alignment check
    align_ok, align_detail, align_flags = _check_grade_alignment(spans)
    result["alignment_ok"] = align_ok
    result["alignment_detail"] = align_detail
    all_flags.extend(align_flags)

    # Font/metadata check
    font_ok, font_detail, font_flags = _check_gpa_degree_fonts(spans)
    result["font_ok"] = font_ok
    result["font_detail"] = font_detail
    all_flags.extend(font_flags)

    result["flags"] = all_flags

    # One-line summary for the agent
    parts = [f"Alignment: {align_detail}", f"Font: {font_detail}"]
    if all_flags:
        parts.append("Alerts: " + "; ".join(all_flags))
    result["summary"] = " | ".join(parts)

    return result
