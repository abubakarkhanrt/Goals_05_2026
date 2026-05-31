"""Ollama-backed risk assessor (ADK Agent + LiteLLM) — optional ADK Agent wrapper."""

from __future__ import annotations

from .llm_config import ollama_api_base, ollama_model, ollama_temperature
from .ollama_client import OLLAMA_ASSESSOR_INSTRUCTION
from .schemas import TranscriptAssessment


def build_ollama_lite_llm():
    from google.adk.models.lite_llm import LiteLlm

    return LiteLlm(
        model=ollama_model(),
        api_base=ollama_api_base(),
        temperature=ollama_temperature(),
    )


def build_ollama_risk_assessor():
    from google.adk import Agent

    return Agent(
        name="ollama_risk_assessor",
        model=build_ollama_lite_llm(),
        instruction=OLLAMA_ASSESSOR_INSTRUCTION,
        output_schema=TranscriptAssessment,
        mode="single_turn",
    )
