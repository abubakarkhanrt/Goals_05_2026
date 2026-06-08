"""ADK FunctionTools for the riddle game.

Workshop file 3 of 5: tools the LlmAgent calls during play.
"""

from __future__ import annotations

import json
import time
import urllib.error
from typing import Any

from google.adk.tools.tool_context import ToolContext

from .constants import (
    CONNECTIVITY_CACHE_TTL,
    STATE_CONNECTIVITY,
    STATE_CONNECTIVITY_AT,
)
from .game import (
    _apply_exit_state,
    _evaluate_guess,
    _fetch_api_riddle,
    _generate_riddle_via_llm,
    _load_local_riddle,
    _next_hint,
    _reveal_answer,
    _store_riddle,
)
from .runtime import _MODE_LABEL, _probe_internet, _should_use_local_llm


def _cached_online(state: dict[str, Any], *, force: bool = False) -> bool:
    """Probe internet at most once per session TTL (default 60s)."""
    if not force:
        probed_at = state.get(STATE_CONNECTIVITY_AT)
        if probed_at is not None:
            age = time.time() - float(probed_at)
            if age < CONNECTIVITY_CACHE_TTL:
                return bool(state.get(STATE_CONNECTIVITY))

    online = _probe_internet()
    state[STATE_CONNECTIVITY] = online
    state[STATE_CONNECTIVITY_AT] = time.time()
    return online


def check_internet(tool_context: ToolContext) -> dict[str, Any]:
    """Check whether the internet is reachable. Call before fetching a riddle."""
    if _should_use_local_llm(tool_context.state):
        return {
            "online": False,
            "offline_only": True,
            "message": "Local fallback mode — use get_local_riddle.",
        }
    online = _cached_online(tool_context.state)
    return {
        "online": online,
        "llm_mode": _MODE_LABEL,
        "message": (
            "Internet is available — online riddles are enabled."
            if online
            else "Internet is unavailable — using offline riddles."
        ),
    }


def get_local_riddle(tool_context: ToolContext) -> dict[str, Any]:
    """Pick a random offline riddle with pre-stored hints. Use when internet is off."""
    data = _load_local_riddle(tool_context.state)
    return {
        **data,
        "message": "Offline riddle loaded. Do not reveal the answer.",
    }


def fetch_online_riddle(tool_context: ToolContext) -> dict[str, Any]:
    """Fetch a riddle from the internet (answer stored secretly). Falls back to LLM generation."""
    if _should_use_local_llm(tool_context.state):
        return get_local_riddle(tool_context)
    if not _cached_online(tool_context.state):
        return {
            "error": "No internet. Call get_local_riddle instead.",
            "online": False,
        }

    source = "api"
    try:
        data = _fetch_api_riddle()
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        try:
            data = _generate_riddle_via_llm()
            source = "generated"
        except Exception as exc:
            return {"error": f"Could not fetch or generate an online riddle: {exc}"}

    _store_riddle(
        tool_context.state,
        question=data["question"],
        answer=data["answer"],
        aliases=data.get("aliases", []),
        hints=[],
        source=source,
    )
    return {
        "question": data["question"],
        "source": source,
        "hints_available": 0,
        "message": "Online riddle loaded. Answer is stored server-side — never reveal it yet.",
    }


def start_riddle(tool_context: ToolContext) -> dict[str, Any]:
    """Probe connectivity and load a riddle in one step (online or offline)."""
    if _should_use_local_llm(tool_context.state):
        return get_local_riddle(tool_context)
    if _cached_online(tool_context.state):
        return fetch_online_riddle(tool_context)
    return get_local_riddle(tool_context)


def check_answer(
    guess: str,
    is_final: bool = False,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Check the user's guess against the stored answer. Never returns the correct answer."""
    if tool_context is None:
        return {"error": "Session context missing."}
    return _evaluate_guess(tool_context.state, guess, is_final=is_final)


def give_hint(tool_context: ToolContext) -> dict[str, Any]:
    """Return the next hint for the active riddle. Never reveals the answer."""
    return _next_hint(tool_context.state)


def reveal_answer(tool_context: ToolContext) -> dict[str, Any]:
    """Reveal the answer only when the user explicitly gives up."""
    return _reveal_answer(tool_context.state)


def exit_game(tool_context: ToolContext) -> dict[str, Any]:
    """End the current riddle game. Also triggered by /exit, quit, or stop."""
    _apply_exit_state(tool_context.state)
    return {
        "exited": True,
        "message": (
            "Game ended. Thank the player and tell them they can say "
            "\"Let's play\" to start again or type /exit anytime."
        ),
    }
