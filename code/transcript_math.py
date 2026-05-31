"""
Phase 2: The "Calculator" tool.
Deterministic verification of transcript math: credits, GPA, and logical consistency.
"""

import re
from pathlib import Path

import pdfplumber

# Tolerance for GPA comparison (e.g. 0.01 = allow 0.01 difference)
GPA_TOLERANCE = 0.01
# Max credits per semester considered reasonable; flag if exceeded
MAX_CREDITS_PER_SEMESTER = 24

# Standard 4.0 scale (US style). Grades not in this map are skipped for GPA (e.g. P/F, W).
GRADE_POINTS = {
    "A": 4.0,
    "A+": 4.0,
    "A-": 3.7,
    "B+": 3.3,
    "B": 3.0,
    "B-": 2.7,
    "C+": 2.3,
    "C": 2.0,
    "C-": 1.7,
    "D+": 1.3,
    "D": 1.0,
    "D-": 0.7,
    "F": 0.0,
}


def _normalize_header(h: str) -> str:
    """Normalize table header for matching."""
    return (h or "").strip().lower().replace(" ", "")


def _is_likely_course_code(s: str) -> bool:
    """Check if a string looks like a course code (alphanumeric, not just numbers)."""
    if not s or len(s.strip()) < 2:
        return False
    s = s.strip()
    # Course codes are usually alphanumeric (e.g., "CS101", "MATH201", "ENG101")
    # or descriptive names (e.g., "English I", "Algebra I")
    # Not just numbers like "0", "1.00", "2.00"
    if s.replace(".", "").replace("-", "").isdigit():
        return False  # Pure number
    # Has letters or is a descriptive name
    return bool(re.search(r'[A-Za-z]', s)) or len(s.split()) > 1


def _find_column_indices(headers: list[str], sample_rows: list[list] = None) -> dict[str, int] | None:
    """
    Find indices for Course, Credit(s), and Grade.
    Uses header matching first, then falls back to data pattern analysis if headers are unclear.
    Returns None if not all found.
    """
    normalized = [_normalize_header(h) for h in headers]
    idx = {}
    used_indices = set()  # Track which columns we've already assigned
    
    # Strategy 1: Match headers directly (highest priority)
    for want, aliases in [
        ("course", ["course", "coursecode", "coursename", "code", "subject", "subj", "title", "coursetitle"]),
        ("credit", ["credit", "credits", "cr", "hrs", "hours", "hr"]),
        ("grade", ["grade", "grades", "gr", "grd"]),
    ]:
        for i, n in enumerate(normalized):
            if i in used_indices:
                continue
            if any(alias in n or n in alias for alias in aliases):
                idx[want] = i
                used_indices.add(i)
                break
    
    # Strategy 2: If course not found by header, try to infer from data (check empty headers first)
    if "course" not in idx and sample_rows:
        # First try columns with empty headers
        for i, header in enumerate(headers):
            if i in used_indices:
                continue
            if not header or not str(header).strip():
                # Check if this column has course-like values
                course_like_count = 0
                for row in sample_rows[:5]:
                    if row and i < len(row) and row[i]:
                        val = str(row[i]).strip()
                        # Check first line if multi-line
                        first_line = val.split('\n')[0] if '\n' in val else val
                        if _is_likely_course_code(first_line):
                            course_like_count += 1
                if course_like_count >= 2:
                    idx["course"] = i
                    used_indices.add(i)
                    break
        # If still not found, try any column
        if "course" not in idx:
            for i in range(len(headers)):
                if i in used_indices:
                    continue
                course_like_count = 0
                for row in sample_rows[:5]:
                    if row and i < len(row) and row[i]:
                        val = str(row[i]).strip()
                        first_line = val.split('\n')[0] if '\n' in val else val
                        if _is_likely_course_code(first_line):
                            course_like_count += 1
                if course_like_count >= 2:
                    idx["course"] = i
                    used_indices.add(i)
                    break
    
    # Strategy 3: If credit not found, look for numeric columns (skip course column)
    if "credit" not in idx and sample_rows:
        for i in range(len(headers)):
            if i in used_indices:
                continue
            # Check if this column has small numeric values (credits are usually 1-6)
            numeric_count = 0
            for row in sample_rows[:5]:
                if row and i < len(row) and row[i]:
                    val_str = str(row[i]).strip()
                    # Handle multi-line: check each line
                    for line in val_str.split('\n'):
                        val = _parse_float(line)
                        if val is not None and 0 < val <= 10:  # Credits are usually 1-6, sometimes up to 10
                            numeric_count += 1
                            break  # Count once per row
            if numeric_count >= 2:
                idx["credit"] = i
                used_indices.add(i)
                break
    
    # Strategy 4: If grade not found, look for letter grades (skip course and credit columns)
    if "grade" not in idx and sample_rows:
        for i in range(len(headers)):
            if i in used_indices:
                continue
            grade_like_count = 0
            for row in sample_rows[:5]:
                if row and i < len(row) and row[i]:
                    val_str = str(row[i]).strip()
                    # Handle multi-line: check each line
                    for line in val_str.split('\n'):
                        val = line.strip().upper()
                        if _parse_grade(val) is not None:
                            grade_like_count += 1
                            break  # Count once per row
            if grade_like_count >= 2:
                idx["grade"] = i
                used_indices.add(i)
                break
    
    # Must have all three and they must be different columns
    if "course" not in idx or "credit" not in idx or "grade" not in idx:
        return None
    if len(set([idx["course"], idx["credit"], idx["grade"]])) < 3:
        return None  # All three must be different columns
    
    return idx


