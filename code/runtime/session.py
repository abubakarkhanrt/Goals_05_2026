"""Process-local session store for developer slash commands."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LocalMessage:
    role: str
    text: str
    local_only: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RuntimeSession:
    """Local introspection state; separate from ADK session service."""

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    messages: list[LocalMessage] = field(default_factory=list)
    debug_enabled: bool = False
    workflow_runs: int = 0
    token_usage_hint: dict[str, Any] = field(default_factory=dict)
    reload_count: int = 0
    last_pdf_path: str | None = None
    last_pdf_image_paths: list[str] = field(default_factory=list)
    last_math_result: dict | None = None
    last_spatial_result: dict | None = None
    last_dates_result: dict | None = None
    last_assessment: dict | None = None

    def record_user(self, text: str, *, local_only: bool = False) -> None:
        self.messages.append(LocalMessage(role="user", text=text, local_only=local_only))
        self._persist_message_to_db("user", text, local_only=local_only)

    def record_assistant(self, text: str, *, local_only: bool = False) -> None:
        self.messages.append(
            LocalMessage(role="assistant", text=text, local_only=local_only)
        )
        self._persist_message_to_db("assistant", text, local_only=local_only)

    def clear(self) -> None:
        from ..pdf_images import delete_session_cache

        delete_session_cache(self.session_id)
        self._clear_db_session()
        self.messages.clear()
        self.workflow_runs = 0
        self.token_usage_hint.clear()
        self.clear_verification_cache()

    def save_verification(
        self,
        pdf_path: str | None,
        math_result: dict | None,
        spatial_result: dict | None,
        assessment: dict | None = None,
        *,
        pdf_image_paths: list[str] | None = None,
        dates_result: dict | None = None,
    ) -> None:
        self.last_pdf_path = pdf_path
        self.last_math_result = math_result
        self.last_spatial_result = spatial_result
        if dates_result is not None:
            self.last_dates_result = dates_result
        if pdf_image_paths is not None:
            self.last_pdf_image_paths = list(pdf_image_paths)
        if assessment is not None:
            self.last_assessment = assessment
        self._persist_verification_to_db(
            pdf_path,
            math_result,
            spatial_result,
            assessment,
            pdf_image_paths=pdf_image_paths,
        )

    def save_pdf_images(self, image_paths: list[str]) -> None:
        self.last_pdf_image_paths = list(image_paths)

    def clear_verification_cache(self) -> None:
        self.last_pdf_path = None
        self.last_pdf_image_paths = []
        self.last_math_result = None
        self.last_spatial_result = None
        self.last_dates_result = None
        self.last_assessment = None

    def _memory_has_verification_cache(self) -> bool:
        return bool(
            self.last_pdf_path
            and self.last_math_result is not None
            and self.last_spatial_result is not None
        )

    def load_verification_from_db(self) -> bool:
        from ..db.config import db_enabled

        if not db_enabled():
            return False
        try:
            from ..db.store import get_verification_store

            record = get_verification_store().get_latest(self.session_id)
        except Exception as exc:
            logger.warning("Failed to load verification from SQLite: %s", exc)
            return False
        if record is None:
            return False
        self.last_pdf_path = record.pdf_path
        self.last_math_result = record.math_result
        self.last_spatial_result = record.spatial_result
        if record.assessment is not None:
            self.last_assessment = record.assessment
        if record.pdf_image_paths:
            self.last_pdf_image_paths = list(record.pdf_image_paths)
        return self._memory_has_verification_cache()

    def ensure_verification_loaded(self) -> bool:
        if self._memory_has_verification_cache():
            return True
        return self.load_verification_from_db()

    def has_verification_cache(self) -> bool:
        return self.ensure_verification_loaded()

    def _persist_message_to_db(
        self, role: str, text: str, *, local_only: bool = False
    ) -> None:
        from ..db.config import db_enabled

        if not db_enabled():
            return
        try:
            from ..db.store import persist_message

            persist_message(self.session_id, role, text, local_only=local_only)
        except Exception as exc:
            logger.warning("Failed to persist message to SQLite: %s", exc)

    def _persist_verification_to_db(
        self,
        pdf_path: str | None,
        math_result: dict | None,
        spatial_result: dict | None,
        assessment: dict | None,
        *,
        pdf_image_paths: list[str] | None,
    ) -> None:
        from ..db.config import db_enabled

        if not db_enabled():
            return
        if math_result is None and spatial_result is None:
            return
        try:
            from ..db.store import get_verification_store

            get_verification_store().save_verification(
                self.session_id,
                pdf_path,
                math_result,
                spatial_result,
                assessment,
                pdf_image_paths=pdf_image_paths or self.last_pdf_image_paths or None,
            )
        except Exception as exc:
            logger.warning("Failed to persist verification to SQLite: %s", exc)

    def _clear_db_session(self) -> None:
        from ..db.config import db_enabled

        if not db_enabled():
            return
        try:
            from ..db.store import get_verification_store

            get_verification_store().clear_session(self.session_id)
        except Exception as exc:
            logger.warning("Failed to clear SQLite session rows: %s", exc)

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def model_facing_message_count(self) -> int:
        return sum(1 for m in self.messages if not m.local_only)


_SESSION = RuntimeSession()


def get_runtime_session() -> RuntimeSession:
    return _SESSION


def reset_runtime_session() -> RuntimeSession:
    global _SESSION
    _SESSION = RuntimeSession()
    return _SESSION
