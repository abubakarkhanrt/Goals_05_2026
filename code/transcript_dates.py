"""
Reference clock and transcript date validation.

get_current_datetime — authoritative "now" for the agent (UTC).
verify_transcript_dates — extract dates from PDF text; flag any future dates.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pdfplumber

_MONTH_MAP = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

# ISO, US numeric, and "Month DD, YYYY" (common on transcripts)
_DATE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "iso",
        re.compile(r"\b(20\d{2}|19\d{2})-(0?[1-9]|1[0-2])-(0?[1-9]|[12]\d|3[01])\b"),
    ),
    (
        "mdy",
        re.compile(
            r"\b(0?[1-9]|1[0-2])[/-](0?[1-9]|[12]\d|3[01])[/-]((?:20\d{2}|19\d{2})|\d{2})\b"
        ),
    ),
    (
        "mdy_text",
        re.compile(
            r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
            r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
            r"Dec(?:ember)?)\.?\s+(0?[1-9]|[12]\d|3[01]),?\s+(20\d{2}|19\d{2})\b",
            re.IGNORECASE,
        ),
    ),
]


def get_current_datetime(*, reference: datetime | None = None) -> dict[str, Any]:
    """Return the agent reference date/time (UTC) used for transcript date checks."""
    now = reference or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    return {
        "success": True,
        "reference_datetime": now.isoformat(),
        "reference_date": now.date().isoformat(),
        "timezone": "UTC",
        "unix_timestamp": now.timestamp(),
    }


def _normalize_year(year: int) -> int:
    if year < 100:
        return 2000 + year if year <= 69 else 1900 + year
    return year


def _parse_match(kind: str, match: re.Match[str]) -> date | None:
    try:
        if kind == "iso":
            y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
            return date(y, m, d)
        if kind == "mdy":
            m, d, y = int(match.group(1)), int(match.group(2)), _normalize_year(int(match.group(3)))
            return date(y, m, d)
        if kind == "mdy_text":
            month = _MONTH_MAP[match.group(1).lower()[:3]]
            d = int(match.group(2))
            y = int(match.group(3))
            return date(y, month, d)
    except (ValueError, KeyError):
        return None
    return None


def extract_dates_from_text(text: str) -> list[dict[str, str]]:
    """Find date-like strings in transcript text and parse them."""
    found: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for kind, pattern in _DATE_PATTERNS:
        for match in pattern.finditer(text or ""):
            raw = match.group(0)
            parsed = _parse_match(kind, match)
            if parsed is None:
                continue
            key = (raw, parsed.isoformat())
            if key in seen:
                continue
            seen.add(key)
            found.append({"text": raw, "parsed_date": parsed.isoformat(), "pattern": kind})

    found.sort(key=lambda item: item["parsed_date"])
    return found


def _extract_pdf_text(pdf_path: str) -> str:
    parts: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def verify_transcript_dates(
    pdf_path: str,
    *,
    reference: datetime | None = None,
) -> dict[str, Any]:
    """
    Parse dates from transcript PDF text and flag any date after the reference clock.
    """
    clock = get_current_datetime(reference=reference)
    ref_date = date.fromisoformat(clock["reference_date"])

    path = Path(pdf_path)
    if not path.is_file():
        return {
            **clock,
            "success": False,
            "dates_ok": False,
            "logical_ok": False,
            "dates_found": [],
            "future_dates": [],
            "flags": [f"PDF not found: {pdf_path}"],
            "message": "Unable to read transcript PDF for date checks.",
        }

    try:
        text = _extract_pdf_text(str(path))
    except Exception as exc:
        return {
            **clock,
            "success": False,
            "dates_ok": False,
            "logical_ok": False,
            "dates_found": [],
            "future_dates": [],
            "flags": [f"Failed to read PDF text: {exc}"],
            "message": "PDF text extraction failed for date verification.",
        }

    dates_found = extract_dates_from_text(text)
    future_dates: list[dict[str, str]] = []
    for item in dates_found:
        parsed = date.fromisoformat(item["parsed_date"])
        if parsed > ref_date:
            future_dates.append(
                {
                    **item,
                    "reason": f"after reference date {ref_date.isoformat()}",
                }
            )

    flags: list[str] = []
    if not dates_found:
        flags.append("No parseable dates found in transcript text")
    for item in future_dates:
        flags.append(f"Future date on transcript: {item['text']} ({item['parsed_date']})")

    dates_ok = len(future_dates) == 0
    return {
        **clock,
        "success": True,
        "dates_ok": dates_ok,
        "logical_ok": dates_ok,
        "dates_found": dates_found,
        "future_dates": future_dates,
        "flags": flags,
        "message": (
            f"Checked {len(dates_found)} date(s) against reference {clock['reference_datetime']}. "
            + (
                "No future dates detected."
                if dates_ok
                else f"{len(future_dates)} future date(s) detected."
            )
        ),
    }
