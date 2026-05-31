# Transcript Verification Agent (Code)

**New to the project?** Start with [`../TEAM_QUICK_START.md`](../TEAM_QUICK_START.md) (15-minute demo script, env flags, troubleshooting).

ADK **Workflow** agent that assesses academic transcript PDFs using a **dual-path pipeline**:

1. **PDF path** — deterministic Python tools parse the `.pdf` file (no cloud API).
2. **PNG path** — page renders in `.session_cache/` for the **local Ollama** or **cloud Gemini** vision model.
3. **Assessment** — LLM reads **PNGs + tool JSON**, or **rule-based** scoring when LLM is off/unavailable.

Follow-up **session Q&A** reuses cached PNGs and tool results without re-running full assessment.

## Requirements

- **Python 3.11+** (recommended for ADK 2.x).
- **[Ollama](https://ollama.com/)** for local mode (`adk run code_local`). Default model: `gemma4:26b`.
- **Google API key** for cloud mode (`adk run code_cloud`). Set `GOOGLE_API_KEY` in `code/.env`.
- Set `USE_OLLAMA=false` for rules-only scoring (no LLM).
- **Tesseract** (optional): OCR fallback for scanned PDFs in the **tools** (see [OCR](#ocr-for-scanned-pdfs)).

## Architecture

```
User message
     │
     ▼
_workflow_input_gate ── /help, /model, … ──► local commands (no LLM, no tools)
     │
     ├── verify ──► _render_pdf_for_llm ──► .session_cache/<session>/images/page-NNN.png
     │                    │
     │                    ├── verify_transcript_math(pdf)    ── PDF only
     │                    ├── verify_transcript_spatial(pdf) ── PDF only
     │                    └── verify_transcript_dates(pdf)  ── PDF only (uses get_current_datetime)
     │                              │
     │                              ▼
     │                    Ollama or Gemini (PNGs + tool JSON)  or  rules fallback
     │
     ├── qa ──► cached PNGs + tool JSON ──► LLM Q&A (plain language)
     │
     └── qa_refresh (explain + .pdf) ── same chain as verify, then Q&A (no re-assessment JSON)
```

| Input | Consumer | Technology |
|-------|----------|------------|
| Original `.pdf` | `verify_transcript_math`, `verify_transcript_spatial`, `verify_transcript_dates` | pdfplumber, PyMuPDF, optional Tesseract OCR |
| Reference clock | `get_current_datetime` (UTC) | Used by `verify_transcript_dates` — no PDF required |
| Session PNGs | LLM assessment & Q&A | PyMuPDF render → LiteLLM → Ollama or Gemini |
| Tool JSON | Ollama + rules scorer | Authoritative for numeric checks, date flags, and other tool flags |

**Important:** Tools never read the session PNG cache. The LLM never parses the PDF file directly.

## Setup (from project root `Agent/`)

### Check Python

| OS | Command |
|----|---------|
| **Windows** | `py -0`, then `py -3.11 --version` |
| **Linux / macOS** | `python3.11 --version` |

On Windows use the **`py` launcher** (`py -3.11`), not `python3.11`, unless that alias is on PATH.

### Linux / macOS

```bash
cd /path/to/Agent
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r code/requirements.txt
pip show google-adk    # expect 2.1.0
```

### Windows (PowerShell)

```powershell
cd D:\RT\Goals\Agent
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r code\requirements.txt
python -m pip show google-adk
```

### Environment file

Copy `code/.env.example` → `code/.env` and adjust:

```env
USE_OLLAMA=true
OLLAMA_MODEL=ollama/gemma4:26b
OLLAMA_API_BASE=http://localhost:11434
OLLAMA_TEMPERATURE=0.2

# Cloud (for adk run code_cloud)
# GOOGLE_API_KEY=your-key
# CLOUD_MODEL=gemini/gemini-2.0-flash

SESSION_CACHE_DIR=.session_cache
PDF_RENDER_DPI=150
PDF_MAX_PAGES=20

OLLAMA_TIMEOUT_SECONDS=300
OLLAMA_IMAGE_MAX_EDGE=1024
OLLAMA_MAX_IMAGES=4
# OLLAMA_SEND_IMAGES=false   # text-only LLM (faster; tool JSON only)
```

| Variable | Purpose |
|----------|---------|
| `TRANSCRIPT_LLM_BACKEND` | Set by entry point: `local` or `cloud` (or legacy: unset + `USE_OLLAMA`) |
| `USE_OLLAMA` | `false` → rule-based assessment only |
| `GOOGLE_API_KEY` | Required for `adk run code_cloud` |
| `CLOUD_MODEL` | LiteLLM Gemini id (default `gemini/gemini-2.0-flash`) |
| `OLLAMA_MODEL` | LiteLLM model id (e.g. `ollama/gemma4:26b`) |
| `SESSION_CACHE_DIR` | Per-session PNG cache root |
| `PDF_RENDER_DPI` | DPI when rendering PDF pages to PNG |
| `PDF_MAX_PAGES` | Max pages rendered per PDF |
| `OLLAMA_TIMEOUT_SECONDS` | Per-request timeout (vision can be slow) |
| `OLLAMA_IMAGE_MAX_EDGE` | Downscale PNG longest edge before sending to Ollama |
| `OLLAMA_MAX_IMAGES` | Cap images attached per LLM call |
| `OLLAMA_SEND_IMAGES` | `false` → LLM gets tool JSON only (no vision) |

### Ollama setup

```powershell
ollama serve
ollama pull gemma4:26b
```

Use a **vision-capable** model if you rely on PNG analysis. Text-only models work with `OLLAMA_SEND_IMAGES=false` or when vision fails (automatic text-only retry).

If Ollama is down, times out, or returns invalid JSON, the agent **falls back to rule-based scoring** and notes that in `explanation_summary`.

## What’s in this package

| Item | Location |
|------|----------|
| Dependencies | `code/requirements.txt` (`google-adk[extensions]==2.1.0`, …) |
| Workflow agent | `code/agent.py` — gate, dual path, LLM/rules, session Q&A |
| ADK entry points | `code_local/agent.py`, `code_cloud/agent.py` — pick backend at startup |
| LLM dispatch | `code/llm_client.py` — routes to Ollama or Gemini |
| Cloud client | `code/cloud_client.py` — Gemini via LiteLLM |
| Intent routing | `code/intent.py` — verify vs explain/Q&A vs need PDF |
| PDF → PNG | `code/pdf_images.py` — session cache (LLM only) |
| Ollama client | `code/ollama_client.py` — LiteLLM, JSON schema prompt, vision resize |
| Rule scoring | `code/scoring.py` — fallback / `USE_OLLAMA=false` |
| Session Q&A | `code/session_qa.py` — rules fallback for explain questions |
| Output schema | `code/schemas.py` — `TranscriptAssessment` + JSON schema helpers |
| Math tool | `code/transcript_math.py` — `verify_transcript_math` |
| Spatial tool | `code/transcript_spatial.py` — `verify_transcript_spatial` |
| Date / clock tools | `code/transcript_dates.py` — `get_current_datetime`, `verify_transcript_dates` |
| Slash commands | `code/commands/`, `code/middleware/` — see [SLASH_COMMANDS.md](SLASH_COMMANDS.md) |
| Runtime session | `code/runtime/session.py` — history, verification cache, PNG paths |
| Env template | `code/.env.example` |

## Verification tools (PDF only)

| Tool | Purpose |
|------|---------|
| **`get_current_datetime`** | Returns the agent reference clock (UTC): `reference_datetime`, `reference_date`, `timezone`. Used as “today” for transcript date checks. |
| **`verify_transcript_dates`** | Extracts dates from PDF text; flags any date **after** the reference clock (future dates on a transcript are suspicious). |
| **`verify_transcript_math`** | Course/credit/grade extraction (tables, text, OCR), credit sum vs stated total, GPA check (±0.01), logical flags. |
| **`verify_transcript_spatial`** | Grade-column alignment, GPA/degree font consistency (PyMuPDF spans; OCR fallback). |

Both date tools live in `code/transcript_dates.py`. The verify workflow runs `verify_transcript_dates` after math and spatial on every PDF verify.

Example date-tool flags: `Future date on transcript: 07/01/2027 (2027-07-01)`. Future dates drive **High Risk** in the rules scorer and appear in LLM evidence as `dates_verification`.

All verification tools return JSON dicts consumed by the rules scorer and passed as evidence to Ollama.

## Session Q&A and routing

| User message | Route |
|--------------|-------|
| `code/pdf/foo.pdf` or “Verify … foo.pdf” | Full verify → `TranscriptAssessment` JSON |
| “Explain …”, “How did you compute …?” (with session cache) | Q&A from cached PNGs + tool JSON |
| “Explain … foo.pdf” (new/changed PDF) | Tools + PNG render, then Q&A (not full assessment JSON) |
| `/help`, `/model`, … | Local slash commands |

Examples:

```text
Verify the transcript at code/pdf/sample.pdf
How did you compute 24.0?
Explain the credit sum for code/pdf/sample.pdf
```

Session cache (PNG + tool results) clears on `/clear`.

## Ollama assessment output

The assessor prompt embeds the **Pydantic JSON schema** and an example. The client:

- Sends PNGs (resized) + tool JSON to Ollama
- Parses JSON with fence stripping
- Retries once on invalid JSON (text-only repair call)
- Falls back to rules on timeout or connection errors

Output fields: `legitimacy_score`, `risk_level`, `explanation_summary`, `flags`.

## Running the agent

ADK does **not** support custom flags like `adk run code --local`. Use separate entry points or the wrapper script.

### Local LLM (Ollama)

From project root with venv activated:

```powershell
adk run code_local
```

Or:

```powershell
.\scripts\run_agent.ps1 -Mode local
```

Requires Ollama running (`ollama serve`) with the configured model pulled.

### Cloud LLM (Gemini)

Set `GOOGLE_API_KEY` in `code/.env`, then:

```powershell
adk run code_cloud
```

Or:

```powershell
.\scripts\run_agent.ps1 -Mode cloud
```

### Legacy entry point

`adk run code` still works and follows `USE_OLLAMA` / env vars (no explicit backend flag).

### ADK web UI

```powershell
adk web
```

Open http://127.0.0.1:8000 and select **`code_local`** or **`code_cloud`**.

Wrapper with web UI:

```powershell
.\scripts\run_agent.ps1 -Mode local -Web
```

### Local slash commands

Input starting with `/` is handled locally before the workflow. See [SLASH_COMMANDS.md](SLASH_COMMANDS.md) for `/help`, `/tools`, `/model`, `/config`, `/session`, `/clear`, etc.

### Verbose mode

```powershell
$env:TRANSCRIPT_AGENT_VERBOSE = "1"
adk run code_local
```

## OCR for scanned PDFs

Tools can use **Tesseract** when the PDF has little native text:

- **Windows:** [Tesseract installer](https://github.com/UB-Mannheim/tesseract/wiki)
- **Linux:** `sudo apt install tesseract-ocr`
- **macOS:** `brew install tesseract`

Scanned PDFs may fail structured table extraction in math/spatial while the **vision LLM** can still read PNGs — the assessor is instructed to treat **tool JSON as authoritative** and not Auto-Approve when tools report failures.

## Troubleshooting

| Symptom | Likely cause | Mitigation |
|---------|--------------|------------|
| Hangs after “Calling Ollama” | Large vision model + full-page PNGs | Wait (check logs for `Ollama request finished`); lower `OLLAMA_IMAGE_MAX_EDGE`; increase `OLLAMA_TIMEOUT_SECONDS` |
| Rules template in Q&A (`Math verification:` block) | Ollama failed; rules fallback | Fix Ollama; use vision model or `OLLAMA_SEND_IMAGES=false` |
| “Ollama unavailable … used rule-based scoring” in JSON | Timeout, invalid JSON, or Ollama down | Check `ollama serve`; see logs |
| Tools fail, LLM says Auto-Approve | Scanned PDF; tools can’t parse tables | Expected with dual path; tool JSON should drive risk when present |

Use `/model` and `/config` in the CLI to inspect active model and env.

## Tests

From project root with venv activated:

```powershell
python -m pytest tests/ -v
```

| Test file | Covers |
|-----------|--------|
| `test_transcript_math.py` | Math tool helpers and contract |
| `test_transcript_spatial.py` | Spatial tool helpers and contract |
| `test_transcript_dates.py` | Reference clock + future-date detection |
| `test_slash_commands.py` | Slash parser, dispatcher, workflow gate |
| `test_ollama.py` | Ollama routing, rules fallback, `/model` |
| `test_ollama_schema.py` | JSON schema prompt, parse/retry |
| `test_ollama_images.py` | PNG resize and multimodal message building |
| `test_pdf_images.py` | Session PDF → PNG cache |
| `test_session_qa.py` | Intent routing and Q&A workflow |
| `test_dual_path.py` | PDF tools vs PNG render separation |
| `test_metrics.py` | Prometheus instrumentation helpers |
| `test_db_store.py` | SQLite verification store + DB metrics |

Tests set `USE_OLLAMA=false`, `AGENT_DB_ENABLED=false`, and `AGENT_METRICS_ENABLED=false` by default in `tests/conftest.py`.

## Observability (Grafana)

Application metrics and dashboards live in [`monitoring/`](../monitoring/README.md):

```powershell
# Terminal 1 — stack
cd monitoring
docker compose up -d

# Terminal 2 — agent with metrics
$env:AGENT_METRICS_ENABLED = "true"
adk run code_local
```

Open **http://localhost:3001** for Grafana (port 3001 avoids conflict with Open WebUI on 3000).
