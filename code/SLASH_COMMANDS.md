# Local slash commands

Developer-only commands for the Transcript Risk Assessor ADK workflow.  
**Lines starting with `/` are handled locally** — they are not sent to the LLM, do not invoke workflow tools, and are stored in local runtime history with `local_only=True`.

## Architecture

```
code/
  commands/
    base.py           # BaseCommand interface
    parser.py         # /cmd args --flags parsing
    registry.py       # CommandRegistry
    dispatcher.py     # CommandDispatcher + suggestions
    terminal.py       # Colored tables (when TTY)
    handlers/         # One module per command group
  middleware/
    slash_commands.py # SlashCommandInterceptor (pre-workflow)
  runtime/
    session.py        # Local session (history, debug, verification cache)
    context.py        # CommandContext for handlers
    introspection.py  # /tools, /agents, /config, /model metadata
  intent.py           # verify vs Q&A intent (used by agent gate)
  pdf_images.py       # PDF → PNG for LLM (not used by tools)
  user_text.py        # Extract text from ADK Content
```

**Integration:** `code/agent.py` → `_workflow_input_gate` runs the interceptor first.

| Route | Behavior |
|-------|----------|
| `local` | `_local_command_sink` — no PNG render, no tools, no LLM |
| `verify` | PNG render → math → spatial → Ollama assessment or rules |
| `qa` | Cached PNGs + tool JSON → Ollama Q&A (or rules fallback) |

Dual path on verify / explain-refresh:

```
.pdf file  → verify_transcript_math / verify_transcript_spatial / verify_transcript_dates
.pdf file  → ensure_pdf_images → .session_cache/<session_id>/images/.../page-NNN.png
PNG + tool JSON → Ollama assessment / session Q&A
```

Session cache layout:

```
.session_cache/<session_id>/images/<pdf_slug>/page-001.png
                                              manifest.txt
```

Cleared by `/clear` (local history + PNG cache for that session).

## Commands

| Command | Description |
|---------|-------------|
| `/help` | List commands |
| `/tools` | `get_current_datetime`, `verify_transcript_dates`, `verify_transcript_math`, `verify_transcript_spatial` |
| `/agents` | Root `Workflow` agent |
| `/prompts` | Instruction / prompt summary (truncated) |
| `/memory` | Local + ADK state summary |
| `/session` | Session ids, message counts |
| `/config` | Runtime env flags (see also `/model`) |
| `/model` | Active Ollama model + local vs cloud deployment |
| `/history [N]` | Conversation log (SQLite when enabled) |
| `/assessments [N]` | Verification runs for this session |
| `/audit [N]` | Tool runs + LLM call audit log |
| `/clear` | Clear local history, SQLite rows, and session image cache |
| `/reload` | `importlib.reload` of `code.*` modules |
| `/debug on` \| `/debug off` | Verbose logging |
| `/exit` | End session (`SystemExit`) |

Aliases: `/?`, `/h` → help; `/quit`, `/q` → exit.

## Sample session

```
[user]: /model
... ollama/gemma4:26b (local) ...

[user]: Verify the transcript at code/pdf/sample.pdf
... TranscriptAssessment JSON ...

[user]: How did you compute 24.0?
... plain-language Q&A from cached PNGs + tool JSON ...

[user]: Explain the credit sum for code/pdf/sample.pdf
... tools + PNG if needed, then explanation (not assessment JSON) ...

[user]: /clear
Local runtime history and session image cache cleared.
```

## Extending

1. Subclass `BaseCommand` in `code/commands/handlers/`.
2. Register in `handlers/__init__.py` → `build_all_handlers()`.
3. Handlers receive `CommandContext` and `ParsedCommand`.

Autocomplete metadata: `command.autocomplete_meta` on each handler.

## Tests

```powershell
.\venv\Scripts\Activate.ps1
python -m pytest tests/test_slash_commands.py tests/test_session_qa.py -v
```

See [README.md](README.md) for the full test suite and environment variables.