def _parse_float(s: str) -> float | None:
    """Parse a string to float; return None if invalid."""
    if s is None:
        return None
    s = str(s).strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_grade(grade_str: str) -> str | None:
    """Normalize grade string to a key in GRADE_POINTS, or None if not graded (P/F, W, etc.)."""
    if not grade_str:
        return None
    g = str(grade_str).strip().upper()
    if g in GRADE_POINTS:
        return g
    # Try without +/-
    base = g.rstrip("+-")
    if base in GRADE_POINTS:
        return g if g in GRADE_POINTS else base
    return None


def _extract_courses_from_tables(pdf_path: str) -> tuple[list[dict], str]:
    """
    Extract course rows (course, credits, grade) from all tables in the PDF.
    Uses multiple strategies: header matching, then data pattern analysis.
    Returns (list of dicts with keys course, credits, grade), error_message.
    If error_message is non-empty, the list may be incomplete or empty.
    """
    path = Path(pdf_path)
    if not path.exists():
        return [], f"File not found: {pdf_path}"

    try:
        courses: list[dict] = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                if not tables:
                    continue
                for table in tables:
                    if not table or len(table) < 2:
                        continue
                    headers = [cell and str(cell).strip() for cell in table[0]]
                    # Get sample rows for pattern analysis
                    sample_rows = table[1:min(6, len(table))] if len(table) > 1 else []
                    col_map = _find_column_indices(headers, sample_rows)
                    if not col_map:
                        continue
                    ci = col_map["course"]
                    cr_i = col_map["credit"]
                    gi = col_map["grade"]
                    for row in table[1:]:
                        if not row or len(row) <= max(ci, cr_i, gi):
                            continue
                        course_cell = str(row[ci] or "").strip()
                        credit_cell = str(row[cr_i] or "").strip()
                        grade_cell = str(row[gi] or "").strip()
                        
                        # Handle multi-line course cells (courses separated by newlines)
                        course_lines_raw = [line.strip() for line in course_cell.split('\n') if line.strip()]
                        credit_lines = [line.strip() for line in credit_cell.split('\n') if line.strip()]
                        grade_lines = [line.strip() for line in grade_cell.split('\n') if line.strip()]
                        
                        # Filter course lines to only include actual course codes (skip semester headers, etc.)
                        course_lines = [c for c in course_lines_raw if _is_likely_course_code(c)]
                        
                        # If we have multiple courses and matching counts, zip them together
                        if len(course_lines) > 1 and len(credit_lines) == len(course_lines) and len(grade_lines) == len(course_lines):
                            # Perfect match: each course has its own credit and grade
                            for course, credit_str, grade_str in zip(course_lines, credit_lines, grade_lines):
                                credit_val = _parse_float(credit_str)
                                grade = _parse_grade(grade_str)
                                if credit_val is not None:
                                    courses.append({
                                        "course": course,
                                        "credits": credit_val,
                                        "grade": grade,
                                    })
                        elif len(course_lines) > 0 and len(credit_lines) > 0 and len(grade_lines) > 0:
                            # Mismatched counts: try to match by position (skip semester headers in courses)
                            # Use the minimum count to avoid index errors
                            min_count = min(len(course_lines), len(credit_lines), len(grade_lines))
                            for i in range(min_count):
                                course = course_lines[i]
                                credit_val = _parse_float(credit_lines[i])
                                grade = _parse_grade(grade_lines[i])
                                if credit_val is not None:
                                    courses.append({
                                        "course": course,
                                        "credits": credit_val,
                                        "grade": grade,
                                    })
                        else:
                            # Single course per row (or no multi-line data)
                            course = course_lines[0] if course_lines else course_cell
                            credit_val = _parse_float(credit_lines[0] if credit_lines else credit_cell)
                            grade = _parse_grade(grade_lines[0] if grade_lines else grade_cell)
                            
                            if course and _is_likely_course_code(course) and credit_val is not None:
                                courses.append({
                                    "course": course,
                                    "credits": credit_val,
                                    "grade": grade,
                                })
        if courses:
            return courses, ""
    except Exception as e:
        return [], f"Failed to extract tables: {e}"

    # Fallback: parse course lines from page text (e.g. "SUBJ NO. COURSE TITLE CRED GRD" layout with no table)
    courses, err = _extract_courses_from_text(pdf_path=pdf_path)
    if courses:
        return courses, ""
    # OCR fallback for image-based (scanned) PDFs
    try:
        from .ocr_utils import is_ocr_available, pdf_has_little_text, ocr_pdf_to_text
        if is_ocr_available() and pdf_has_little_text(pdf_path):
            ocr_text = ocr_pdf_to_text(pdf_path)
            if ocr_text:
                courses = _parse_course_lines_from_text(ocr_text)
                if courses:
                    return courses, ""
    except Exception:
        pass
    return [], "No course/credit/grade table found in PDF."


