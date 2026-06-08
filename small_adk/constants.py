"""Shared constants — session keys, patterns, tool names, URLs."""

from __future__ import annotations

import os
import re

RIDDLES_API_URL = os.environ.get(
    "RIDDLES_API_URL", "https://riddles-api.vercel.app/random"
)
INTERNET_PROBE_URL = os.environ.get(
    "INTERNET_PROBE_URL", "https://www.google.com"
)

STATE_QUESTION = "riddle_question"
STATE_ANSWER = "riddle_answer"
STATE_ALIASES = "riddle_aliases"
STATE_HINTS = "riddle_hints"
STATE_HINTS_USED = "riddle_hints_used"
STATE_SOURCE = "riddle_source"
STATE_AWAITING_FINAL = "riddle_awaiting_final"
STATE_PENDING_GUESS = "riddle_pending_guess"
STATE_USED_OFFLINE = "riddle_used_offline_indices"
STATE_OFFLINE_ONLY = "offline_riddles_only"
STATE_EXITED = "riddle_game_exited"
STATE_ACCEPTED_ANSWERS = "riddle_accepted_answers"
STATE_CONNECTIVITY = "connectivity_online"
STATE_CONNECTIVITY_AT = "connectivity_probed_at"

RIDDLE_STATE_KEYS = (
    STATE_QUESTION,
    STATE_ANSWER,
    STATE_ALIASES,
    STATE_HINTS,
    STATE_HINTS_USED,
    STATE_SOURCE,
    STATE_AWAITING_FINAL,
    STATE_PENDING_GUESS,
    STATE_ACCEPTED_ANSWERS,
)

LOCAL_PLAY_RE = re.compile(
    r"(let'?s?\s+play|new\s+riddle|another\s+riddle|start|play)",
    re.IGNORECASE,
)
GIVE_UP_RE = re.compile(r"\b(give\s+up|surrender|i\s+quit)\b", re.IGNORECASE)
HINT_RE = re.compile(r"\bhint\b", re.IGNORECASE)
CONFIRM_RE = re.compile(r"\b(yes|yeah|yep|final|sure|correct)\b", re.IGNORECASE)
NO_RE = re.compile(r"\b(no|nope|nah|not\s+sure|wait)\b", re.IGNORECASE)
EXIT_RE = re.compile(r"^/?(?:exit|quit|stop)(?:\s+game)?\.?$", re.IGNORECASE)

VALID_TOOL_NAMES = frozenset(
    {
        "start_riddle",
        "check_internet",
        "get_local_riddle",
        "fetch_online_riddle",
        "check_answer",
        "give_hint",
        "reveal_answer",
        "exit_game",
    }
)

HALLUCINATED_TOOL_ALIASES = {
    "riddle_agent": "start_riddle",
    "riddle_master": "start_riddle",
}

CONNECTIVITY_CACHE_TTL = float(os.environ.get("CONNECTIVITY_CACHE_TTL", "60"))
