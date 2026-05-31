"""Render PDF pages to PNG images stored per runtime session (LLM vision path only).

Tools (verify_transcript_math, verify_transcript_spatial) read the original PDF file.
These PNGs are attached to Ollama for visual assessment and Q&A — not fed back into tools.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path

import fitz  # PyMuPDF

from .llm_config import pdf_max_pages, pdf_render_dpi, session_cache_dir

logger = logging.getLogger(__name__)


def session_cache_root(session_id: str) -> Path:
    return session_cache_dir() / session_id


def session_images_root(session_id: str) -> Path:
    return session_cache_root(session_id) / "images"


def pdf_slug(pdf_path: str) -> str:
    resolved = str(Path(pdf_path).resolve())
    digest = hashlib.sha256(resolved.encode()).hexdigest()[:12]
    stem = Path(pdf_path).stem[:40] or "document"
    safe_stem = "".join(c if c.isalnum() or c in "-_" else "_" for c in stem)
    return f"{safe_stem}_{digest}"


def _pdf_output_dir(session_id: str, pdf_path: str) -> Path:
    return session_images_root(session_id) / pdf_slug(pdf_path)


def _manifest_path(output_dir: Path) -> Path:
    return output_dir / "manifest.txt"


def _read_manifest(output_dir: Path) -> dict[str, str]:
    manifest = _manifest_path(output_dir)
    if not manifest.is_file():
        return {}
    data: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()
    return data


def _write_manifest(output_dir: Path, pdf_path: Path, *, page_count: int) -> None:
    _manifest_path(output_dir).write_text(
        "\n".join(
            [
                f"source={pdf_path.resolve()}",
                f"mtime={pdf_path.stat().st_mtime}",
                f"pages={page_count}",
                f"dpi={pdf_render_dpi()}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _cached_images_valid(output_dir: Path, pdf_path: Path) -> list[str] | None:
    if not output_dir.is_dir():
        return None
    manifest = _read_manifest(output_dir)
    if manifest.get("source") != str(pdf_path.resolve()):
        return None
    try:
        if float(manifest.get("mtime", "-1")) != pdf_path.stat().st_mtime:
            return None
    except ValueError:
        return None
    images = sorted(output_dir.glob("page-*.png"))
    if not images:
        return None
    return [str(p.resolve()) for p in images]


def ensure_pdf_images(
    pdf_path: str,
    session_id: str,
    *,
    force: bool = False,
) -> list[str]:
    """
    Render PDF pages to PNG under `.session_cache/<session_id>/images/...`.
    Returns absolute paths to page images (reuses cache when PDF unchanged).
    """
    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    output_dir = _pdf_output_dir(session_id, str(path))
    if not force:
        cached = _cached_images_valid(output_dir, path)
        if cached is not None:
            logger.info("Reusing %d cached PDF page image(s) from %s", len(cached), output_dir)
            return cached

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    dpi = pdf_render_dpi()
    max_pages = pdf_max_pages()
    doc = fitz.open(str(path))
    page_count = min(len(doc), max_pages)
    image_paths: list[str] = []

    for index in range(page_count):
        page = doc[index]
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        png_path = output_dir / f"page-{index + 1:03d}.png"
        pix.save(str(png_path))
        image_paths.append(str(png_path.resolve()))

    doc.close()
    _write_manifest(output_dir, path, page_count=len(image_paths))
    logger.info(
        "Rendered %d PDF page image(s) at %s dpi -> %s",
        len(image_paths),
        dpi,
        output_dir,
    )
    return image_paths


def delete_session_cache(session_id: str) -> None:
    root = session_cache_root(session_id)
    if root.is_dir():
        shutil.rmtree(root, ignore_errors=True)
