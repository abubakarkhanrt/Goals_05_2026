"""Unified assessment / Q&A dispatch for local (Ollama) and cloud (Gemini) backends."""

from __future__ import annotations

import json
import logging
from typing import Any

from .llm_config import llm_backend, llm_enabled
from .schemas import TranscriptAssessment

logger = logging.getLogger(__name__)


async def assess_transcript(
    pdf_path: str | None,
    math_result: dict | None = None,
    spatial_result: dict | None = None,
    dates_result: dict | None = None,
    image_paths: list[str] | None = None,
) -> TranscriptAssessment:
    backend = llm_backend()
    if backend == "local":
        from .ollama_client import assess_with_ollama

        return await assess_with_ollama(
            pdf_path, math_result, spatial_result, dates_result, image_paths
        )
    if backend == "cloud":
        from .cloud_client import assess_with_cloud

        return await assess_with_cloud(
            pdf_path, math_result, spatial_result, dates_result, image_paths
        )
    raise RuntimeError("LLM assessment is disabled (rules-only mode)")


async def answer_session_question(
    question: str,
    pdf_path: str | None,
    math_result: dict | None = None,
    spatial_result: dict | None = None,
    last_assessment: dict | None = None,
    dates_result: dict | None = None,
    image_paths: list[str] | None = None,
) -> str:
    backend = llm_backend()
    if backend == "local":
        from .ollama_client import answer_session_question as ollama_qa

        return await ollama_qa(
            question,
            pdf_path,
            math_result,
            spatial_result,
            last_assessment,
            dates_result,
            image_paths,
        )
    if backend == "cloud":
        from .cloud_client import answer_session_question as cloud_qa

        return await cloud_qa(
            question,
            pdf_path,
            math_result,
            spatial_result,
            last_assessment,
            dates_result,
            image_paths,
        )
    raise RuntimeError("LLM Q&A is disabled (rules-only mode)")


def llm_unavailable_message(exc: Exception) -> str:
    backend = llm_backend()
    label = "Ollama" if backend == "local" else "Cloud LLM"
    return f"{label} unavailable ({exc}); used rule-based scoring."
