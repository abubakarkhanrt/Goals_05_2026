"""Base command interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..runtime.context import CommandContext
    from .parser import ParsedCommand


class BaseCommand(ABC):
    name: str
    description: str
    aliases: tuple[str, ...] = ()
    usage: str = ""

    @abstractmethod
    async def execute(self, context: CommandContext, parsed: ParsedCommand) -> str:
        """Run the command and return text shown to the developer."""

    @property
    def autocomplete_meta(self) -> dict[str, str]:
        return {
            "name": self.name,
            "description": self.description,
            "usage": self.usage or f"/{self.name}",
        }
