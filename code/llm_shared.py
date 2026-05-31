"""Shared LLM prompts, image helpers, and LiteLLM completion utilities."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from .llm_config import (
    llm_image_max_edge,
    llm_max_images,
    llm_send_images,
    llm_temperature,
    llm_timeout_seconds,
)
from .schemas import TranscriptAssessment, assessment_example, assessment_json_schema

try:
    from .observability.metrics import track_task_async
except ImportError:  # pragma: no cover
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def track_task_async(task: str):  # type: ignore[misc]
        yield

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)
_VISION_ERROR_MARKERS = (
    "missing data required for image input",
    "does not support images",
    "multimodal",
)

ASSESSOR_RULES = """You are a Transcript Risk Assessor.

Inputs (two separate paths — do not confuse them):
1. PNG page images — visual renders of the transcript for your eyes only.
2. JSON tool evidence — produced by Python tools that parsed the original PDF file
   (verify_transcript_math, verify_transcript_spatial, verify_transcript_dates). This JSON is authoritative for
   numeric checks, flags, date checks, and structured extraction results.

Rules:
- Use PNG images for layout, alignment, fonts, and visible transcript content.
- Use tool JSON for credit sums, GPA checks, and deterministic flags.
- Do NOT invent courses, grades, GPAs, or layout facts not in the images or tool JSON.
- If math_verification.success is false or flags report mismatches, do NOT Auto-Approve
  based on visuals alone — prefer Manual Review or High Risk.
- If dates_verification reports future_dates or dates_ok is false, treat as High Risk /
  Manual Review — transcript issue dates must not be after the reference clock.
- Base legitimacy_score (0.0–1.0), risk_level, explanation_summary, and flags on BOTH sources.
- risk_level must be exactly one of: Auto-Approve, Manual Review, High Risk.
- Include important flags from both math and spatial tools in the flags list.
- Keep explanation_summary concise; cite tool JSON and visible image details."""

ASSESSOR_OUTPUT_CONTRACT = """
Output format (strict):
- Return a single JSON object only. No markdown, no code fences, no commentary.
- Use exactly these top-level keys: legitimacy_score, risk_level, explanation_summary, flags
- Do not add any other keys (no assessment_summary, summary, or nested wrapper objects).

JSON Schema:
{schema}

Example (structure only — base your answer on the actual evidence):
{example}
"""

SESSION_QA_INSTRUCTION = """You are a Transcript Verification assistant answering follow-up questions.

Inputs (two separate paths):
1. PNG page images — visual renders for layout and visible numbers.
2. JSON tool evidence — from Python tools that parsed the original PDF file. Authoritative
   for verify_transcript_math / verify_transcript_spatial / verify_transcript_dates outputs.

Rules:
- Answer the user's question directly in plain language.
- For tool output questions, quote the tool JSON; use images to supplement visuals only.
- Do NOT claim a tool was run unless the evidence JSON contains its results.
- Do NOT invent courses, grades, GPAs, or layout facts not in the images or tool JSON.
- For numeric questions (e.g. "how did you compute 24.0?"), cite credit_sum_detail, gpa_detail, flags.
- Keep answers concise and helpful.
- Do NOT output JSON assessment schema — write a natural language explanation."""


def build_assessor_system_instruction() -> str:
    return (
        ASSESSOR_RULES
        + ASSESSOR_OUTPUT_CONTRACT.format(
            schema=json.dumps(assessment_json_schema(), indent=2),
            example=json.dumps(assessment_example(), indent=2),
        )
    )


def evidence_payload(
    pdf_path: str | None,
    math_result: dict | None,
    spatial_result: dict | None,
    dates_result: dict | None = None,
) -> dict[str, Any]:
    return {
        "pdf_path": pdf_path,
        "math_verification": math_result or {},
        "spatial_verification": spatial_result or {},
        "dates_verification": dates_result or {},
    }


def extract_json_object(raw: str) -> str:
    text = _FENCE_RE.sub("", (raw or "").strip()).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def parse_assessment_response(raw: str) -> TranscriptAssessment:
    return TranscriptAssessment.model_validate_json(extract_json_object(raw))


def is_vision_unsupported_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in _VISION_ERROR_MARKERS)


def llm_image_paths(image_paths: list[str] | None) -> list[str]:
    if not llm_send_images():
        return []
    paths = [p for p in (image_paths or []) if p and Path(p).is_file()]
    limit = llm_max_images()
    if limit > 0:
        paths = paths[:limit]
    return paths


def _read_image_bytes_for_llm(image_path: str) -> tuple[bytes, str]:
    path = Path(image_path)
    suffix = path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    raw = path.read_bytes()
    max_edge = llm_image_max_edge()
    if max_edge <= 0:
        return raw, mime

    try:
        from PIL import Image
    except ImportError:
        return raw, mime

    with Image.open(io.BytesIO(raw)) as img:
        if max(img.size) <= max_edge:
            return raw, mime
        resized = img.copy()
        resized.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        save_format = "PNG" if suffix == ".png" else "JPEG"
        resized.save(buf, format=save_format, optimize=True)
        logger.info(
            "Resized LLM image %s from %sx%s to %sx%s (max edge %s)",
            path.name,
            img.size[0],
            img.size[1],
            resized.size[0],
            resized.size[1],
            max_edge,
        )
        out_mime = "image/png" if save_format == "PNG" else "image/jpeg"
        return buf.getvalue(), out_mime


def user_message_with_images(text: str, image_paths: list[str] | None) -> str | list[dict[str, Any]]:
    paths = llm_image_paths(image_paths)
    if not paths:
        return text

    parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for image_path in paths:
        payload, mime = _read_image_bytes_for_llm(image_path)
        encoded = base64.b64encode(payload).decode("ascii")
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{encoded}"},
            }
        )
    return parts


async def litellm_chat(
    messages: list[dict[str, Any]],
    *,
    model: str,
    provider_label: str,
    api_base: str | None = None,
    json_mode: bool = False,
    image_count: int = 0,
    operation: str = "chat",
) -> str:
    import litellm

    timeout = llm_timeout_seconds()
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": llm_temperature(),
        "timeout": timeout,
    }
    if api_base:
        kwargs["api_base"] = api_base
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    logger.info(
        "%s request started model=%s images=%d timeout=%ss",
        provider_label,
        model,
        image_count,
        int(timeout),
    )
    started = time.monotonic()
    async with track_task_async("llm_chat"):
        try:
            response = await asyncio.wait_for(litellm.acompletion(**kwargs), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise TimeoutError(
                f"{provider_label} did not respond within {int(timeout)}s "
                f"(model={model}, images={image_count})"
            ) from exc

    elapsed = time.monotonic() - started
    text = response.choices[0].message.content
    if not text:
        raise RuntimeError(f"{provider_label} returned empty content")
    logger.info("%s request finished in %.1fs", provider_label, elapsed)

    try:
        from .llm_config import llm_backend
        from .runtime.session import get_runtime_session
        from .db.store import persist_llm_call

        persist_llm_call(
            get_runtime_session().session_id,
            operation,
            model=model,
            backend=llm_backend() if llm_backend() else provider_label.lower(),
            duration_s=elapsed,
            image_count=image_count,
            status="success",
        )
    except Exception:
        pass

    return text.strip()
