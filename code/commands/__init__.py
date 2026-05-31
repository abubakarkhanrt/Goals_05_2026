"""Local slash-command framework for ADK runtime introspection."""

from .dispatcher import CommandDispatcher
from .parser import ParsedCommand, parse_slash_command
from .registry import CommandRegistry, build_default_registry

__all__ = [
    "CommandDispatcher",
    "CommandRegistry",
    "ParsedCommand",
    "build_default_registry",
    "parse_slash_command",
]
