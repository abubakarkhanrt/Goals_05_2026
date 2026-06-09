"""LLM runtime — connectivity, model selection, and ADK callbacks.

Workshop file 4 of 5: cloud vs Ollama routing, Gemini 503 fallback, Ollama sanitization.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.google_llm import Gemini
from google.adk.models.lite_llm import LiteLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from .constants import (
    HALLUCINATED_TOOL_ALIASES,
    INTERNET_PROBE_URL,
    STATE_OFFLINE_ONLY,
    VALID_TOOL_NAMES,
)

logger = logging.getLogger(__name__)


def _configure_cloud_auth() -> str | None:
    """Google AI Studio API keys require GOOGLE_GENAI_USE_VERTEXAI=false."""
    key = os.environ.get("GOOGLE_API_KEY", "").strip()
    use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if key and use_vertex:
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "false"
        return (
            "GOOGLE_API_KEY detected — switched to Google AI Studio "
            "(Vertex AI does not accept API keys)."
        )
    return None


_AUTH_NOTE = _configure_cloud_auth()


def _workshop_mode() -> bool:
    return os.environ.get("WORKSHOP_MODE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "local",
    }


def _raw_ollama_mode() -> bool:
    return os.environ.get("RAW_OLLAMA_MODE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _skip_startup_probe() -> bool:
    return os.environ.get("SKIP_STARTUP_PROBE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _probe_internet(timeout: float = 3.0) -> bool:
    try:
        req = urllib.request.Request(
            INTERNET_PROBE_URL,
            method="HEAD",
            headers={"User-Agent": "small-adk-riddle-agent/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 400
    except Exception:
        return False


def _cloud_configured() -> bool:
    key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if key:
        return True
    return os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _ollama_model() -> str:
    return os.environ.get("OLLAMA_MODEL", "ollama/gemma4:26b").strip()


def _cloud_model_name() -> str:
    raw = os.environ.get("CLOUD_MODEL", "gemini-2.0-flash").strip()
    for prefix in ("gemini/", "gemini:"):
        if raw.startswith(prefix):
            return raw[len(prefix) :]
    return raw


def _litellm_model_for_tools() -> str:
    name = _cloud_model_name()
    if "/" in name or name.startswith("ollama:"):
        return name
    return f"gemini/{name}"


def _build_cloud_llm() -> Gemini:
    return Gemini(model=_cloud_model_name())


def _ollama_api_base() -> str:
    return os.environ.get("OLLAMA_API_BASE", "http://localhost:11434").strip()


def _llm_temperature() -> float:
    try:
        return float(os.environ.get("LLM_TEMPERATURE", "0.3"))
    except ValueError:
        return 0.3


def _build_ollama_llm() -> LiteLlm:
    return LiteLlm(
        model=_ollama_model(),
        api_base=_ollama_api_base(),
        temperature=_llm_temperature(),
    )


def _resolve_runtime() -> tuple[Any, str, str, bool | None]:
    """Return (model, mode_label, litellm_model_str, internet_at_startup)."""
    if _workshop_mode():
        online = None if _skip_startup_probe() else _probe_internet()
        return (
            _build_ollama_llm(),
            "workshop (Ollama + offline riddles)",
            _ollama_model(),
            online,
        )

    if _skip_startup_probe():
        online = None
    else:
        online = _probe_internet()

    if online and _cloud_configured():
        return (
            _build_cloud_llm(),
            f"cloud (Gemini {_cloud_model_name()} + online riddles)",
            _litellm_model_for_tools(),
            online,
        )
    if online:
        return (
            _build_ollama_llm(),
            (
                "raw Ollama single-call demo (offline riddles; no GOOGLE_API_KEY)"
                if _raw_ollama_mode()
                else "local deterministic (offline riddles; no GOOGLE_API_KEY)"
            ),
            _ollama_model(),
            online,
        )
    return (
        _build_ollama_llm(),
        (
            "raw Ollama single-call demo (offline riddles)"
            if _raw_ollama_mode()
            else "local deterministic (offline riddles)"
        ),
        _ollama_model(),
        online,
    )


_ACTIVE_MODEL, _MODE_LABEL, _LITELLM_MODEL, _INTERNET_AT_STARTUP = _resolve_runtime()
_FORCE_LOCAL_LLM = (
    _workshop_mode() or (isinstance(_ACTIVE_MODEL, LiteLlm) and not _raw_ollama_mode())
)


def _should_use_local_llm(state: Any) -> bool:
    return bool(_FORCE_LOCAL_LLM or state.get("llm_fallback_active"))


def _is_using_cloud_model(model_obj: Any) -> bool:
    return isinstance(model_obj, Gemini)


def _is_cloud_transient_error(error: Exception) -> bool:
    msg = str(error).lower()
    if any(
        token in msg
        for token in (
            "503",
            "429",
            "unavailable",
            "high demand",
            "resource exhausted",
            "rate limit",
            "overloaded",
        )
    ):
        return True
    code = getattr(error, "code", None)
    if code in (503, 429, 500, 502):
        return True
    return type(error).__name__ in {"ServerError", "RateLimitError"}


def _cloud_error_summary(error: Exception) -> str:
    """Short, user-facing summary of a Gemini API failure."""
    code = getattr(error, "code", None)
    msg = str(error).strip() or type(error).__name__
    if ". {" in msg:
        msg = msg.split(". {", 1)[0].strip()
    elif "\n" in msg:
        msg = msg.split("\n", 1)[0].strip()
    if code is not None and str(code) not in msg:
        return f"{code} {msg}"
    return msg


def _activate_local_fallback(
    agent: Any | None = None,
    state: Any | None = None,
    error: Exception | None = None,
) -> LiteLlm:
    """Switch agent + tool helpers from cloud Gemini to local Ollama."""
    global _LITELLM_MODEL, _MODE_LABEL, _ACTIVE_MODEL, _FORCE_LOCAL_LLM

    local = _build_ollama_llm()
    _FORCE_LOCAL_LLM = True
    _ACTIVE_MODEL = local
    _LITELLM_MODEL = _ollama_model()
    _MODE_LABEL = "local fallback (Ollama + offline riddles)"
    if state is not None:
        state["llm_fallback_active"] = True
        state[STATE_OFFLINE_ONLY] = True
    if agent is not None:
        agent.model = local
    if error is not None:
        logger.warning(
            "Cloud Gemini unavailable (%s) — switched to local Ollama.",
            _cloud_error_summary(error),
        )
    else:
        logger.warning("Cloud Gemini unavailable — switched to local Ollama.")
    return local


def _content_to_text_summary(content: types.Content) -> str | None:
    lines: list[str] = []
    for part in content.parts or []:
        if part.text:
            lines.append(part.text)
        elif part.function_call:
            lines.append(f"[Tool call: {part.function_call.name}]")
        elif part.function_response:
            resp = part.function_response.response
            if isinstance(resp, dict):
                lines.append(f"[Tool result: {json.dumps(resp)}]")
            else:
                lines.append(f"[Tool result: {resp}]")
    if not lines:
        return None
    return "\n".join(lines)


def _sanitize_contents_for_ollama(
    contents: list[types.Content],
) -> list[types.Content]:
    cleaned: list[types.Content] = []
    for content in contents:
        text = _content_to_text_summary(content)
        if not text:
            continue
        role = content.role if content.role in ("user", "model") else "user"
        cleaned.append(
            types.Content(role=role, parts=[types.Part.from_text(text=text)])
        )
    return cleaned


async def _before_model(
    callback_context: CallbackContext,
    llm_request: Any,
) -> LlmResponse | None:
    from .game import (
        _handle_exit_command,
        _handle_local_fallback_turn,
        _handle_raw_ollama_turn,
        _last_user_text,
    )

    inv = callback_context.get_invocation_context()
    agent = inv.agent
    state = callback_context.state

    if (
        _should_use_local_llm(state)
        and not isinstance(agent.model, LiteLlm)
        and not state.get("llm_fallback_active")
    ):
        _activate_local_fallback(agent, state)

    user_text = _last_user_text(llm_request.contents)
    exit_response = _handle_exit_command(state, user_text)
    if exit_response is not None:
        return exit_response

    if _raw_ollama_mode():
        raw_local_response = _handle_raw_ollama_turn(state, user_text)
        if raw_local_response is not None:
            return raw_local_response

    if _should_use_local_llm(state):
        local_response = _handle_local_fallback_turn(state, user_text)
        if local_response is not None:
            return local_response

    if isinstance(agent.model, LiteLlm):
        llm_request.model = agent.model.model
        llm_request.contents = _sanitize_contents_for_ollama(llm_request.contents)
    return None


def _rewrite_function_call_name(
    part: types.Part,
    tool_name: str,
) -> types.Part:
    call = part.function_call
    return types.Part(
        function_call=types.FunctionCall(
            id=call.id,
            name=tool_name,
            args=call.args or {},
        )
    )


async def _after_model(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> LlmResponse | None:
    content = llm_response.content
    if not content or not content.parts:
        return None

    changed = False
    rewritten: list[types.Part] = []
    for part in content.parts:
        if not part.function_call:
            rewritten.append(part)
            continue

        name = part.function_call.name
        if name in VALID_TOOL_NAMES:
            rewritten.append(part)
            continue

        if _should_use_local_llm(callback_context.state):
            if name in {"check_internet", "fetch_online_riddle", "start_riddle"}:
                rewritten.append(_rewrite_function_call_name(part, "get_local_riddle"))
                changed = True
                continue
            alias = "get_local_riddle"
        else:
            if name in {"check_internet", "fetch_online_riddle"}:
                rewritten.append(_rewrite_function_call_name(part, "start_riddle"))
                changed = True
                continue
            alias = HALLUCINATED_TOOL_ALIASES.get(name)
        if alias:
            rewritten.append(_rewrite_function_call_name(part, alias))
            changed = True
            continue

        changed = True

    if not changed:
        return None

    if not any(p.function_call for p in rewritten):
        rewritten.append(
            types.Part.from_text(
                text=(
                    "Use only these tools: start_riddle, check_answer, give_hint, "
                    "reveal_answer, exit_game."
                )
            )
        )

    return llm_response.model_copy(
        update={"content": types.ModelContent(parts=rewritten)}
    )


async def _on_tool_error(
    tool: Any,
    args: dict[str, Any],
    tool_context: ToolContext,
    error: Exception,
) -> dict[str, Any] | None:
    if "not found" not in str(error).lower():
        return None
    return {
        "error": (
            f"Tool '{tool.name}' does not exist. Call one of: "
            f"{', '.join(sorted(VALID_TOOL_NAMES))}."
        )
    }


def _fallback_user_message(error: Exception) -> LlmResponse:
    detail = _cloud_error_summary(error)
    return LlmResponse(
        content=types.ModelContent(
            parts=[
                types.Part.from_text(
                    text=(
                        f"Cloud Gemini failed ({detail}). "
                        "I've switched to local Ollama with offline riddles — "
                        "please send your message again and I'll continue."
                    )
                )
            ]
        ),
    )


async def _on_model_error(
    callback_context: CallbackContext,
    llm_request: Any,
    error: Exception,
) -> LlmResponse | None:
    if not _is_cloud_transient_error(error):
        return None

    inv = callback_context.get_invocation_context()
    agent = inv.agent

    if _is_using_cloud_model(agent.model):
        first_switch = not _should_use_local_llm(callback_context.state)
        _activate_local_fallback(agent, callback_context.state, error=error)
        return _fallback_user_message(error) if first_switch else None

    if isinstance(agent.model, LiteLlm) and "invalid message" in str(error).lower():
        callback_context.state["llm_fallback_active"] = True
        return LlmResponse(
            content=types.ModelContent(
                parts=[
                    types.Part.from_text(
                        text=(
                            "I hit a chat-history issue switching to local Ollama. "
                            "Please send your message one more time."
                        )
                    )
                ]
            )
        )

    return None
