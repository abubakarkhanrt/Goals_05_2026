"""Command registry and default command set."""

from __future__ import annotations

from typing import Iterable

from .base import BaseCommand
from .handlers import build_all_handlers


class CommandRegistry:
    def __init__(self, commands: Iterable[BaseCommand] | None = None) -> None:
        self._commands: dict[str, BaseCommand] = {}
        if commands:
            for cmd in commands:
                self.register(cmd)

    def register(self, command: BaseCommand) -> None:
        self._commands[command.name] = command
        for alias in command.aliases:
            self._commands[alias] = command

    def get(self, name: str) -> BaseCommand | None:
        return self._commands.get(name.lower())

    def names(self) -> list[str]:
        seen: set[str] = set()
        primary: list[str] = []
        for cmd in self._commands.values():
            if cmd.name in seen:
                continue
            seen.add(cmd.name)
            primary.append(cmd.name)
        return sorted(primary)

    def all_commands(self) -> list[BaseCommand]:
        seen: set[int] = set()
        out: list[BaseCommand] = []
        for cmd in self._commands.values():
            if id(cmd) in seen:
                continue
            seen.add(id(cmd))
            out.append(cmd)
        return sorted(out, key=lambda c: c.name)

    def autocomplete_catalog(self) -> list[dict[str, str]]:
        return [c.autocomplete_meta for c in self.all_commands()]


def build_default_registry() -> CommandRegistry:
    return CommandRegistry(build_all_handlers())
