"""ADK entry point — local Ollama backend.

Run from project root:
  adk run code_local
  adk web          (then select code_local)
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "code" / ".env")

import os

os.environ["TRANSCRIPT_LLM_BACKEND"] = "local"
os.environ.setdefault("USE_OLLAMA", "true")

from code.agent import root_agent

__all__ = ["root_agent"]
