"""SQLite store for verification history, messages, tool runs, and LLM audit (Option 3)."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import db_enabled, db_path

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS verification_runs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    pdf_path TEXT,
    math_json TEXT,
    spatial_json TEXT,
    assessment_json TEXT,
    pdf_image_paths_json TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_verification_session_created
    ON verification_runs (session_id, created_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    local_only INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session_created
    ON messages (session_id, created_at DESC);

CREATE TABLE IF NOT EXISTS tool_runs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    verification_run_id TEXT,
    tool_name TEXT NOT NULL,
    pdf_path TEXT,
    result_json TEXT,
    duration_ms REAL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tool_runs_session_created
    ON tool_runs (session_id, created_at DESC);

CREATE TABLE IF NOT EXISTS llm_calls (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    model TEXT,
    backend TEXT,
    duration_s REAL,
    image_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    error_type TEXT,
    fallback INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_llm_calls_session_created
    ON llm_calls (session_id, created_at DESC);
"""

_store: "VerificationStore | None" = None
_store_lock = threading.Lock()


@dataclass
class VerificationRecord:
    id: str
    pdf_path: str | None
    math_result: dict | None
    spatial_result: dict | None
    assessment: dict | None
    pdf_image_paths: list[str]
    created_at: str


@dataclass
class VerificationSummary:
    id: str
    pdf_path: str | None
    risk_level: str | None
    legitimacy_score: float | None
    created_at: str


@dataclass
class MessageRecord:
    role: str
    text: str
    local_only: bool
    created_at: str


@dataclass
class ToolRunRecord:
    tool_name: str
    pdf_path: str | None
    status: str
    duration_ms: float | None
    created_at: str
    result: dict | None


@dataclass
class LlmCallRecord:
    operation: str
    model: str | None
    backend: str | None
    duration_s: float | None
    image_count: int
    status: str
    error_type: str | None
    fallback: bool
    created_at: str


class VerificationStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.executescript(_SCHEMA)
                row = conn.execute(
                    "SELECT MAX(version) AS v FROM schema_version"
                ).fetchone()
                current = row["v"] if row and row["v"] is not None else 0
                if current < 3:
                    conn.execute(
                        "INSERT OR REPLACE INTO schema_version (version, applied_at) VALUES (?, ?)",
                        (3, datetime.now(timezone.utc).isoformat()),
                    )
                conn.commit()

    def save_verification(
        self,
        session_id: str,
        pdf_path: str | None,
        math_result: dict | None,
        spatial_result: dict | None,
        assessment: dict | None = None,
        *,
        pdf_image_paths: list[str] | None = None,
    ) -> str:
        from ..observability.metrics import track_db

        run_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        with track_db("insert_verification"):
            with self._lock:
                with self._connect() as conn:
                    conn.execute(
                        """
                        INSERT INTO verification_runs (
                            id, session_id, pdf_path, math_json, spatial_json,
                            assessment_json, pdf_image_paths_json, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            session_id,
                            pdf_path,
                            json.dumps(math_result) if math_result is not None else None,
                            json.dumps(spatial_result) if spatial_result is not None else None,
                            json.dumps(assessment) if assessment is not None else None,
                            json.dumps(pdf_image_paths) if pdf_image_paths is not None else None,
                            created_at,
                        ),
                    )
                    conn.commit()
        return run_id

    def get_latest(self, session_id: str) -> VerificationRecord | None:
        from ..observability.metrics import track_db

        with track_db("select_latest_verification"):
            with self._lock:
                with self._connect() as conn:
                    row = conn.execute(
                        """
                        SELECT id, pdf_path, math_json, spatial_json, assessment_json,
                               pdf_image_paths_json, created_at
                        FROM verification_runs
                        WHERE session_id = ?
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        (session_id,),
                    ).fetchone()
        if row is None:
            return None
        return _row_to_verification_record(row)

    def list_verifications(
        self, session_id: str, *, limit: int = 20
    ) -> list[VerificationSummary]:
        from ..observability.metrics import track_db

        with track_db("select_verification_history"):
            with self._lock:
                with self._connect() as conn:
                    rows = conn.execute(
                        """
                        SELECT id, pdf_path, assessment_json, created_at
                        FROM verification_runs
                        WHERE session_id = ?
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        (session_id, limit),
                    ).fetchall()
        out: list[VerificationSummary] = []
        for row in rows:
            assessment = _loads_json(row["assessment_json"])
            risk_level = None
            legitimacy_score = None
            if isinstance(assessment, dict):
                risk_level = assessment.get("risk_level")
                raw_score = assessment.get("legitimacy_score")
                if isinstance(raw_score, (int, float)):
                    legitimacy_score = float(raw_score)
            out.append(
                VerificationSummary(
                    id=row["id"],
                    pdf_path=row["pdf_path"],
                    risk_level=risk_level,
                    legitimacy_score=legitimacy_score,
                    created_at=row["created_at"],
                )
            )
        return out

    def save_message(
        self,
        session_id: str,
        role: str,
        text: str,
        *,
        local_only: bool = False,
    ) -> str:
        from ..observability.metrics import track_db

        msg_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        with track_db("insert_message"):
            with self._lock:
                with self._connect() as conn:
                    conn.execute(
                        """
                        INSERT INTO messages (id, session_id, role, text, local_only, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (msg_id, session_id, role, text, int(local_only), created_at),
                    )
                    conn.commit()
        return msg_id

    def list_messages(self, session_id: str, *, limit: int = 50) -> list[MessageRecord]:
        from ..observability.metrics import track_db

        with track_db("select_messages"):
            with self._lock:
                with self._connect() as conn:
                    rows = conn.execute(
                        """
                        SELECT role, text, local_only, created_at
                        FROM messages
                        WHERE session_id = ?
                        ORDER BY created_at ASC
                        LIMIT ?
                        """,
                        (session_id, limit),
                    ).fetchall()
        return [
            MessageRecord(
                role=row["role"],
                text=row["text"],
                local_only=bool(row["local_only"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def save_tool_run(
        self,
        session_id: str,
        tool_name: str,
        *,
        pdf_path: str | None = None,
        result: dict | None = None,
        duration_ms: float | None = None,
        status: str = "success",
        verification_run_id: str | None = None,
    ) -> str:
        from ..observability.metrics import track_db

        run_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        with track_db("insert_tool_run"):
            with self._lock:
                with self._connect() as conn:
                    conn.execute(
                        """
                        INSERT INTO tool_runs (
                            id, session_id, verification_run_id, tool_name, pdf_path,
                            result_json, duration_ms, status, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            session_id,
                            verification_run_id,
                            tool_name,
                            pdf_path,
                            json.dumps(result) if result is not None else None,
                            duration_ms,
                            status,
                            created_at,
                        ),
                    )
                    conn.commit()
        return run_id

    def list_tool_runs(self, session_id: str, *, limit: int = 20) -> list[ToolRunRecord]:
        from ..observability.metrics import track_db

        with track_db("select_tool_runs"):
            with self._lock:
                with self._connect() as conn:
                    rows = conn.execute(
                        """
                        SELECT tool_name, pdf_path, status, duration_ms, result_json, created_at
                        FROM tool_runs
                        WHERE session_id = ?
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        (session_id, limit),
                    ).fetchall()
        return [
            ToolRunRecord(
                tool_name=row["tool_name"],
                pdf_path=row["pdf_path"],
                status=row["status"],
                duration_ms=row["duration_ms"],
                created_at=row["created_at"],
                result=_loads_json(row["result_json"]),
            )
            for row in rows
        ]

    def save_llm_call(
        self,
        session_id: str,
        operation: str,
        *,
        model: str | None = None,
        backend: str | None = None,
        duration_s: float | None = None,
        image_count: int = 0,
        status: str = "success",
        error_type: str | None = None,
        fallback: bool = False,
    ) -> str:
        from ..observability.metrics import track_db

        call_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        with track_db("insert_llm_call"):
            with self._lock:
                with self._connect() as conn:
                    conn.execute(
                        """
                        INSERT INTO llm_calls (
                            id, session_id, operation, model, backend, duration_s,
                            image_count, status, error_type, fallback, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            call_id,
                            session_id,
                            operation,
                            model,
                            backend,
                            duration_s,
                            image_count,
                            status,
                            error_type,
                            int(fallback),
                            created_at,
                        ),
                    )
                    conn.commit()
        return call_id

    def list_llm_calls(self, session_id: str, *, limit: int = 20) -> list[LlmCallRecord]:
        from ..observability.metrics import track_db

        with track_db("select_llm_calls"):
            with self._lock:
                with self._connect() as conn:
                    rows = conn.execute(
                        """
                        SELECT operation, model, backend, duration_s, image_count,
                               status, error_type, fallback, created_at
                        FROM llm_calls
                        WHERE session_id = ?
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        (session_id, limit),
                    ).fetchall()
        return [
            LlmCallRecord(
                operation=row["operation"],
                model=row["model"],
                backend=row["backend"],
                duration_s=row["duration_s"],
                image_count=row["image_count"],
                status=row["status"],
                error_type=row["error_type"],
                fallback=bool(row["fallback"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def clear_session(self, session_id: str) -> int:
        from ..observability.metrics import track_db

        with track_db("delete_session_verifications"):
            with self._lock:
                with self._connect() as conn:
                    deleted = 0
                    for table in (
                        "messages",
                        "tool_runs",
                        "llm_calls",
                        "verification_runs",
                    ):
                        cur = conn.execute(
                            f"DELETE FROM {table} WHERE session_id = ?",
                            (session_id,),
                        )
                        deleted += cur.rowcount
                    conn.commit()
                    return deleted

    def close(self) -> None:
        """Checkpoint WAL so Windows can delete the database file in tests."""
        with self._lock:
            try:
                with self._connect() as conn:
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    conn.commit()
            except Exception:
                pass


def _loads_json(raw: str | None) -> Any:
    if not raw:
        return None
    return json.loads(raw)


def _row_to_verification_record(row: sqlite3.Row) -> VerificationRecord:
    return VerificationRecord(
        id=row["id"],
        pdf_path=row["pdf_path"],
        math_result=_loads_json(row["math_json"]),
        spatial_result=_loads_json(row["spatial_json"]),
        assessment=_loads_json(row["assessment_json"]),
        pdf_image_paths=_loads_json(row["pdf_image_paths_json"]) or [],
        created_at=row["created_at"],
    )


def get_verification_store() -> VerificationStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = VerificationStore(db_path())
    return _store


def reset_verification_store(path: Path | None = None) -> VerificationStore:
    """Test helper — point store at a new database file."""
    global _store
    with _store_lock:
        _store = VerificationStore(path or db_path())
        return _store


def close_verification_store() -> None:
    """Release singleton (helps Windows tests delete temp DB files)."""
    global _store
    with _store_lock:
        _store = None


def persist_message(
    session_id: str, role: str, text: str, *, local_only: bool = False
) -> None:
    if not db_enabled():
        return
    try:
        get_verification_store().save_message(
            session_id, role, text, local_only=local_only
        )
    except Exception as exc:
        logger.warning("Failed to persist message to SQLite: %s", exc)


def persist_tool_run(
    session_id: str,
    tool_name: str,
    *,
    pdf_path: str | None = None,
    result: dict | None = None,
    duration_ms: float | None = None,
    status: str = "success",
) -> None:
    if not db_enabled():
        return
    try:
        get_verification_store().save_tool_run(
            session_id,
            tool_name,
            pdf_path=pdf_path,
            result=result,
            duration_ms=duration_ms,
            status=status,
        )
    except Exception as exc:
        logger.warning("Failed to persist tool run to SQLite: %s", exc)


def persist_llm_call(
    session_id: str,
    operation: str,
    *,
    model: str | None = None,
    backend: str | None = None,
    duration_s: float | None = None,
    image_count: int = 0,
    status: str = "success",
    error_type: str | None = None,
    fallback: bool = False,
) -> None:
    if not db_enabled():
        return
    try:
        get_verification_store().save_llm_call(
            session_id,
            operation,
            model=model,
            backend=backend,
            duration_s=duration_s,
            image_count=image_count,
            status=status,
            error_type=error_type,
            fallback=fallback,
        )
    except Exception as exc:
        logger.warning("Failed to persist LLM call to SQLite: %s", exc)
