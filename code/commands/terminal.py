"""Terminal formatting helpers (color when supported)."""

from __future__ import annotations

import os
import sys


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


class Terminal:
    def __init__(self) -> None:
        self._color = _supports_color()

    def _c(self, code: str, text: str) -> str:
        if not self._color:
            return text
        return f"\033[{code}m{text}\033[0m"

    def heading(self, text: str) -> str:
        return self._c("1;36", text)

    def success(self, text: str) -> str:
        return self._c("32", text)

    def warning(self, text: str) -> str:
        return self._c("33", text)

    def error(self, text: str) -> str:
        return self._c("31", text)

    def muted(self, text: str) -> str:
        return self._c("90", text)

    def table(self, headers: list[str], rows: list[list[str]]) -> str:
        if not rows:
            return self.muted("(empty)")
        widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(cell))
        fmt = "  ".join(f"{{:{w}}}" for w in widths)
        lines = [fmt.format(*headers)]
        lines.append(fmt.format(*["-" * w for w in widths]))
        for row in rows:
            lines.append(fmt.format(*row))
        return "\n".join(lines)
