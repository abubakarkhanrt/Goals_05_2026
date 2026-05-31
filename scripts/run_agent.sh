#!/usr/bin/env bash
# Run transcript agent with local Ollama or cloud Gemini.
# ADK does not support `adk run code --local` — use:
#   ./scripts/run_agent.sh local
#   ./scripts/run_agent.sh cloud
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
MODE="${1:-local}"
shift || true
case "$MODE" in
  local) AGENT=code_local ;;
  cloud) AGENT=code_cloud ;;
  *) echo "Usage: $0 {local|cloud} [adk args...]" >&2; exit 1 ;;
esac
if [[ -x "$ROOT/venv/bin/adk" ]]; then
  exec "$ROOT/venv/bin/adk" run "$AGENT" "$@"
fi
exec adk run "$AGENT" "$@"
