"""LLM backend configuration: local Ollama, cloud Gemini, or rules-only."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

LlmBackend = Literal["local", "cloud", "rules"]


def ollama_enabled() -> bool:
    return os.environ.get("USE_OLLAMA", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def cloud_llm_configured() -> bool:
    key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if key:
        return True
    return os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def llm_backend() -> LlmBackend:
    """Active assessment backend: local Ollama, cloud Gemini, or rules-only."""
    mode = os.environ.get("TRANSCRIPT_LLM_BACKEND", "").strip().lower()
    if mode == "cloud":
        return "cloud" if cloud_llm_configured() else "rules"
    if mode == "local":
        return "local" if ollama_enabled() else "rules"
    if ollama_enabled():
        return "local"
    return "rules"


def llm_enabled() -> bool:
    return llm_backend() in ("local", "cloud")


def assessment_mode_label() -> str:
    backend = llm_backend()
    if backend == "local":
        return f"ollama (local) — {ollama_model()}"
    if backend == "cloud":
        return f"cloud — {cloud_model()}"
    return "rules (local Python)"


def ollama_model() -> str:
    return os.environ.get("OLLAMA_MODEL", "ollama/gemma4:26b").strip()


def cloud_model() -> str:
    return os.environ.get("CLOUD_MODEL", "gemini/gemini-2.0-flash").strip()


def ollama_api_base() -> str:
    return os.environ.get("OLLAMA_API_BASE", "http://localhost:11434").strip()


def llm_temperature() -> float:
    try:
        return float(os.environ.get("OLLAMA_TEMPERATURE", os.environ.get("LLM_TEMPERATURE", "0.2")))
    except ValueError:
        return 0.2


def ollama_temperature() -> float:
    return llm_temperature()


def llm_timeout_seconds() -> float:
    try:
        raw = os.environ.get("OLLAMA_TIMEOUT_SECONDS", os.environ.get("LLM_TIMEOUT_SECONDS", "300"))
        return max(30.0, float(raw))
    except ValueError:
        return 300.0


def ollama_timeout_seconds() -> float:
    return llm_timeout_seconds()


def llm_image_max_edge() -> int:
    try:
        raw = os.environ.get("OLLAMA_IMAGE_MAX_EDGE", os.environ.get("LLM_IMAGE_MAX_EDGE", "1024"))
        return max(0, int(raw))
    except ValueError:
        return 1024


def ollama_image_max_edge() -> int:
    return llm_image_max_edge()


def llm_max_images() -> int:
    try:
        raw = os.environ.get("OLLAMA_MAX_IMAGES", os.environ.get("LLM_MAX_IMAGES", "4"))
        return max(0, int(raw))
    except ValueError:
        return 4


def ollama_max_images() -> int:
    return llm_max_images()


def llm_send_images() -> bool:
    return os.environ.get("OLLAMA_SEND_IMAGES", os.environ.get("LLM_SEND_IMAGES", "true")).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def ollama_send_images() -> bool:
    return llm_send_images()


def session_cache_dir() -> Path:
    raw = os.environ.get("SESSION_CACHE_DIR", ".session_cache").strip()
    return Path(raw)


def pdf_render_dpi() -> int:
    try:
        return max(72, int(os.environ.get("PDF_RENDER_DPI", "150")))
    except ValueError:
        return 150


def pdf_max_pages() -> int:
    try:
        return max(1, int(os.environ.get("PDF_MAX_PAGES", "20")))
    except ValueError:
        return 20


ROUTE_LLM = "llm"
ROUTE_OLLAMA = ROUTE_LLM  # backward compatible route name
ROUTE_RULES = "rules"
ROUTE_QA = "qa"
ROUTE_QA_REFRESH = "qa_refresh"