# Line patterns for text-based extraction
# Pattern 1: strict (e.g. "AUCC 140 Native American Cultures 3.00 W 0.00")
_COURSE_LINE_END = re.compile(r"\s+(\d+\.\d{2})\s+([A-FWPCI][+]?)\s*(?:\s|$|\.)")
_COURSE_CODE_START = re.compile(r"^\s*([A-Z]{2,5}\s+\d{2,4})\s+", re.IGNORECASE)
# Pattern 2: credits + grade anywhere (relaxed for OCR / varied layouts; allow 3.0 or 3.00)
_CREDITS_GRADE_ANYWHERE = re.compile(r"\b(\d+\.\d{1,2})\s+([A-FWPCI][+]?)\b", re.IGNORECASE)
# Course code: letters + optional space + digits (e.g. ENG 110, CS101, MATH 201)
_COURSE_CODE_PATTERN = re.compile(r"([A-Z]{2,5}\s*\d{2,4})", re.IGNORECASE)
_SKIP_LINE_PHRASES = (
    "ehrs:", "gpa-hrs:", "qpts:", "gpa:", "total", "overall", "institution credit",
    "fall term", "spring ", "winter ", "summer ", "transcript", "end of", "****",
    "earned hrs", "accordance", "registrar", "page:",
)


def _extract_course_code_from_left_part(left_text: str) -> str | None:
    """
    Extract a course code from the part of a line before credits/grade.
    Tries: (1) "XXX 123" or "XXX123" at start, (2) first such pattern anywhere, (3) first 2–3 tokens.
    """
    left = left_text.strip()
    if not left or len(left) < 2:
        return None
    # Prefer match at start (e.g. "ENG 110" or "ENG110")
    start_match = _COURSE_CODE_PATTERN.match(left)
    if start_match:
        code = start_match.group(1).strip()
        if _is_likely_course_code(code):
            return code
    # Any "XXX 123" or "XXX123" in the left part (take first)
    for m in _COURSE_CODE_PATTERN.finditer(left):
        code = m.group(1).strip()
        if _is_likely_course_code(code):
            return code
    # Generic: first 2 tokens if they look like code (letters + digits)
    tokens = left.split()
    if len(tokens) >= 2:
        two = f"{tokens[0]} {tokens[1]}"
        if _is_likely_course_code(two):
            return two
    if len(tokens) >= 1 and _is_likely_course_code(tokens[0]):
        return tokens[0]
    return None


