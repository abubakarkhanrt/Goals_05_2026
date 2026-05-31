"""Tests for Prometheus instrumentation (no live metrics server required)."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from code.observability.metrics import (
    metrics_enabled,
    metrics_port,
    record_llm_fallback,
    record_route,
    track_task,
)


class TestMetricsConfig(unittest.TestCase):
    def test_disabled_by_default(self):
        with patch.dict(os.environ, {"AGENT_METRICS_ENABLED": ""}, clear=False):
            self.assertFalse(metrics_enabled())

    def test_enabled_when_set(self):
        with patch.dict(os.environ, {"AGENT_METRICS_ENABLED": "true"}, clear=False):
            self.assertTrue(metrics_enabled())

    def test_metrics_port_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AGENT_METRICS_PORT", None)
            self.assertEqual(metrics_port(), 9464)


class TestTrackTask(unittest.TestCase):
    def test_track_task_noop_when_disabled(self):
        with patch.dict(os.environ, {"AGENT_METRICS_ENABLED": "false"}, clear=False):
            with track_task("test_task"):
                pass

    def test_track_task_records_when_enabled(self):
        with patch.dict(os.environ, {"AGENT_METRICS_ENABLED": "true"}, clear=False):
            from code.observability import metrics as m

            m._ensure_metrics()
            before = m.TASK_TOTAL.labels(task="unit_test", status="success")._value.get()
            with track_task("unit_test"):
                pass
            after = m.TASK_TOTAL.labels(task="unit_test", status="success")._value.get()
            self.assertEqual(after, before + 1)

    def test_record_route_when_enabled(self):
        with patch.dict(os.environ, {"AGENT_METRICS_ENABLED": "true"}, clear=False):
            from code.observability import metrics as m

            m._ensure_metrics()
            before = m.ROUTE_TOTAL.labels(route="verify")._value.get()
            record_route("verify")
            after = m.ROUTE_TOTAL.labels(route="verify")._value.get()
            self.assertEqual(after, before + 1)

    def test_record_llm_fallback_when_enabled(self):
        with patch.dict(os.environ, {"AGENT_METRICS_ENABLED": "true"}, clear=False):
            from code.observability import metrics as m

            m._ensure_metrics()
            before = m.LLM_FALLBACK_TOTAL.labels(operation="assess", reason="TimeoutError")._value.get()
            record_llm_fallback("assess", "TimeoutError")
            after = m.LLM_FALLBACK_TOTAL.labels(operation="assess", reason="TimeoutError")._value.get()
            self.assertEqual(after, before + 1)

    def test_host_and_process_gauges_registered(self):
        with patch.dict(os.environ, {"AGENT_METRICS_ENABLED": "true"}, clear=False):
            from code.observability import metrics as m

            m._ensure_metrics()
            self.assertIsNotNone(m.PROCESS_CPU)
            self.assertIsNotNone(m.HOST_CPU)
            self.assertIsNotNone(m.HOST_MEMORY_USED)
            self.assertIsNotNone(m.HOST_MEMORY_TOTAL)
            self.assertIsNotNone(m.DB_DURATION)


if __name__ == "__main__":
    unittest.main()
