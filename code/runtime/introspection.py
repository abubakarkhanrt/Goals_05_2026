"""Collect agent/tool/config metadata for slash commands."""

from __future__ import annotations

import inspect
import os
from pathlib import Path
from typing import Any

from .. import transcript_dates, transcript_math, transcript_spatial


def workflow_tools() -> list[dict[str, str]]:
    tools = [
        ("get_current_datetime", transcript_dates.get_current_datetime),
        ("verify_transcript_dates", transcript_dates.verify_transcript_dates),
        ("verify_transcript_math", transcript_math.verify_transcript_math),
        ("verify_transcript_spatial", transcript_spatial.verify_transcript_spatial),
    ]
    rows: list[dict[str, str]] = []
    for name, fn in tools:
        doc = (inspect.getdoc(fn) or "").strip().split("\n")[0]
        rows.append({"name": name, "description": doc or "(no description)"})
    return rows


def workflow_agents(root_agent: Any) -> list[dict[str, str]]:
    if root_agent is None:
        return [{"name": "(unknown)", "type": "?", "description": "root_agent not set"}]
    agent_type = type(root_agent).__name__
    name = getattr(root_agent, "name", None) or "(unnamed)"
    desc = (getattr(root_agent, "description", None) or "").strip()
    if not desc:
        desc = f"ADK {agent_type} orchestrating transcript verification nodes."
    return [{"name": name, "type": agent_type, "description": desc}]


def runtime_config() -> list[tuple[str, str]]:
    from ..llm_config import (
        cloud_model,
        llm_backend,
        llm_enabled,
        llm_temperature,
        ollama_api_base,
        ollama_model,
    )

    backend = llm_backend()
    return [
        ("google-adk", os.environ.get("GOOGLE_ADK_VERSION", "2.1.0 (pinned in requirements.txt)")),
        ("llm_backend", backend),
        ("assessment_backend", "llm" if llm_enabled() else "rules (local Python)"),
        ("use_ollama", str(backend == "local")),
        ("ollama_model", ollama_model() if backend == "local" else "(n/a)"),
        ("ollama_api_base", ollama_api_base() if backend == "local" else "(n/a)"),
        ("cloud_model", cloud_model() if backend == "cloud" else "(n/a)"),
        ("llm_temperature", str(llm_temperature()) if llm_enabled() else "(n/a)"),
        ("entry_points", "adk run code_local | adk run code_cloud"),
        ("provider", backend if llm_enabled() else _provider_label()),
        ("environment", os.environ.get("ENVIRONMENT", os.environ.get("ENV", "local"))),
        ("vertex_ai", os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")),
        ("verbose", os.environ.get("TRANSCRIPT_AGENT_VERBOSE", "0")),
    ]


def _provider_label() -> str:
    if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in ("1", "true", "yes"):
        return "vertex_ai"
    if os.environ.get("GOOGLE_API_KEY"):
        return "google_ai_studio"
    return "(none configured)"


def model_info() -> dict[str, Any]:
    """Active and configured models for /model and /config."""
    from ..llm_config import (
        cloud_llm_configured,
        cloud_model,
        llm_backend,
        llm_temperature,
        ollama_api_base,
        ollama_model,
    )

    backend = llm_backend()
    vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "FALSE").strip()
    has_cloud_key = cloud_llm_configured()

    if backend == "local":
        litellm_id = ollama_model()
        ollama_name = litellm_id.removeprefix("ollama/") if litellm_id.startswith("ollama/") else litellm_id
        active = {
            "deployment": "local",
            "provider": "ollama",
            "model": ollama_name,
            "litellm_model_id": litellm_id,
            "api_base": ollama_api_base(),
            "temperature": llm_temperature(),
            "used_for": "reads session PNGs + PDF tool JSON for assessment/Q&A",
            "entry_point": "adk run code_local",
        }
    elif backend == "cloud":
        active = {
            "deployment": "cloud",
            "provider": "gemini (google ai studio)" if has_cloud_key else "cloud (misconfigured)",
            "model": cloud_model(),
            "litellm_model_id": cloud_model(),
            "api_base": "(google api)",
            "temperature": llm_temperature(),
            "used_for": "reads session PNGs + PDF tool JSON for assessment/Q&A",
            "entry_point": "adk run code_cloud",
        }
    else:
        active = {
            "deployment": "local",
            "provider": "(none — rule-based)",
            "model": "(none)",
            "litellm_model_id": "(n/a)",
            "api_base": "(n/a)",
            "temperature": "(n/a)",
            "used_for": "final TranscriptAssessment via Python rules",
            "entry_point": "adk run code_local or code_cloud to enable LLM",
        }

    if vertex.lower() in ("1", "true", "yes"):
        cloud_provider = "vertex_ai"
    elif has_cloud_key:
        cloud_provider = "google_ai_studio"
    else:
        cloud_provider = "(not configured)"

    cloud = {
        "deployment": "cloud",
        "provider": cloud_provider,
        "model": cloud_model(),
        "configured": has_cloud_key,
        "used_for": "assessment/Q&A when started via adk run code_cloud",
        "entry_point": "adk run code_cloud",
    }

    local = {
        "deployment": "local",
        "provider": "ollama",
        "model": ollama_model(),
        "configured": True,
        "used_for": "assessment/Q&A when started via adk run code_local",
        "entry_point": "adk run code_local",
    }

    pdf_tools = {
        "deployment": "local",
        "provider": "python",
        "model": "(none)",
        "used_for": "verify_transcript_math + verify_transcript_spatial + verify_transcript_dates on PDF",
    }

    return {"active_assessment": active, "pdf_verification": pdf_tools, "cloud_configured": cloud, "local_configured": local}


def model_info_rows() -> list[list[str]]:
    """Flat rows for /model table display."""
    info = model_info()
    rows: list[list[str]] = []
    for section, label in (
        ("active_assessment", "Active (assessment)"),
        ("pdf_verification", "PDF tools"),
        ("local_configured", "Local (configured)"),
        ("cloud_configured", "Cloud (configured)"),
    ):
        block = info[section]
        rows.append([label, block.get("deployment", ""), block.get("provider", ""), block.get("model", "")])
        if section == "active_assessment" and block.get("litellm_model_id"):
            rows.append(["", "", "litellm id", str(block.get("litellm_model_id", ""))])
            if block.get("api_base") and block["api_base"] != "(n/a)":
                rows.append(["", "", "api base", str(block.get("api_base", ""))])
            if block.get("temperature") and block["temperature"] != "(n/a)":
                rows.append(["", "", "temperature", str(block.get("temperature", ""))])
        rows.append(["", "", "used for", str(block.get("used_for", ""))])
    return rows