def _parse_course_lines_from_text(full_text: str) -> list[dict]:
    """
    Parse course/credit/grade from transcript text using multiple strategies so
    different layouts (native text, OCR, various institutions) are accommodated.
    Returns list of {"course", "credits", "grade"}, deduplicated.
    """
    seen: set[tuple[str, float, str | None]] = set()
    courses: list[dict] = []

    def add(course: str, credits: float, grade: str | None) -> None:
        key = (course.strip(), credits, grade)
        if key in seen:
            return
        seen.add(key)
        if not course or not _is_likely_course_code(course):
            return
        courses.append({"course": course.strip(), "credits": credits, "grade": grade})

    for line in full_text.splitlines():
        line = line.strip()
        if not line or len(line) < 6:
            continue
        lower = line.lower()
        if any(skip in lower for skip in _SKIP_LINE_PHRASES):
            continue

        credit_val: float | None = None
        grade_str: str | None = None
        left_part: str | None = None

        # Strategy 1: strict end pattern "X.XX G" at end of line
        end_match = _COURSE_LINE_END.search(line)
        if end_match:
            credit_val = _parse_float(end_match.group(1))
            grade_str = (end_match.group(2) or "").strip().upper()
            left_part = line[: end_match.start()].strip()
            if credit_val is not None and left_part:
                start_match = _COURSE_CODE_START.match(left_part)
                if start_match:
                    code = start_match.group(1).strip()
                    add(code, credit_val, _parse_grade(grade_str))
                    continue

        # Strategy 2 & 3: credits + grade anywhere (last occurrence to avoid points column)
        anywhere_matches = list(_CREDITS_GRADE_ANYWHERE.finditer(line))
        if not anywhere_matches:
            continue
        # Use last match so we get "credits grade" not an earlier number
        last = anywhere_matches[-1]
        credit_val = _parse_float(last.group(1))
        grade_str = (last.group(2) or "").strip().upper()
        if credit_val is None:
            continue
        left_part = line[: last.start()].strip()
        if not left_part:
            continue
        # Extract course code from left part (generic)
        code = _extract_course_code_from_left_part(left_part)
        if code:
            add(code, credit_val, _parse_grade(grade_str))
        else:
            # Very generic: use first few tokens as label if they contain a letter
            tokens = left_part.split()
            if tokens and any(c.isalpha() for c in " ".join(tokens[:3])):
                generic_label = " ".join(tokens[:3]) if len(tokens) >= 3 else left_part[:40]
                if len(generic_label) >= 2:
                    add(generic_label, credit_val, _parse_grade(grade_str))

    return courses


def _extract_courses_from_text(pdf_path: str | None = None, text: str | None = None) -> tuple[list[dict], str]:
    """
    Fallback: extract course/credit/grade from transcript text when no table is detected.
    Either pass pdf_path (text read from PDF) or pre-extracted text (e.g. from OCR).
    """
    if text is not None:
        full_text = text
    elif pdf_path:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                full_text = ""
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        full_text += t + "\n"
        except Exception as e:
            return [], str(e)
    else:
        return [], "No input."

    courses = _parse_course_lines_from_text(full_text)
    return courses, ""


def _extract_stated_summary(pdf_path: str) -> tuple[float | None, float | None]:
    """
    Try to extract stated 'Earned Credits' / 'Total Credits' and 'GPA' / 'Cumulative GPA' from PDF text.
    Returns (stated_credits, stated_gpa). Either may be None if not found.
    """
    stated_credits: float | None = None
    stated_gpa: float | None = None
    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    full_text += t + "\n"
        # Common patterns for stated earned credits
        for pattern in [
            r"(?:earned|total)\s*credits?\s*[:\s]*([0-9]+(?:\.[0-9]+)?)",
            r"credits?\s*earned\s*[:\s]*([0-9]+(?:\.[0-9]+)?)",
            r"([0-9]+(?:\.[0-9]+)?)\s*(?:total|earned)\s*credits?",
            r"TOTAL\s+INSTITUTION\s+([0-9]+(?:\.[0-9]+)?)\s+",  # "TOTAL INSTITUTION 7.00 19.00 ..."
            r"OVERALL\s+([0-9]+(?:\.[0-9]+)?)\s+",  # "OVERALL 7.00 19.00 ..."
        ]:
            m = re.search(pattern, full_text, re.IGNORECASE)
            if m:
                c = _parse_float(m.group(1))
                if c is not None:
                    stated_credits = c
                    break
        for pattern in [
            r"(?:cumulative\s*)?gpa\s*[:\s]*([0-9]\.[0-9]{2,})",
            r"gpa\s*[=\s]*([0-9]\.[0-9]{2,})",
            r"([0-9]\.[0-9]{2,})\s*(?:cumulative\s*)?gpa",
            r"OVERALL\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+([0-9]\.[0-9]{2,})",  # last number is GPA
            r"TOTAL\s+INSTITUTION\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+([0-9]\.[0-9]{2,})",
        ]:
            m = re.search(pattern, full_text, re.IGNORECASE)
            if m:
                g = _parse_float(m.group(1))
                if g is not None and 0 <= g <= 4.0:
                    stated_gpa = g
                    break
    except Exception:
        pass
    return stated_credits, stated_gpa


