"""Riddle Agent — ADK entry point (workshop file 5 of 5).

Run from the parent directory:
  adk run small_adk
  adk web   → select small_adk
"""

from __future__ import annotations

import os

from google.adk import Agent

from .runtime import (
    _AUTH_NOTE,
    _ACTIVE_MODEL,
    _INTERNET_AT_STARTUP,
    _MODE_LABEL,
    _after_model,
    _before_model,
    _on_model_error,
    _on_tool_error,
    _raw_ollama_mode,
    _workshop_mode,
)
from .tools import (
    check_answer,
    check_internet,
    exit_game,
    fetch_online_riddle,
    get_local_riddle,
    give_hint,
    reveal_answer,
    start_riddle,
)

INSTRUCTION = """You are a friendly Riddle Master for a workshop demo.

## Tools (exact names only)
start_riddle, check_answer, give_hint, reveal_answer, exit_game
(Also: check_internet, get_local_riddle, fetch_online_riddle — prefer start_riddle.)

## Rules
1. New game or "new riddle" → call `start_riddle` once, then present ONLY the question.
2. User guesses → `check_answer`. Correct → congratulate. needs_confirmation → ask final answer.
   Wrong final → encourage; never reveal the answer.
3. "hint" → `give_hint`. "give up" → `reveal_answer`.
4. `/exit`, quit, stop → `exit_game`. Wait for "Let's play" before a new riddle.
5. If `llm_fallback_active` in state → offline riddles only; `start_riddle` handles it.

Keep replies short and fun. Never invent or leak answers — tools hold the secret.
"""

_STARTUP_NOTE = ""
if _AUTH_NOTE:
    _STARTUP_NOTE += f"\nNote: {_AUTH_NOTE}\n"
if _workshop_mode():
    _STARTUP_NOTE += "\nNote: WORKSHOP_MODE=local — Ollama + offline riddles only.\n"
elif _INTERNET_AT_STARTUP is None:
    _STARTUP_NOTE += (
        "\nNote: SKIP_STARTUP_PROBE set — connectivity checked on first riddle.\n"
    )
elif _INTERNET_AT_STARTUP and not os.environ.get("GOOGLE_API_KEY", "").strip():
    if _raw_ollama_mode():
        _STARTUP_NOTE += (
            "\nNote: RAW_OLLAMA_MODE=true — local Ollama will be called once "
            "per turn for wording while Python controls game state.\n"
        )
    else:
        _STARTUP_NOTE += (
            "\nNote: Internet is on but GOOGLE_API_KEY is not set — using the "
            "deterministic offline riddle handler to avoid local tool loops.\n"
        )

_internet_line = (
    "deferred (first riddle)"
    if _INTERNET_AT_STARTUP is None
    else ("yes" if _INTERNET_AT_STARTUP else "no")
)

print(
    f"""Riddle Agent (small_adk) is ready.

Mode: {_MODE_LABEL}
Internet at startup: {_internet_line}
{_STARTUP_NOTE}
Try: "Let's play"  ·  "hint"  ·  "give up"  ·  "/exit"
"""
)

root_agent = Agent(
    name="riddle_master",
    model=_ACTIVE_MODEL,
    instruction=INSTRUCTION,
    before_model_callback=_before_model,
    after_model_callback=_after_model,
    on_model_error_callback=_on_model_error,
    on_tool_error_callback=_on_tool_error,
    tools=[
        start_riddle,
        check_internet,
        get_local_riddle,
        fetch_online_riddle,
        check_answer,
        give_hint,
        reveal_answer,
        exit_game,
    ],
)

__all__ = ["root_agent"]
