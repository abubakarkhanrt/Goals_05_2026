"""Direct Ollama calls via LiteLLM."""

from __future__ import annotations

import json
import logging
from typing import Any

from .llm_config import ollama_api_base, ollama_model
from .llm_shared import (
    SESSION_QA_INSTRUCTION,
    build_assessor_system_instruction,
    evidence_payload,
    is_vision_unsupported_error,
    litellm_chat,
    llm_image_paths,
    parse_assessment_response,
    user_message_with_images,
)
from .schemas import TranscriptAssessment

# Re-export for tests and ollama_assessor.py
OLLAMA_ASSESSOR_INSTRUCTION = build_assessor_system_instruction()
from .llm_shared import extract_json_object  # noqa: E402 — re-export for tests

logger = logging.getLogger(__name__)


async def _ollama_chat(
    messages: list[dict[str, Any]],
    *,
    json_mode: bool = False,
    image_count: int = 0,
    operation: str = "chat",
) -> str:
    return await litellm_chat(
        messages,
        model=ollama_model(),
        provider_label="Ollama",
        api_base=ollama_api_base(),
        json_mode=json_mode,
        image_count=image_count,
        operation=operation,
    )


async def answer_session_question(
    question: str,
    pdf_path: str | None,
    math_result: dict | None = None,
    spatial_result: dict | None = None,
    last_assessment: dict | None = None,
    dates_result: dict | None = None,
    image_paths: list[str] | None = None,
) -> str:
    evidence = evidence_payload(pdf_path, math_result, spatial_result, dates_result)
    if last_assessment:
        evidence["last_assessment"] = last_assessment

    user_text = (
        f"Question: {question}\n\n"
        "Tool evidence from PDF parsing (authoritative — images are visual supplement only):\n"
        + json.dumps(evidence, indent=2)
    )

    llm_images = llm_image_paths(image_paths)
    logger.info(
        "Session Q&A via Ollama model=%s api_base=%s images=%d",
        ollama_model(),
        ollama_api_base(),
        len(llm_images),
    )

    system = SESSION_QA_INSTRUCTION
    user_content = user_message_with_images(user_text, llm_images)
    try:
        return await _ollama_chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user_content}],
            image_count=len(llm_images),
            operation="qa",
        )
    except Exception as exc:
        if not llm_images or not is_vision_unsupported_error(exc):
            raise
        logger.warning("Vision unsupported for Q&A, retrying text-only: %s", exc)
        return await _ollama_chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user_text}],
            image_count=0,
            operation="qa",
        )


async def assess_with_ollama(
    pdf_path: str | None,
    math_result: dict | None = None,
    spatial_result: dict | None = None,
    dates_result: dict | None = None,
    image_paths: list[str] | None = None,
) -> TranscriptAssessment:
    evidence = evidence_payload(pdf_path, math_result, spatial_result, dates_result)
    system = build_assessor_system_instruction()
    user_text = (
        "Assess the transcript using the attached PNG page images (visual) and the tool "
        "evidence JSON below (from PDF parsing — authoritative for math/spatial checks).\n"
        "Return only JSON matching the schema above.\n"
        + json.dumps(evidence, indent=2)
    )

    llm_images = llm_image_paths(image_paths)
    logger.info(
        "Calling Ollama model=%s api_base=%s images=%d",
        ollama_model(),
        ollama_api_base(),
        len(llm_images),
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_message_with_images(user_text, llm_images)},
    ]

    try:
        raw = await _ollama_chat(messages, json_mode=True, image_count=len(llm_images), operation="assess")
    except Exception as exc:
        if not llm_images or not is_vision_unsupported_error(exc):
            raise
        logger.warning("Vision unsupported for assessment, retrying text-only: %s", exc)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ]
        raw = await _ollama_chat(messages, json_mode=True, image_count=0, operation="assess")

    try:
        return parse_assessment_response(raw)
    except Exception as first_exc:
        logger.warning("Assessment JSON parse failed, retrying text-only: %s", first_exc)
        repair_user = (
            "Your previous response was invalid JSON or did not match the schema.\n"
            "Return ONLY a corrected JSON object with keys: "
            "legitimacy_score, risk_level, explanation_summary, flags.\n\n"
            f"Tool evidence:\n{json.dumps(evidence, indent=2)}\n\n"
            f"Invalid previous output:\n{raw[:4000]}"
        )
        repaired = await _ollama_chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": repair_user},
            ],
            json_mode=True,
            image_count=0,
            operation="assess_repair",
        )
        return parse_assessment_response(repaired)
