#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
docker compose up -d
echo ""
echo "Grafana:    http://localhost:3001"
echo "Prometheus: http://localhost:9090"
echo ""
echo 'Run agent: AGENT_METRICS_ENABLED=true adk run code_local'
echo "Metrics:   http://127.0.0.1:9464/metrics"
