"""Rule-based transcript assessment (no LLM)."""

from __future__ import annotations

from .schemas import TranscriptAssessment


def build_rules_assessment(
    pdf_path: str | None,
    math_result: dict | None = None,
    spatial_result: dict | None = None,
    dates_result: dict | None = None,
) -> TranscriptAssessment:
    if not pdf_path:
        return TranscriptAssessment(
            legitimacy_score=0.4,
            risk_level="Manual Review",
            explanation_summary="Unable to verify: no PDF path was provided.",
            flags=["Missing PDF path"],
        )

    flags: list[str] = []
    if isinstance(math_result, dict):
        flags.extend(math_result.get("flags", []) or [])
    if isinstance(spatial_result, dict):
        flags.extend(spatial_result.get("flags", []) or [])
    if isinstance(dates_result, dict):
        flags.extend(dates_result.get("flags", []) or [])

    math_success = bool((math_result or {}).get("success", False))
    spatial_success = bool((spatial_result or {}).get("success", False))
    dates_success = bool((dates_result or {}).get("success", False))

    math_failed = (not math_success) or not all(
        bool((math_result or {}).get(k, True))
        for k in ("credit_sum_ok", "gpa_ok", "logical_ok")
    )
    spatial_flagged = bool(spatial_success) and (
        not bool((spatial_result or {}).get("alignment_ok", True))
        or not bool((spatial_result or {}).get("font_ok", True))
    )
    dates_failed = bool(dates_success) and not bool((dates_result or {}).get("dates_ok", True))

    if math_failed or dates_failed:
        risk_level = "High Risk"
        legitimacy_score = 0.2
    elif (not math_success) or (not spatial_success) or spatial_flagged or not dates_success:
        risk_level = "Manual Review"
        legitimacy_score = 0.5
    else:
        risk_level = "Auto-Approve"
        legitimacy_score = 0.85

    math_details = {
        "success": math_success,
        "credit_sum_ok": (math_result or {}).get("credit_sum_ok", None),
        "gpa_ok": (math_result or {}).get("gpa_ok", None),
        "logical_ok": (math_result or {}).get("logical_ok", None),
        "message": (math_result or {}).get("message", None),
    }
    spatial_details = {
        "success": spatial_success,
        "alignment_ok": (spatial_result or {}).get("alignment_ok", None),
        "font_ok": (spatial_result or {}).get("font_ok", None),
        "message": (spatial_result or {}).get("message", None),
    }
    dates_details = {
        "success": dates_success,
        "dates_ok": (dates_result or {}).get("dates_ok", None),
        "reference_datetime": (dates_result or {}).get("reference_datetime", None),
        "future_dates": (dates_result or {}).get("future_dates", []),
        "message": (dates_result or {}).get("message", None),
    }

    explanation_summary = (
        f"PDF: {pdf_path}. "
        f"verify_transcript_math: success={math_details['success']}, "
        f"credit_sum_ok={math_details['credit_sum_ok']}, gpa_ok={math_details['gpa_ok']}, "
        f"logical_ok={math_details['logical_ok']}"
        + (f", message={math_details['message']}" if math_details["message"] else "")
        + ". "
        f"verify_transcript_spatial: success={spatial_details['success']}, "
        f"alignment_ok={spatial_details['alignment_ok']}, font_ok={spatial_details['font_ok']}"
        + (f", message={spatial_details['message']}" if spatial_details["message"] else "")
        + ". "
        f"verify_transcript_dates: success={dates_details['success']}, "
        f"dates_ok={dates_details['dates_ok']}, "
        f"reference={dates_details['reference_datetime']}"
        + (f", message={dates_details['message']}" if dates_details["message"] else "")
        + f". Decision: {risk_level} (rule-based)."
    )

    return TranscriptAssessment(
        legitimacy_score=legitimacy_score,
        risk_level=risk_level,
        explanation_summary=explanation_summary,
        flags=flags,
    )