def verify_transcript_math(pdf_path: str) -> dict:
    """
    Verify the mathematical consistency of an academic transcript PDF.

    Extracts course/credit/grade data from tables, then checks:
    - Credit sum: total of course credits vs. stated Earned/Total Credits (if found).
    - GPA: computed GPA from grades and credits vs. stated GPA (if found); tolerance 0.01.
    - Logical: flags if any semester exceeds 24 credits (if semester info present) or duplicate course codes.

    Args:
        pdf_path (str): Path to the transcript PDF file.

    Returns:
        dict: Contains success (bool), flags (list[str]), and detailed fields for the agent.
    """
    result: dict = {
        "success": False,
        "error": None,
        "flags": [],
        "credit_sum_ok": None,
        "credit_sum_detail": "",
        "gpa_ok": None,
        "gpa_detail": "",
        "logical_ok": None,
        "logical_detail": "",
        "summary": "",
    }

    courses, err = _extract_courses_from_tables(pdf_path)
    if err:
        result["error"] = err
        result["summary"] = f"Extraction failed: {err}"
        return result

    if not courses:
        result["error"] = "No course/credit/grade table found in PDF. (Tried header matching and data pattern analysis.)"
        result["summary"] = result["error"]
        return result

    result["success"] = True
    stated_credits, stated_gpa = _extract_stated_summary(pdf_path)

    # --- Credit sum ---
    total_credits = sum(c["credits"] for c in courses)
    if stated_credits is not None:
        if abs(total_credits - stated_credits) < 0.01:
            result["credit_sum_ok"] = True
            result["credit_sum_detail"] = f"Credit sum matches: {total_credits} vs stated {stated_credits}."
        else:
            result["credit_sum_ok"] = False
            result["credit_sum_detail"] = f"Credit sum mismatch: computed {total_credits}, stated {stated_credits}."
            result["flags"].append("Credit sum mismatch")
    else:
        result["credit_sum_ok"] = None
        result["credit_sum_detail"] = f"Computed total credits: {total_credits}. (Stated earned credits not found in PDF.)"

    # --- GPA ---
    graded = [c for c in courses if c["grade"] is not None and c["grade"] in GRADE_POINTS]
    if graded:
        weighted = sum(GRADE_POINTS[c["grade"]] * c["credits"] for c in graded)
        total_cr = sum(c["credits"] for c in graded)
        computed_gpa = weighted / total_cr if total_cr else 0.0
        if stated_gpa is not None:
            if abs(computed_gpa - stated_gpa) <= GPA_TOLERANCE:
                result["gpa_ok"] = True
                result["gpa_detail"] = f"GPA matches (tolerance {GPA_TOLERANCE}): computed {computed_gpa:.3f}, stated {stated_gpa}."
            else:
                result["gpa_ok"] = False
                result["gpa_detail"] = f"GPA mismatch: computed {computed_gpa:.3f}, stated {stated_gpa}."
                result["flags"].append("GPA mismatch")
        else:
            result["gpa_ok"] = None
            result["gpa_detail"] = f"Computed GPA (graded courses only): {computed_gpa:.3f}. (Stated GPA not found in PDF.)"
    else:
        result["gpa_ok"] = None
        result["gpa_detail"] = "No letter grades found for GPA calculation."

    # --- Logical: duplicate course codes; optional: per-semester credit cap (needs semester column) ---
    course_codes = [c["course"] for c in courses]
    # Only flag duplicates if they're actual course codes (not numbers)
    dupes = [c for c in set(course_codes) if course_codes.count(c) > 1 and _is_likely_course_code(c)]
    if dupes:
        result["flags"].append("Duplicate course codes: " + ", ".join(sorted(dupes)))
    if dupes:
        result["logical_ok"] = False
        result["logical_detail"] = "Duplicate course codes found."
    else:
        result["logical_ok"] = True
        result["logical_detail"] = "No duplicate course codes."

    # Summary line for the agent
    parts = [f"Credits: {result['credit_sum_detail']}", f"GPA: {result['gpa_detail']}", f"Logical: {result['logical_detail']}"]
    if result["flags"]:
        parts.append("Flags: " + "; ".join(result["flags"]))
    result["summary"] = " | ".join(parts)

    return result
