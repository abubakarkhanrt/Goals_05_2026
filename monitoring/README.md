# Transcript Agent — Application Profiling & Observability

**New to the stack?** Open **[monitoring/index.html](index.html)** in a browser — a 14-slide walkthrough of how metrics flow from the agent to Grafana.

Prometheus + Grafana stack for the **Transcript Risk Assessor** ADK agent.

## What is measured

| Metric | Type | Purpose |
|--------|------|---------|
| `agent_task_duration_seconds` | Histogram | Latency per workflow task (6 instrumented tasks) |
| `agent_task_total` | Counter | Task invocations by status |
| `agent_task_errors_total` | Counter | Error rate by task and exception type |
| `agent_route_total` | Counter | Input gate routes (`verify`, `qa`, `local`, …) |
| `agent_llm_fallback_total` | Counter | Rules fallback when LLM fails |
| `agent_cache_io_seconds` | Histogram | PDF render / PNG cache file I/O |
| `agent_db_seconds` | Histogram | SQLite: verifications, messages, tool runs, LLM audit |
| `agent_process_cpu_percent` | Gauge | Agent Python process CPU (sampled every 5s) |
| `agent_process_memory_bytes` | Gauge | Agent process RSS |
| `agent_host_cpu_percent` | Gauge | **Whole machine** CPU (sampled every 5s) |
| `agent_host_memory_used_bytes` / `_total_bytes` | Gauge | Host physical memory |

### Instrumented tasks (6)

1. `workflow_input_gate` — routing and slash commands  
2. `render_pdf` — PDF → PNG session cache  
3. `verify_transcript_math` — math tool  
4. `verify_transcript_spatial` — spatial tool  
5. `llm_assess` — LLM assessment (+ `llm_chat` for raw LLM latency)  
6. `session_qa` — follow-up Q&A  

## Quick start

### 1. Enable metrics in the agent

Add to `code/.env` (or export before running):

```env
AGENT_METRICS_ENABLED=true
AGENT_METRICS_PORT=9464
```

### 2. Start Prometheus + Grafana

From this folder:

```powershell
cd D:\RT\Goals\Agent\monitoring
docker compose up -d
```

Or:

```powershell
.\scripts\start-stack.ps1
```

### 3. Run the agent (separate terminal)

```powershell
cd D:\RT\Goals\Agent
.\venv\Scripts\Activate.ps1
$env:AGENT_METRICS_ENABLED = "true"
adk run code_local
# or: adk web  → select code_local
```

### 4. Open dashboards

| UI | URL |
|----|-----|
| **Grafana** | http://localhost:3001 |
| **Prometheus** | http://localhost:9090 |
| **Alertmanager** | http://localhost:9093 |
| **Agent /metrics** | http://127.0.0.1:9464/metrics |

Grafana loads the **Transcript Risk Assessor** dashboard automatically (anonymous admin enabled for local demos).

### 5. Generate traffic

```text
Verify the transcript at code/pdf/sample.pdf
How did you compute 24.0?
/model
```

Watch latency, error counters, and process memory update in Grafana.

## Getting all panels to show data

Some panels stay empty until the right **traffic** or **events** happen. Use this checklist:

### Always (CPU, memory, task rate, latency, routes, cache I/O)

1. **Metrics enabled** before the agent loads (restart `adk web` / `adk run` after setting env):
   ```powershell
   $env:AGENT_METRICS_ENABLED = "true"
   adk web
   ```
2. **Prometheus scraping** — http://localhost:9090/targets → `transcript-agent` should be **UP**.
3. **Generate workload** in ADK web (select `code_local` or `code`):
   ```text
   Verify the transcript at code/pdf/sample.pdf
   Explain the credit sum
   How did you compute 24.0?
   ```
   Run **2–3 verify + 1–2 Q&A** messages so counters and histograms have samples.
4. **Grafana time range** — set to **Last 15 minutes** (dashboard default) and refresh.

### Panels that need specific events

| Panel | Shows zero / flat until… |
|-------|---------------------------|
| **Overall error rate** | A task throws (e.g. bad path). Healthy runs show **0%** — that is correct. |
| **LLM fallback** | Ollama/Gemini fails (stop `ollama serve`, wrong model, timeout). Success = **0 fallbacks**. |
| **Errors by task** | Same as error rate — empty at 0 is normal when healthy. |

### Optional: demo an error and a fallback (for workshop)

```powershell
# Fallback demo — stop Ollama, then verify a PDF in ADK web
Stop-Process -Name ollama -ErrorAction SilentlyContinue
# … run verify in web UI …
# Restart: ollama serve
```

```text
Verify the transcript at code/pdf/does-not-exist.pdf
```

### Verify metrics locally

```powershell
Invoke-WebRequest http://127.0.0.1:9464/metrics -UseBasicParsing | Select-Object -Expand Content | Select-String "agent_task_total|agent_process_memory|agent_host_cpu"
```

You should see `agent_process_memory_bytes`, `agent_host_cpu_percent`, and `agent_task_total` lines after at least one workflow run.

| Panel | Shows zero / flat until… |
|-------|---------------------------|
| **Cache I/O latency** | Time to render PDF pages to PNG in `.session_cache/` (file I/O, separate from DB) |
| **DB time** | SQLite ops when `AGENT_DB_ENABLED=true` — verify (INSERT) and Q&A after restart (SELECT) |
| **Host CPU** | ~10s after agent start (5s sampler); may stay >0 if Ollama/Docker are busy |
| **LLM fallback** | Count of times Ollama/Gemini failed and rules-based scoring/Q&A was used instead |

