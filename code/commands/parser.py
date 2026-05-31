"""Parse slash-command input into command name, args, and flags."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParsedCommand:
    name: str
    args: list[str] = field(default_factory=list)
    flags: dict[str, str | bool] = field(default_factory=dict)
    raw: str = ""


_SLASH_RE = re.compile(r"^\s*/")


def is_slash_command(text: str) -> bool:
    return bool(text and _SLASH_RE.match(text))


def parse_slash_command(text: str) -> ParsedCommand | None:
    """
    Parse `/command arg1 --flag value`.

    Returns None if the line is not a slash command.
  """
    stripped = text.strip()
    if not is_slash_command(stripped):
        return None

    body = stripped.lstrip("/").strip()
    if not body:
        return ParsedCommand(name="", args=[], flags={}, raw=stripped)

    try:
        tokens = shlex.split(body, posix=True)
    except ValueError:
        tokens = body.split()

    if not tokens:
        return ParsedCommand(name="", args=[], flags={}, raw=stripped)

    name = tokens[0].lower()
    args: list[str] = []
    flags: dict[str, str | bool] = {}
    i = 1
    while i < len(tokens):
        tok = tokens[i]
        if tok.startswith("--"):
            key = tok[2:].replace("-", "_")
            if "=" in key:
                k, _, v = key.partition("=")
                flags[k] = v
            elif i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                flags[key] = tokens[i + 1]
                i += 1
            else:
                flags[key] = True
        else:
            args.append(tok)
        i += 1

    return ParsedCommand(name=name, args=args, flags=flags, raw=stripped)
