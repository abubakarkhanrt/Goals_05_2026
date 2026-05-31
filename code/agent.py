"""
Transcript verification agent: Risk Assessor.
Orchestrated with Google ADK 2.x Workflow (google-adk==2.1.0).

Dual-path pipeline:
  1. PDF path  — verify_transcript_math + verify_transcript_spatial on the .pdf file
  2. PNG path  — page renders in `.session_cache/` for the local vision LLM only
  3. Assessment — Ollama reads PNGs + tool JSON; rules fallback if Ollama is off/down
  4. Session Q&A — follow-up questions reuse cached PNGs + tool JSON

Local slash commands (/help, …) are intercepted before the workflow runs.
"""

import json
import logging
import os
import time
import warnings

_VERBOSE = os.environ.get("TRANSCRIPT_AGENT_VERBOSE", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "y",
    "on",
}

if not _VERBOSE:
    warnings.filterwarnings("ignore", category=FutureWarning)
    warnings.filterwarnings("ignore", category=UserWarning)
    logging.getLogger("google_adk").setLevel(logging.ERROR)
    logging.getLogger("google").setLevel(logging.ERROR)

from google.adk import Context
from google.adk import Event
from google.adk import Workflow

from .intent import classify_turn, extract_pdf_path
from .llm_config import ROUTE_LLM, ROUTE_QA, ROUTE_RULES, assessment_mode_label, llm_enabled, llm_backend
from .middleware.slash_commands import (
    ROUTE_LOCAL,
    ROUTE_VERIFY,
    try_intercept_slash_command,
)
from .pdf_images import ensure_pdf_images
from .runtime.session import get_runtime_session
from .scoring import build_rules_assessment
from .session_qa import answer_with_rules, build_qa_context
from .transcript_math import verify_transcript_math
from .transcript_spatial import verify_transcript_spatial
from .transcript_dates import get_current_datetime, verify_transcript_dates
from .user_text import extract_user_text
from .observability.metrics import (
    metrics_enabled,
    record_llm_fallback,
    record_route,
    start_metrics_server,
    track_cache_io,
    track_task,
    track_task_async,
)

_ASSESSMENT_MODE = assessment_mode_label()

if metrics_enabled():
    start_metrics_server()

_STARTUP_BANNER = f"""Transcript Risk Assessor is ready.

Pipeline (dual path):
  1. Tools on the PDF file — math + spatial (pdfplumber / PyMuPDF / OCR)
  2. PNG renders in `.session_cache/<session_id>/` — for the local vision LLM only
  3. Final assessment via {_ASSESSMENT_MODE} (LLM reads PNGs + tool JSON from PDF)
  4. Follow-up Q&A — cached PNGs + tool JSON

Capabilities:
- verify_transcript_math — credits, GPA, logical checks (OCR if needed)
- verify_transcript_spatial — alignment, font consistency (OCR if needed)
- verify_transcript_dates — future-date check vs get_current_datetime (UTC)
- Structured JSON: legitimacy_score, risk_level, explanation_summary, flags
- Session Q&A: "Explain the credit sum", "How did you compute 24.0?"

LLM backend: {llm_backend()} — see `adk run code_local` or `adk run code_cloud`

Local (Ollama): ensure `ollama serve` is running; tune OLLAMA_TIMEOUT_SECONDS / OLLAMA_IMAGE_MAX_EDGE.
Cloud (Gemini): set GOOGLE_API_KEY in code/.env; tune CLOUD_MODEL.
Rules-only: USE_OLLAMA=false and no cloud key, or use a disabled backend entry.

Local commands: /help, /tools, /config, …

Examples:
  Verify the transcript at code/pdf/2c48062a-f42e-46ee-9137-fedb70e9952a.pdf
  Explain the credit sum for code/pdf/2c48062a-f42e-46ee-9137-fedb70e9952a.pdf
  How did you compute 24.0?
"""

print(_STARTUP_BANNER)

logger = logging.getLogger(__name__)


async def _workflow_input_gate(ctx: Context, node_input=None) -> Event:
    """Slash commands → local; Q&A → cached evidence; otherwise → verification pipeline."""
    async with track_task_async("workflow_input_gate"):
        text = extract_user_text(getattr(ctx, "user_content", None), node_input)
        runtime = get_runtime_session()

        slash_result = await try_intercept_slash_command(text, adk_context=ctx)
        if slash_result and slash_result.handled:
            record_route(ROUTE_LOCAL)
            return Event(
                message=slash_result.output,
                route=ROUTE_LOCAL,
                state={"slash_command": slash_result.command_name},
            )

        from .user_attachments import resolve_pdf_from_user_content

        attachment_pdf = await resolve_pdf_from_user_content(
            getattr(ctx, "user_content", None),
            session_id=runtime.session_id,
            adk_context=ctx,
        )

        if text.strip():
            runtime.record_user(text, local_only=False)
        runtime.workflow_runs += 1

        event = _route_user_turn(
            ctx, node_input, text=text, attachment_pdf_path=attachment_pdf
        )
        record_route(getattr(event.actions, "route", None) or "unknown")
        return event


