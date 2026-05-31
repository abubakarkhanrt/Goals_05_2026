# Team Quick Start — Transcript Risk Assessor

One-page guide to run, demo, and troubleshoot the ADK agent. Full details: [`code/README.md`](code/README.md) · Workshop deck: [`index.html`](index.html) · Observability: [`monitoring/README.md`](monitoring/README.md).

## Prerequisites

| Item | Local (`code_local`) | Cloud (`code_cloud`) |
|------|----------------------|----------------------|
| Python 3.11+ venv | Required | Required |
| `pip install -r code/requirements.txt` | Required | Required |
| Ollama + `gemma4:26b` | Required | Optional |
| `GOOGLE_API_KEY` in `code/.env` | Not needed | Required |
| Docker Desktop | For Grafana only | For Grafana only |

```powershell
cd D:\RT\Goals\Agent
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r code\requirements.txt
copy code\.env.example code\.env
ollama serve    # separate terminal
ollama pull gemma4:26b
```

## Choose your entry point

| Command | Backend | When to use |
|---------|---------|-------------|
| `adk run code_local` | Ollama | Dev, privacy-sensitive PDFs, offline |
| `adk run code_cloud` | Gemini | No local GPU; needs API key |
| `adk web` → select `code_local` or `code_cloud` | Either | Workshop demo, PDF **file attach** |

Wrapper script: `.\scripts\run_agent.ps1 -Mode local` or `-Mode cloud -Web`.

## 15-minute demo script

1. **Start observability** (optional but recommended for Goal 3):
   ```powershell
   cd monitoring
   docker compose up -d
   ```
   Open http://localhost:3001 (Grafana).

2. **Start agent with metrics + DB** — add to `code/.env`:
   ```env
   AGENT_METRICS_ENABLED=true
   AGENT_DB_ENABLED=true
   ```
   Then restart: `adk web` → pick **code_local**.

3. **Verify a transcript** (either method):
   - **Path in text:** `Verify the transcript at code/pdf/sample.pdf`
   - **ADK web attach:** upload `code/pdf/sample.pdf`, then type `Verify this transcript`

4. **Follow-up Q&A:** `How did you compute 24.0?`

5. **Operator commands:** `/model` · `/tools` · `/agents` · `/history` · `/assessments` · `/audit`

6. **Grafana:** refresh dashboard — latency, CPU, DB time, error rate after verify.

7. **Workshop deck:** open `index.html` in a browser (arrow keys / Space to navigate).

## Environment flags (copy from `code/.env.example`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `AGENT_METRICS_ENABLED` | `false` | Expose `:9464/metrics` for Prometheus |
| `AGENT_METRICS_PORT` | `9464` | Metrics port |
| `AGENT_DB_ENABLED` | `true` | SQLite: messages, verifications, tool/LLM audit |
| `AGENT_DB_PATH` | `code/.data/transcript_agent.db` | DB file (gitignored) |
| `USE_OLLAMA` | `true` | `false` = rules-only scoring, no LLM |

## Slash commands (project-scoped)

`/help` · `/tools` · `/agents` · `/model` · `/config` · `/session` · `/history` · `/assessments` · `/audit` · `/clear` · `/reload` · `/debug on|off` · `/exit`

See [`code/SLASH_COMMANDS.md`](code/SLASH_COMMANDS.md).

## Troubleshooting (fast)

| Symptom | Fix |
|---------|-----|
| Grafana panels empty | Set `AGENT_METRICS_ENABLED=true`, restart agent, run one verify |
| Prometheus target DOWN | Agent not running or metrics disabled |
| “Verify” with attached PDF fails | Use `adk web` (not CLI-only); message must mention verify |
| Ollama hang / timeout | Check `ollama serve`; lower `OLLAMA_IMAGE_MAX_EDGE`; increase `OLLAMA_TIMEOUT_SECONDS` |
| Invalid JSON → rules fallback | Normal for some Ollama models; check `/audit` for LLM call status |
| `/exit` in web UI | Ends turn only; close tab to leave web UI |
| **`code-local` errors in ADK web** | Old folder name — stop `adk web`, run `.\scripts\cleanup_stale_agents.ps1`, restart, select **`code_local`** |
| Tests | `python -m pytest tests/ -q` (97 tests, no live Ollama) |

## Repo map

```
Agent/
  TEAM_QUICK_START.md     ← this file
  index.html              ← internal workshop deck
  code/agent.py           ← ADK Workflow
  code_local/ code_cloud/ ← ADK entry points
  monitoring/             ← Prometheus + Grafana + alerts
  tests/                  ← pytest suite
```
