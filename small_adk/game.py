"""Riddle game — session state and game flow.

Workshop file 2 of 5: guess/hint/exit logic, local-fallback handler.
"""

from __future__ import annotations

import json
import logging
import random
import re
import urllib.request
from typing import Any

from google.adk.models.llm_response import LlmResponse
from google.genai import types

from .constants import (
    CONFIRM_RE,
    EXIT_RE,
    GIVE_UP_RE,
    HINT_RE,
    LOCAL_PLAY_RE,
    NO_RE,
    RIDDLES_API_URL,
    RIDDLE_STATE_KEYS,
    STATE_ACCEPTED_ANSWERS,
    STATE_ALIASES,
    STATE_ANSWER,
    STATE_AWAITING_FINAL,
    STATE_EXITED,
    STATE_HINTS,
    STATE_HINTS_USED,
    STATE_PENDING_GUESS,
    STATE_QUESTION,
    STATE_SOURCE,
    STATE_USED_OFFLINE,
)
from .riddles import OFFLINE_RIDDLES
from .runtime import (
    _LITELLM_MODEL,
    _activate_local_fallback,
    _content_to_text_summary,
    _is_cloud_transient_error,
    _llm_temperature,
    _should_use_local_llm,
)

logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    for prefix in ("a ", "an ", "the "):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    return text.strip()


def _build_accepted_answers(answer: str, aliases: list[str] | None) -> set[str]:
    answers = {_normalize(answer)}
    for alias in aliases or []:
        if alias:
            answers.add(_normalize(str(alias)))
    answers.discard("")
    return answers


def _accepted_answers(state: dict[str, Any]) -> set[str]:
    cached = state.get(STATE_ACCEPTED_ANSWERS)
    if cached is not None:
        return set(cached)
    answers = _build_accepted_answers(
        str(state.get(STATE_ANSWER, "")),
        state.get(STATE_ALIASES, []) or [],
    )
    state[STATE_ACCEPTED_ANSWERS] = list(answers)
    return answers


def _has_active_riddle(state: dict[str, Any]) -> bool:
    return bool(state.get(STATE_QUESTION) and state.get(STATE_ANSWER))


def _last_user_text(contents: list[types.Content]) -> str:
    for content in reversed(contents):
        if content.role != "user":
            continue
        text = _content_to_text_summary(content)
        if text:
            return text.strip()
    return ""


def _text_response(text: str) -> LlmResponse:
    return LlmResponse(
        content=types.ModelContent(parts=[types.Part.from_text(text=text)])
    )


def _is_exit_command(user_text: str) -> bool:
    return bool(EXIT_RE.match(user_text.strip()))


# ADK session State has no .pop() — clear keys to empty values instead.
_RIDDLE_STATE_CLEAR: dict[str, Any] = {
    STATE_QUESTION: "",
    STATE_ANSWER: "",
    STATE_ALIASES: [],
    STATE_HINTS: [],
    STATE_HINTS_USED: 0,
    STATE_SOURCE: "",
    STATE_AWAITING_FINAL: False,
    STATE_PENDING_GUESS: "",
    STATE_ACCEPTED_ANSWERS: [],
}


def _apply_exit_state(state: Any) -> None:
    for key in RIDDLE_STATE_KEYS:
        if key in _RIDDLE_STATE_CLEAR:
            state[key] = _RIDDLE_STATE_CLEAR[key]
    state[STATE_EXITED] = True


def _exit_game_response(state: dict[str, Any]) -> LlmResponse:
    _apply_exit_state(state)
    return _text_response(
        "Thanks for playing! You're out of the game.\n\n"
        'Say "Let\'s play" to start a new round, or type /exit anytime.'
    )


def _handle_exit_command(
    state: dict[str, Any],
    user_text: str,
) -> LlmResponse | None:
    if _is_exit_command(user_text):
        if state.get(STATE_EXITED) and not _has_active_riddle(state):
            return _text_response(
                'You are not in a game right now. Say "Let\'s play" to start.'
            )
        return _exit_game_response(state)

    if state.get(STATE_EXITED):
        if LOCAL_PLAY_RE.search(user_text):
            state[STATE_EXITED] = False
            return None
        return _text_response(
            'You left the game. Say "Let\'s play" to start again, or /exit anytime.'
        )
    return None


def _local_riddle_intro(question: str, *, switched: bool = False) -> str:
    prefix = (
        "Cloud Gemini was busy — I'm on local Ollama with offline riddles.\n\n"
        if switched
        else ""
    )
    return (
        f"{prefix}Here's your riddle:\n\n{question}\n\n"
        "Take a guess, ask for a hint, say give up, or type /exit to leave."
    )