def _local_command_sink(ctx: Context, node_input=None) -> Event:
    return Event(output={"slash_command": True})


def _route_user_turn(
    ctx: Context,
    node_input=None,
    *,
    text: str | None = None,
    attachment_pdf_path: str | None = None,
) -> Event:
    if text is None:
        text = extract_user_text(getattr(ctx, "user_content", None), node_input)

    runtime = get_runtime_session()
    pdf_in_message = extract_pdf_path(text) or attachment_pdf_path
    turn = classify_turn(
        text,
        has_cached_verification=runtime.has_verification_cache(),
        pdf_path=pdf_in_message,
    )

    if turn == "need_pdf":
        debug_tail = ""
        if _VERBOSE:
            user_content = getattr(ctx, "user_content", None)
            debug_tail = "\n\n" + "\n".join(
                [
                    f"debug.text={text!r}",
                    f"debug.user_content={user_content!r}",
                    f"debug.node_input={node_input!r}",
                ]
            )
        return Event(
            message=(
                "No transcript in session yet. Verify a PDF first, for example:\n"
                "  Verify the transcript at code/pdf/2c48062a-f42e-46ee-9137-fedb70e9952a.pdf\n\n"
                "Or attach a `.pdf` in ADK web with a message like \"verify transcript\".\n"
                "Or include a `.pdf` path in your explain / follow-up question.\n\n"
                "Developer commands: /help"
            )
            + debug_tail,
            route=ROUTE_LOCAL,
        )

    if turn == "qa":
        pdf_path = pdf_in_message or runtime.last_pdf_path
        need_refresh = (
            pdf_in_message is not None and pdf_in_message != runtime.last_pdf_path
        ) or not runtime.has_verification_cache()
        common_state = {
            "pdf_path": pdf_path,
            "user_question": text.strip(),
            "session_mode": "qa_refresh" if need_refresh else "qa",
        }
        if need_refresh:
            return Event(
                output=pdf_path,
                state=common_state,
                route=ROUTE_VERIFY,
            )
        return Event(
            state={
                **common_state,
                "math_result": runtime.last_math_result,
                "spatial_result": runtime.last_spatial_result,
                "dates_result": runtime.last_dates_result,
                "pdf_image_paths": runtime.last_pdf_image_paths,
            },
            route=ROUTE_QA,
        )

    return Event(
        output=pdf_in_message,
        state={"pdf_path": pdf_in_message, "session_mode": "verify"},
        route=ROUTE_VERIFY,
    )


def _prepare_pdf_images(pdf_path: str | None) -> list[str]:
    """Render PDF pages to session PNGs (LLM vision path only — not used by tools)."""
    if not pdf_path:
        return []
    runtime = get_runtime_session()
    try:
        with track_cache_io("pdf_render"):
            image_paths = ensure_pdf_images(pdf_path, runtime.session_id)
        runtime.save_pdf_images(image_paths)
        return image_paths
    except Exception as exc:
        logger.warning("PDF image conversion failed: %s", exc)
        return runtime.last_pdf_image_paths or []


def _render_pdf_for_llm(pdf_path: str | None) -> Event:
    """PNG path: render PDF pages for the vision LLM (tools do not use these files)."""
    with track_task("render_pdf"):
        image_paths = _prepare_pdf_images(pdf_path)
        return Event(
            output=pdf_path,
            state={"pdf_path": pdf_path, "pdf_image_paths": image_paths},
        )


def _run_math_check(pdf_path: str | None) -> Event:
    """PDF path: deterministic math verification on the transcript file."""
    with track_task("verify_transcript_math"):
        if not pdf_path:
            result = {"success": False, "flags": ["Missing PDF path"]}
            _audit_tool_run("verify_transcript_math", pdf_path, result, status="error")
            return Event(output=None, state={"math_result": result})
        started = time.perf_counter()
        result = verify_transcript_math(pdf_path)
        _audit_tool_run(
            "verify_transcript_math",
            pdf_path,
            result,
            duration_ms=(time.perf_counter() - started) * 1000,
            status="success" if result.get("success") else "error",
        )
        return Event(output=pdf_path, state={"math_result": result})


