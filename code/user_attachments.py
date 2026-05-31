"""Resolve PDF paths from ADK web uploads (inline_data / artifacts)."""

from __future__ import annotations

import base64
import binascii
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote
from urllib.parse import urlparse

from .intent import extract_pdf_path
from .pdf_images import session_cache_root

logger = logging.getLogger(__name__)

_UPLOAD_ARTIFACT_RE = re.compile(r'\[Uploaded Artifact:\s*"([^"]+)"\]', re.IGNORECASE)
_UPLOADED_FILE_RE = re.compile(r"Uploaded file:\s*(\S+)", re.IGNORECASE)


def _uploads_dir(session_id: str) -> Path:
    return session_cache_root(session_id) / "uploads"


def _safe_pdf_name(name: str) -> str:
    stem = Path(name).name or "upload.pdf"
    if not stem.lower().endswith(".pdf"):
        stem = f"{stem}.pdf"
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in stem)
    return safe or "upload.pdf"


def _save_pdf_bytes(session_id: str, filename: str, data: bytes) -> str:
    out_dir = _uploads_dir(session_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / _safe_pdf_name(filename)
    out_path.write_bytes(data)
    return str(out_path)


def _decode_inline_data(data: Any) -> bytes | None:
    if data is None:
        return None
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if isinstance(data, str):
        try:
            return base64.b64decode(data, validate=True)
        except (binascii.Error, ValueError):
            try:
                return base64.urlsafe_b64decode(data)
            except (binascii.Error, ValueError):
                return data.encode("utf-8")
    return None


def _is_pdf_mime(mime_type: str | None) -> bool:
    if not mime_type:
        return False
    normalized = mime_type.split(";", 1)[0].strip().lower()
    return normalized == "application/pdf" or normalized.endswith("+pdf")


def _part_field(part: Any, name: str) -> Any:
    if isinstance(part, dict):
        return part.get(name)
    if hasattr(part, "model_dump"):
        dumped = part.model_dump() or {}
        if isinstance(dumped, dict):
            return dumped.get(name)
    return getattr(part, name, None)


def _inline_pdf_from_part(part: Any) -> tuple[str | None, bytes] | None:
    inline = _part_field(part, "inline_data")
    if inline is None:
        return None
    mime = _part_field(inline, "mime_type")
    if not _is_pdf_mime(mime):
        return None
    data = _decode_inline_data(_part_field(inline, "data"))
    if not data:
        return None
    display_name = _part_field(inline, "display_name") or "upload.pdf"
    return display_name, data


def _file_uri_to_path(uri: str) -> Path | None:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    path = Path(unquote(parsed.path))
    if path.is_file():
        return path
    # Windows file URIs may look like /C:/path
    alt = Path(unquote(uri.replace("file://", "", 1)))
    return alt if alt.is_file() else None


def _file_pdf_from_part(part: Any) -> str | None:
    file_data = _part_field(part, "file_data")
    if file_data is None:
        return None
    mime = _part_field(file_data, "mime_type")
    display_name = _part_field(file_data, "display_name") or ""
    uri = _part_field(file_data, "file_uri") or ""
    if not _is_pdf_mime(mime) and not display_name.lower().endswith(".pdf"):
        return None
    if uri:
        resolved = _file_uri_to_path(uri)
        if resolved is not None:
            return str(resolved)
    return None


def _artifact_names_from_text(text: str) -> list[str]:
    names: list[str] = []
    for pattern in (_UPLOAD_ARTIFACT_RE, _UPLOADED_FILE_RE):
        names.extend(pattern.findall(text or ""))
    return names


async def resolve_pdf_from_user_content(
    user_content: Any,
    *,
    session_id: str,
    adk_context: Any | None = None,
) -> str | None:
    """Return a local PDF path from message text, inline upload, or ADK artifact."""
    text_parts: list[str] = []
    if user_content is None:
        return None

    parts = _part_field(user_content, "parts")
    if not parts and isinstance(user_content, str):
        return extract_pdf_path(user_content)

    if parts:
        for part in parts:
            chunk = _part_field(part, "text")
            if chunk:
                text_parts.append(str(chunk))

            inline_pdf = _inline_pdf_from_part(part)
            if inline_pdf is not None:
                name, data = inline_pdf
                try:
                    return _save_pdf_bytes(session_id, name, data)
                except OSError as exc:
                    logger.warning("Failed to save uploaded PDF %s: %s", name, exc)

            file_pdf = _file_pdf_from_part(part)
            if file_pdf:
                return file_pdf

    combined_text = "".join(text_parts).strip()
    path_in_text = extract_pdf_path(combined_text)
    if path_in_text:
        return path_in_text

    if adk_context is None or not hasattr(adk_context, "load_artifact"):
        return None

    for artifact_name in _artifact_names_from_text(combined_text):
        try:
            artifact = await adk_context.load_artifact(artifact_name)
        except Exception as exc:
            logger.warning("Failed to load artifact %s: %s", artifact_name, exc)
            continue
        inline_pdf = _inline_pdf_from_part(artifact)
        if inline_pdf is not None:
            name, data = inline_pdf
            try:
                return _save_pdf_bytes(session_id, name or artifact_name, data)
            except OSError as exc:
                logger.warning("Failed to save artifact PDF %s: %s", artifact_name, exc)

    return None
