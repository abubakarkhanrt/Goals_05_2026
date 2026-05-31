"""
Output schema for the transcript verification agent.
Enforces a standardized, machine-readable JSON assessment.
"""

from typing import Literal

from pydantic import BaseModel, Field


class TranscriptAssessment(BaseModel):
    """Structured assessment returned by the Risk Assessor agent."""

    legitimacy_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Numeric score from 0 (not legitimate) to 1 (fully legitimate).",
    )
    risk_level: Literal["Auto-Approve", "Manual Review", "High Risk"] = Field(
        ...,
        description="Category for downstream workflow routing.",
    )
    explanation_summary: str | None = Field(
        default=None,
        description="Evidence-based summary of why this risk level was assigned.",
    )
    flags: list[str] = Field(
        default_factory=list,
        description="List of evidentiary flags (e.g. GPA mismatch, alignment anomaly).",
    )


def assessment_json_schema() -> dict:
    """JSON Schema for LLM structured output prompts."""
    return TranscriptAssessment.model_json_schema()


def assessment_example() -> dict[str, object]:
    """Minimal example object (structure only; not real evidence)."""
    return {
        "legitimacy_score": 0.35,
        "risk_level": "Manual Review",
        "explanation_summary": (
            "Credit sum mismatch (computed 24.0 vs stated 7.0). "
            "Grade column alignment spans beyond tolerance."
        ),
        "flags": ["Credit sum mismatch", "Grade column misalignment"],
    }