def _store_riddle(
    state: dict[str, Any],
    *,
    question: str,
    answer: str,
    aliases: list[str] | None = None,
    hints: list[str] | None = None,
    source: str,
) -> None:
    state[STATE_QUESTION] = question.strip()
    state[STATE_ANSWER] = answer.strip()
    state[STATE_ALIASES] = aliases or []
    state[STATE_HINTS] = hints or []
    state[STATE_HINTS_USED] = 0
    state[STATE_SOURCE] = source
    state[STATE_AWAITING_FINAL] = False
    state[STATE_PENDING_GUESS] = ""
    state[STATE_ACCEPTED_ANSWERS] = list(
        _build_accepted_answers(answer, aliases)
    )


def _load_local_riddle(state: dict[str, Any]) -> dict[str, Any]:
    used = set(state.get(STATE_USED_OFFLINE, []) or [])
    available = [i for i in range(len(OFFLINE_RIDDLES)) if i not in used]
    if not available:
        used.clear()
        available = list(range(len(OFFLINE_RIDDLES)))
    idx = random.choice(available)
    used.add(idx)
    state[STATE_USED_OFFLINE] = list(used)

    entry = OFFLINE_RIDDLES[idx]
    _store_riddle(
        state,
        question=entry["question"],
        answer=entry["answer"],
        aliases=entry.get("aliases", []),
        hints=entry.get("hints", []),
        source="offline",
    )
    return {
        "question": entry["question"],
        "source": "offline",
        "hints_available": len(entry.get("hints", [])),
    }


def _evaluate_guess(
    state: dict[str, Any],
    guess: str,
    *,
    is_final: bool = False,
) -> dict[str, Any]:
    """Check a guess against session state. Never returns the correct answer."""
    if not _has_active_riddle(state):
        return {"error": "No active riddle. Fetch a riddle first."}

    normalized_guess = _normalize(guess)
    if not normalized_guess:
        return {"error": "Guess is empty."}

    if normalized_guess in _accepted_answers(state):
        state[STATE_AWAITING_FINAL] = False
        state[STATE_PENDING_GUESS] = ""
        return {
            "correct": True,
            "message": "Correct answer — congratulate the player immediately.",
        }

    pending = _normalize(str(state.get(STATE_PENDING_GUESS) or ""))
    confirming_prior = bool(
        state.get(STATE_AWAITING_FINAL)
        and pending
        and (is_final or normalized_guess == pending)
    )

    if is_final or confirming_prior:
        state[STATE_AWAITING_FINAL] = False
        state[STATE_PENDING_GUESS] = ""
        return {
            "correct": False,
            "final": True,
            "message": (
                "Wrong final answer. Encourage another try, offer a hint, "
                "or wait for the user to say 'give up' before revealing."
            ),
        }

    state[STATE_AWAITING_FINAL] = True
    state[STATE_PENDING_GUESS] = normalized_guess
    return {
        "correct": False,
        "needs_confirmation": True,
        "message": "Ask the user: Are you sure? Is that your final answer?",
    }


def _next_hint(state: dict[str, Any]) -> dict[str, Any]:
    if not _has_active_riddle(state):
        return {"error": "No active riddle. Fetch a riddle first."}

    hints: list[str] = list(state.get(STATE_HINTS) or [])
    used = int(state.get(STATE_HINTS_USED) or 0)
    source = state.get(STATE_SOURCE, "unknown")

    if used >= 3:
        return {
            "hint": None,
            "hints_remaining": 0,
            "message": "No more hints. Keep guessing or say 'give up'.",
        }

    if used < len(hints):
        hint_text = hints[used]
    elif _should_use_local_llm(state):
        fallback_hints = [
            "Read the riddle again — each word is a clue.",
            "Think literally about what the riddle describes.",
            "Say give up if you'd like the answer revealed.",
        ]
        hint_text = fallback_hints[min(used - len(hints), len(fallback_hints) - 1)]
    else:
        try:
            hint_text = _generate_hint_via_llm(
                state[STATE_QUESTION],
                state[STATE_ANSWER],
                used + 1,
            )
        except Exception as exc:
            return {"error": f"Could not generate hint: {exc}"}

    state[STATE_HINTS_USED] = used + 1
    remaining = max(0, 3 - (used + 1))
    return {
        "hint": hint_text,
        "hints_remaining": remaining,
        "source": source,
        "message": "Share this hint only — do not reveal the answer.",
    }


