"""User intent classification for verify vs session Q&A."""

from __future__ import annotations

import re

_PDF_PATH_RE = re.compile(r"(?P<path>\S+\.pdf)", re.IGNORECASE)
_BARE_PDF_RE = re.compile(r"^\s*\S+\.pdf\s*$", re.IGNORECASE)

_QA_PATTERNS = (
    r"\?",
    r"\bexplain\b",
    r"\bhow\b",
    r"\bwhy\b",
    r"\bwhat\b",
    r"\bdescribe\b",
    r"\btell me\b",
    r"\bbreakdown\b",
    r"\bdetails?\b",
    r"\bcompute[ds]?\b",
    r"\bcalculated\b",
    r"\bwalk me through\b",
    r"\bshow me\b",
)

_VERIFY_PATTERNS = (
    r"\bverify\b",
    r"\bassess\b",
    r"\bcheck\b",
    r"\bscan\b",
    r"\baudit\b",
    r"\banaly[sz]e\b",
    r"\bvalidate\b",
)


def extract_pdf_path(text: str) -> str | None:
    match = _PDF_PATH_RE.search(text or "")
    return match.group("path") if match else None


def is_explicit_verify_intent(text: str) -> bool:
    return bool(re.search("|".join(_VERIFY_PATTERNS), text or "", re.IGNORECASE))


def is_qa_intent(text: str) -> bool:
    """True for follow-up / explain questions (not a bare PDF path submit)."""
    stripped = (text or "").strip()
    if not stripped:
        return False
    if _BARE_PDF_RE.match(stripped):
        return False
    if is_explicit_verify_intent(stripped) and not re.search(
        r"\b(explain|how|why|what)\b", stripped, re.IGNORECASE
    ):
        return False
    return any(re.search(p, stripped, re.IGNORECASE) for p in _QA_PATTERNS)


def classify_turn(
    text: str,
    *,
    has_cached_verification: bool,
    pdf_path: str | None = None,
) -> str:
    """
    Returns: 'slash' handled elsewhere | 'qa' | 'qa_refresh' | 'verify' | 'need_pdf'
    """
    stripped = (text or "").strip()
    pdf_in_message = pdf_path or extract_pdf_path(stripped)

    if is_qa_intent(stripped):
        if not pdf_in_message and not has_cached_verification:
            return "need_pdf"
        if pdf_in_message or has_cached_verification:
            return "qa"
        return "need_pdf"

    if pdf_in_message:
        return "verify"

    if has_cached_verification and stripped:
        # Conversational follow-up without keywords still goes to Q&A if we have context.
        return "qa"

    return "need_pdf"
