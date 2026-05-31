"""Tests for Ollama assessment JSON schema prompts and parsing."""

from __future__ import annotations

import json
import unittest
from unittest.mock import AsyncMock, patch

from code.ollama_client import (
    OLLAMA_ASSESSOR_INSTRUCTION,
    build_assessor_system_instruction,
    extract_json_object,
    parse_assessment_response,
)
from code.schemas import TranscriptAssessment, assessment_json_schema


class TestAssessmentSchemaPrompt(unittest.TestCase):
    def test_instruction_includes_json_schema(self):
        instruction = build_assessor_system_instruction()
        self.assertIn("legitimacy_score", instruction)
        self.assertIn("explanation_summary", instruction)
        self.assertIn("JSON Schema", instruction)
        self.assertIn('"risk_level"', instruction)

    def test_module_constant_matches_builder(self):
        self.assertEqual(OLLAMA_ASSESSOR_INSTRUCTION, build_assessor_system_instruction())

    def test_schema_matches_pydantic_model(self):
        schema = assessment_json_schema()
        self.assertEqual(schema["title"], "TranscriptAssessment")
        self.assertIn("legitimacy_score", schema["properties"])


class TestAssessmentJsonParsing(unittest.TestCase):
    def test_parse_fenced_json(self):
        raw = """```json
{
  "legitimacy_score": 0.2,
  "risk_level": "High Risk",
  "explanation_summary": "Mismatch detected.",
  "flags": ["Credit sum mismatch"]
}
```"""
        assessment = parse_assessment_response(raw)
        self.assertEqual(assessment.risk_level, "High Risk")
        self.assertEqual(assessment.legitimacy_score, 0.2)

    def test_extract_json_object_from_prose(self):
        raw = 'Here is the result: {"legitimacy_score": 0.5, "risk_level": "Manual Review", "explanation_summary": "x", "flags": []} done'
        cleaned = extract_json_object(raw)
        data = json.loads(cleaned)
        self.assertEqual(data["risk_level"], "Manual Review")


class TestAssessWithOllamaRetry(unittest.IsolatedAsyncioTestCase):
    async def test_retries_on_invalid_json(self):
        from code.ollama_client import assess_with_ollama

        bad = '{"assessment_summary_sum": "incomplete'
        good = json.dumps(
            {
                "legitimacy_score": 0.1,
                "risk_level": "High Risk",
                "explanation_summary": "Fixed.",
                "flags": ["Credit sum mismatch"],
            }
        )

        with patch("code.ollama_client._ollama_chat", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [bad, good]
            result = await assess_with_ollama(
                "code/pdf/x.pdf",
                math_result={"success": False, "flags": ["Credit sum mismatch"]},
                spatial_result={"success": True},
                image_paths=None,
            )

        self.assertEqual(result.risk_level, "High Risk")
        self.assertEqual(mock_llm.call_count, 2)
        self.assertFalse(mock_llm.call_args_list[1].kwargs.get("json_mode") is False)


if __name__ == "__main__":
    unittest.main()