### Top stat row shows 0 but routes graph shows 1?

Stat panels count **since the agent process started** (Prometheus counters reset when you restart `adk web`). The route **timeseries** uses the same counters — both should match after a dashboard refresh.

If **Cache I/O** or **DB time** is empty, run at least one **PDF verify** (not Q&A-only). Cache tracks `pdf_render`; DB tracks SQLite insert/select on verify and Q&A.

**LLM fallback** at **0** is correct when Ollama/Gemini succeeded — fallbacks are recorded only on failure.

### Process vs host CPU

Both are sampled every **5 seconds** in a background thread (Windows cannot report CPU on a one-off scrape).

| Panel | Metric | What it shows |
|-------|--------|----------------|
| **Process CPU** | `agent_process_cpu_percent` | Agent Python process only |
| **Host CPU (whole machine)** | `agent_host_cpu_percent` | All cores / all processes on the machine |

After restarting the agent, wait ~10s and run a verify — you should see spikes during PDF render and LLM calls. Between requests, **0% process CPU is normal** for an idle Python process; **host CPU** may stay higher if Ollama, Docker, or other apps are busy.

### Process CPU shows 0%

CPU is sampled every **5 seconds** in a background thread (Windows cannot report CPU on a one-off scrape). After restarting the agent, wait ~10s and run a verify — you should see spikes during PDF render and LLM calls. Between requests, **0% is normal** for an idle Python process.

### Cache I/O latency empty?

This panel tracks **`pdf_render`** — how long `ensure_pdf_images()` takes when you **verify a PDF** (not Q&A-only turns). Run:

```text
Verify the transcript at code/pdf/sample.pdf
```

If you only sent Q&A messages, math/spatial/LLM panels update but cache I/O may not (PNG cache already warm).

### LLM fallback count stays at 0?

**That means the LLM succeeded** — fallbacks are recorded only on failure. To demo for a workshop:

```powershell
# Stop Ollama, then in ADK web verify a PDF:
Stop-Process -Name ollama -ErrorAction SilentlyContinue
```

Or set a very short timeout in `code/.env`:

```env
OLLAMA_TIMEOUT_SECONDS=1
```

Then verify a PDF — assessment falls back to rules and `agent_llm_fallback_total` increments. Restart `ollama serve` afterward.

**Note:** Restart Grafana after dashboard updates: `docker compose restart grafana` in `monitoring/`.

## Alerting

Prometheus evaluates two rules (see `prometheus/alerts.yml`):

| Alert | Condition | Severity |
|-------|-----------|----------|
| **AgentMetricsTargetDown** | Scrape target down for 2m | critical |
| **AgentHighTaskErrorRate** | Task errors &gt; 0.01/s for 5m | warning |

View firing alerts: http://localhost:9090/alerts · Alertmanager UI: http://localhost:9093

The default receiver logs only (no email/Slack). Extend `alertmanager/alertmanager.yml` for production notifications.

## Architecture

```
adk run code_local  ──► :9464/metrics (Prometheus client)
                              │
                              ▼
                    Prometheus (:9090) ──► Alertmanager (:9093)
                              │
                              ▼
                     Grafana (:3001)
```

Prometheus scrapes the agent on the **host** via `host.docker.internal:9464` (Docker Desktop on Windows/macOS). On Linux, edit `prometheus/prometheus.yml` to use `172.17.0.1:9464` or your host IP.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_METRICS_ENABLED` | `false` | Start `/metrics` HTTP server when agent loads |
| `AGENT_METRICS_PORT` | `9464` | Metrics listen port |
| `AGENT_DB_ENABLED` | `true` | Persist verification history to SQLite (Option 2) |
| `AGENT_DB_PATH` | `code/.data/transcript_agent.db` | SQLite file path |

Instrumentation lives in `code/observability/metrics.py` and is wired into `code/agent.py` and `code/llm_shared.py`.

## Stop the stack

```powershell
docker compose down
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Prometheus target **DOWN** | Ensure agent is running with `AGENT_METRICS_ENABLED=true` |
| Empty Grafana panels | Run at least one verify/Q&A turn; check http://127.0.0.1:9464/metrics |
| **"Unauthorized" toast on refresh** | Harmless Grafana 11.2.0 bug with anonymous login (`/api/user/preferences` → 401). Fixed in **11.3.0+** (this stack uses 11.3.0). Run `docker compose pull && docker compose up -d` in `monitoring/` |
| `host.docker.internal` fails on Linux | Change scrape target in `prometheus/prometheus.yml` |
| Port in use | Grafana defaults to **3001** (3000 is often used by Open WebUI). Change ports in `docker-compose.yml` if needed |

## Org goal mapping

This folder satisfies **Application Profiling & Observability Implementation**:

- **Grafana** dashboards for one core service (transcript agent)  
- **4–6 key tasks** instrumented (6 workflow tasks)  
- **CPU / memory** — process (`agent_process_*`) **and host** (`agent_host_cpu_percent`, `agent_host_memory_*`)  
- **Latency** via `agent_task_duration_seconds`  
- **DB time** via `agent_db_seconds` (SQLite verification persistence — Option 2)  
- **Error rates** via `agent_task_errors_total` (+ LLM fallback counter)