def _run_spatial_check(pdf_path: str | None) -> Event:
    """PDF path: deterministic spatial verification on the transcript file."""
    with track_task("verify_transcript_spatial"):
        if not pdf_path:
            result = {"success": False, "flags": ["Missing PDF path"]}
            _audit_tool_run("verify_transcript_spatial", pdf_path, result, status="error")
            return Event(output=None, state={"spatial_result": result})
        started = time.perf_counter()
        result = verify_transcript_spatial(pdf_path)
        _audit_tool_run(
            "verify_transcript_spatial",
            pdf_path,
            result,
            duration_ms=(time.perf_counter() - started) * 1000,
            status="success" if result.get("success") else "error",
        )
        return Event(output=pdf_path, state={"spatial_result": result})


def _run_dates_check(pdf_path: str | None) -> Event:
    """PDF path: flag transcript dates that are after the agent reference clock."""
    with track_task("verify_transcript_dates"):
        if not pdf_path:
            result = {"success": False, "flags": ["Missing PDF path"], "dates_ok": False}
            _audit_tool_run("verify_transcript_dates", pdf_path, result, status="error")
            return Event(output=None, state={"dates_result": result})
        started = time.perf_counter()
        result = verify_transcript_dates(pdf_path)
        _audit_tool_run(
            "verify_transcript_dates",
            pdf_path,
            result,
            duration_ms=(time.perf_counter() - started) * 1000,
            status="success" if result.get("success") else "error",
        )
        return Event(output=pdf_path, state={"dates_result": result})


def _audit_tool_run(
    tool_name: str,
    pdf_path: str | None,
    result: dict,
    *,
    duration_ms: float | None = None,
    status: str = "success",
) -> None:
    from .db.store import persist_tool_run

    persist_tool_run(
        get_runtime_session().session_id,
        tool_name,
        pdf_path=pdf_path,
        result=result,
        duration_ms=duration_ms,
        status=status,
    )


def _audit_llm_failure(operation: str, exc: Exception, *, fallback: bool = True) -> None:
    from .db.store import persist_llm_call
    from .llm_config import llm_backend, ollama_model, cloud_model

    backend = llm_backend()
    model = ollama_model() if backend == "local" else cloud_model() if backend == "cloud" else None
    persist_llm_call(
        get_runtime_session().session_id,
        operation,
        model=model,
        backend=backend,
        status="error",
        error_type=type(exc).__name__,
        fallback=fallback,
    )


def _post_tools_router(
    pdf_path: str | None,
    math_result: dict | None = None,
    spatial_result: dict | None = None,
    dates_result: dict | None = None,
    session_mode: str = "verify",
    user_question: str | None = None,
    pdf_image_paths: list[str] | None = None,
) -> Event:
    """After math+spatial+dates: full assessment (verify) or session Q&A (explain refresh)."""
    runtime = get_runtime_session()
    image_paths = pdf_image_paths or runtime.last_pdf_image_paths
    runtime.save_verification(
        pdf_path,
        math_result,
        spatial_result,
        pdf_image_paths=image_paths,
        dates_result=dates_result,
    )

    if session_mode == "qa_refresh":
        return Event(
            route=ROUTE_QA,
            state={
                "pdf_path": pdf_path,
                "math_result": math_result,
                "spatial_result": spatial_result,
                "dates_result": dates_result,
                "user_question": user_question or "",
                "pdf_image_paths": image_paths,
            },
        )

    return _assessment_backend_gate(pdf_path, math_result, spatial_result, dates_result)


def _assessment_backend_gate(
    pdf_path: str | None,
    math_result: dict | None = None,
    spatial_result: dict | None = None,
    dates_result: dict | None = None,
) -> Event:
    """Route to LLM assessor (local/cloud) or rule-based scorer."""
    if llm_enabled():
        payload = {
            "pdf_path": pdf_path,
            "math_verification": math_result or {},
            "spatial_verification": spatial_result or {},
            "dates_verification": dates_result or {},
            "reference_clock": get_current_datetime(),
            "llm_backend": llm_backend(),
        }
        return Event(
            output=json.dumps(payload, indent=2),
            route=ROUTE_LLM,
        )
    return Event(route=ROUTE_RULES)


