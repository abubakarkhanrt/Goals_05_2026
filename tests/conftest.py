"""Pytest defaults: use rule-based assessment unless a test overrides USE_OLLAMA."""

import os

os.environ.setdefault("USE_OLLAMA", "false")
os.environ.setdefault("AGENT_DB_ENABLED", "false")
os.environ.setdefault("AGENT_METRICS_ENABLED", "false")
