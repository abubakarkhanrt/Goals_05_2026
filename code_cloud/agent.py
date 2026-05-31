"""ADK entry point — cloud Gemini backend.

Run from project root:
  adk run code_cloud
  adk web          (then select code_cloud)

Requires GOOGLE_API_KEY in code/.env (see code/.env.example).
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "code" / ".env")

import os

os.environ["TRANSCRIPT_LLM_BACKEND"] = "cloud"
os.environ.setdefault("USE_OLLAMA", "false")

from code.agent import root_agent

__all__ = ["root_agent"]