def _score_and_summarize_rules(
    pdf_path: str | None,
    math_result: dict | None = None,
    spatial_result: dict | None = None,
    dates_result: dict | None = None,
    pdf_image_paths: list[str] | None = None,
) -> Event:
    runtime = get_runtime_session()
    assessment = build_rules_assessment(pdf_path, math_result, spatial_result, dates_result)
    dump = assessment.model_dump()
    runtime.save_verification(
        pdf_path,
        math_result,
        spatial_result,
        dump,
        pdf_image_paths=pdf_image_paths or runtime.last_pdf_image_paths,
        dates_result=dates_result,
    )
    body = assessment.model_dump_json(indent=2)
    get_runtime_session().record_assistant(body)
    return Event(message=body, output=dump)


async def _llm_assess_with_fallback(
    pdf_path: str | None,
    math_result: dict | None = None,
    spatial_result: dict | None = None,
    dates_result: dict | None = None,
    pdf_image_paths: list[str] | None = None,
) -> Event:
    """Try configured LLM backend; fall back to rules if unavailable."""
    async with track_task_async("llm_assess"):
        runtime = get_runtime_session()
        image_paths = pdf_image_paths or runtime.last_pdf_image_paths
        rules = build_rules_assessment(pdf_path, math_result, spatial_result, dates_result)
        try:
            from .llm_client import assess_transcript, llm_unavailable_message

            assessment = await assess_transcript(
                pdf_path,
                math_result,
                spatial_result,
                dates_result,
                image_paths=image_paths,
            )
            dump = assessment.model_dump()
            runtime.save_verification(
                pdf_path,
                math_result,
                spatial_result,
                dump,
                pdf_image_paths=image_paths,
                dates_result=dates_result,
            )
            body = assessment.model_dump_json(indent=2)
            get_runtime_session().record_assistant(body)
            return Event(message=body, output=dump)
        except Exception as exc:
            logger.warning("LLM assessment failed, using rules: %s", exc)
            record_llm_fallback("assess", type(exc).__name__)
            _audit_llm_failure("assess", exc)
            rules.explanation_summary = (rules.explanation_summary or "") + " " + llm_unavailable_message(exc)
            dump = rules.model_dump()
            runtime.save_verification(
                pdf_path,
                math_result,
                spatial_result,
                dump,
                pdf_image_paths=image_paths,
                dates_result=dates_result,
            )
            body = rules.model_dump_json(indent=2)
            get_runtime_session().record_assistant(body)
            return Event(message=body, output=dump)


async def _session_qa_answer(
    pdf_path: str | None,
    math_result: dict | None = None,
    spatial_result: dict | None = None,
    dates_result: dict | None = None,
    user_question: str | None = None,
    pdf_image_paths: list[str] | None = None,
) -> Event:
    """Answer explain / follow-up questions from cached verification evidence."""
    async with track_task_async("session_qa"):
        runtime = get_runtime_session()
        runtime.ensure_verification_loaded()
        question = (user_question or "").strip() or "Explain the verification results."
        image_paths = pdf_image_paths or runtime.last_pdf_image_paths
        dates = dates_result if dates_result is not None else runtime.last_dates_result
        context = build_qa_context(
            pdf_path, math_result, spatial_result, runtime.last_assessment, dates
        )

        if llm_enabled():
            try:
                from .llm_client import answer_session_question

                answer = await answer_session_question(
                    question,
                    pdf_path,
                    math_result,
                    spatial_result,
                    runtime.last_assessment,
                    dates,
                    image_paths=image_paths,
                )
            except Exception as exc:
                logger.warning("LLM session Q&A failed, using rules: %s", exc)
                record_llm_fallback("qa", type(exc).__name__)
                _audit_llm_failure("qa", exc)
                answer = answer_with_rules(question, context)
        else:
            answer = answer_with_rules(question, context)

        runtime.record_assistant(answer)
        return Event(message=answer, output={"qa": True, "pdf_path": pdf_path})


# Ollama path: async LiteLLM call with automatic rule-based fallback if Ollama is down.
_LLM_TERMINAL = _llm_assess_with_fallback

root_agent = Workflow(
    name="transcript_risk_assessor",
    edges=[
        (
            "START",
            _workflow_input_gate,
            {
                ROUTE_LOCAL: _local_command_sink,
                ROUTE_VERIFY: _render_pdf_for_llm,
                ROUTE_QA: _session_qa_answer,
            },
        ),
        (_render_pdf_for_llm, _run_math_check, _run_spatial_check, _run_dates_check, _post_tools_router),
        (
            _post_tools_router,
            {
                ROUTE_LLM: _LLM_TERMINAL,
                ROUTE_RULES: _score_and_summarize_rules,
                ROUTE_QA: _session_qa_answer,
            },
        ),
    ],
)
