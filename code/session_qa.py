"""Session Q&A answers from cached verification evidence (rules or Ollama)."""

from __future__ import annotations

import json
from typing import Any


def build_qa_context(
    pdf_path: str | None,
    math_result: dict | None,
    spatial_result: dict | None,
    last_assessment: dict | None = None,
    dates_result: dict | None = None,
) -> dict[str, Any]:
    return {
        "pdf_path": pdf_path,
        "math_verification": math_result or {},
        "spatial_verification": spatial_result or {},
        "dates_verification": dates_result or {},
        "last_assessment": last_assessment or {},
    }


def answer_with_rules(question: str, context: dict[str, Any]) -> str:
    """Deterministic explanation when Ollama is disabled or unavailable."""
    math = context.get("math_verification") or {}
    spatial = context.get("spatial_verification") or {}
    dates = context.get("dates_verification") or {}
    pdf_path = context.get("pdf_path") or "(unknown)"
    lines = [
        f"PDF: {pdf_path}",
        f"Question: {question}",
        "",
        "Math verification:",
        f"  success: {math.get('success')}",
        f"  credit_sum_ok: {math.get('credit_sum_ok')}",
        f"  credit_sum_detail: {math.get('credit_sum_detail') or math.get('summary') or '(none)'}",
        f"  gpa_ok: {math.get('gpa_ok')}",
        f"  gpa_detail: {math.get('gpa_detail') or '(none)'}",
        f"  logical_ok: {math.get('logical_ok')}",
        f"  flags: {', '.join(math.get('flags') or []) or '(none)'}",
        "",
        "Spatial verification:",
        f"  success: {spatial.get('success')}",
        f"  alignment_ok: {spatial.get('alignment_ok')}",
        f"  font_ok: {spatial.get('font_ok')}",
        f"  flags: {', '.join(spatial.get('flags') or []) or '(none)'}",
        "",
        "Date verification:",
        f"  success: {dates.get('success')}",
        f"  reference_datetime: {dates.get('reference_datetime')}",
        f"  dates_ok: {dates.get('dates_ok')}",
        f"  future_dates: {dates.get('future_dates') or '(none)'}",
        f"  flags: {', '.join(dates.get('flags') or []) or '(none)'}",
        "",
        "Use the credit_sum_detail / flags above for numeric questions (e.g. computed 24.0).",
    ]
    return "\n".join(lines)


def format_evidence_for_prompt(context: dict[str, Any]) -> str:
    return json.dumps(context, indent=2)