def _reveal_answer(state: dict[str, Any]) -> dict[str, Any]:
    if not _has_active_riddle(state):
        return {"error": "No active riddle to reveal."}

    answer = state[STATE_ANSWER]
    question = state[STATE_QUESTION]
    state[STATE_AWAITING_FINAL] = False
    state[STATE_PENDING_GUESS] = ""
    return {
        "revealed": True,
        "question": question,
        "answer": answer,
        "message": (
            "The user gave up. Reveal the answer, explain briefly, "
            "and offer a new riddle."
        ),
    }


def _handle_local_fallback_turn(
    state: dict[str, Any],
    user_text: str,
) -> LlmResponse | None:
    """Run the riddle game deterministically — no Ollama tool-calling loop."""
    switched = bool(state.get("llm_fallback_active"))
    user_text = user_text.strip()

    if LOCAL_PLAY_RE.search(user_text) or (
        not _has_active_riddle(state) and not state.get(STATE_EXITED)
    ):
        state[STATE_EXITED] = False
        data = _load_local_riddle(state)
        return _text_response(_local_riddle_intro(data["question"], switched=switched))

    if not user_text:
        return _text_response(
            f"Your riddle:\n\n{state[STATE_QUESTION]}\n\n"
            "Take a guess, ask for a hint, say give up, or type /exit to leave."
        )

    if GIVE_UP_RE.search(user_text):
        result = _reveal_answer(state)
        return _text_response(
            f"No worries! The answer was **{result['answer']}**.\n\n"
            f"Riddle: {result['question']}\n\n"
            'Want another? Say "new riddle".'
        )

    if HINT_RE.search(user_text):
        result = _next_hint(state)
        if result.get("hint"):
            remaining = result.get("hints_remaining", 0)
            return _text_response(
                f"Hint: {result['hint']}"
                + (f" ({remaining} hint(s) left)" if remaining else "")
            )
        return _text_response(result.get("message", "No more hints available."))

    if state.get(STATE_AWAITING_FINAL):
        if CONFIRM_RE.search(user_text):
            pending = str(state.get(STATE_PENDING_GUESS) or user_text)
            result = _evaluate_guess(state, pending, is_final=True)
        elif NO_RE.search(user_text):
            state[STATE_AWAITING_FINAL] = False
            state[STATE_PENDING_GUESS] = ""
            return _text_response("No problem — keep guessing!")
        else:
            result = _evaluate_guess(state, user_text)
    else:
        result = _evaluate_guess(state, user_text)

    if result.get("correct"):
        return _text_response(
            "Correct! Well done!\n\nSay \"new riddle\" if you'd like another."
        )
    if result.get("needs_confirmation"):
        return _text_response("Are you sure? Is that your final answer?")
    if result.get("final"):
        return _text_response(
            "Not quite! Keep trying, ask for a hint, or say \"give up\"."
        )
    if result.get("error"):
        return _text_response(result["error"])
    return None


def _llm_complete(prompt: str) -> str:
    import litellm

    def _call() -> str:
        resp = litellm.completion(
            model=_LITELLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=_llm_temperature(),
        )
        content = resp.choices[0].message.content
        return (content or "").strip()

    try:
        return _call()
    except Exception as exc:
        if _is_cloud_transient_error(exc) and _LITELLM_MODEL.startswith("gemini/"):
            _activate_local_fallback(error=exc)
            return _call()
        raise


def _llm_json(prompt: str) -> dict[str, Any]:
    raw = _llm_complete(prompt + "\n\nRespond with valid JSON only.")
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def _generate_riddle_via_llm() -> dict[str, str]:
    data = _llm_json(
        "Create one original short riddle suitable for a workshop demo. "
        'Return JSON: {"question": "...", "answer": "...", "aliases": ["..."]}'
    )
    return {
        "question": str(data.get("question", "")).strip(),
        "answer": str(data.get("answer", "")).strip(),
        "aliases": [str(a) for a in data.get("aliases", []) if a],
    }


def _generate_hint_via_llm(question: str, answer: str, hint_number: int) -> str:
    return _llm_complete(
        f"You are helping with a riddle game. Riddle: {question}\n"
        f"Correct answer (SECRET — do not reveal): {answer}\n"
        f"Give hint #{hint_number} of 3. The hint must NOT contain the answer "
        f"or any alias. One or two sentences only."
    )


def _fetch_api_riddle() -> dict[str, str]:
    req = urllib.request.Request(
        RIDDLES_API_URL,
        headers={"User-Agent": "small-adk-riddle-agent/1.0"},
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    question = str(payload.get("riddle") or payload.get("question") or "").strip()
    answer = str(payload.get("answer") or "").strip()
    if not question or not answer:
        raise ValueError("Riddle API response missing question or answer")
    return {"question": question, "answer": answer, "aliases": []}
