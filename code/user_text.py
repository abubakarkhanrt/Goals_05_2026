"""Extract plain text from ADK user content / workflow node input."""

from __future__ import annotations

from typing import Any


def extract_user_text(user_content: Any, node_input: Any = None) -> str:
    """Normalize user message text from Context.user_content or node_input."""
    if user_content is None and node_input is not None:
        user_content = node_input

    if user_content is None:
        return ""

    if isinstance(user_content, str):
        return user_content.strip()

    if hasattr(user_content, "parts") and user_content.parts:
        parts_text: list[str] = []
        for part in user_content.parts:
            if isinstance(part, dict):
                chunk = part.get("text", "") or ""
            elif hasattr(part, "model_dump"):
                dumped = part.model_dump() or {}
                chunk = dumped.get("text", "") if isinstance(dumped, dict) else dumped
            else:
                chunk = getattr(part, "text", "") or ""
            parts_text.append(str(chunk))
        return "".join(parts_text).strip()

    if hasattr(user_content, "model_dump_json"):
        try:
            return user_content.model_dump_json()
        except Exception:
            return str(user_content)

    return str(user_content).strip()
