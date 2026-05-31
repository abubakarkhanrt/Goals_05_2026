"""Tests for PDF page image rendering and session cache."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

from code.pdf_images import delete_session_cache, ensure_pdf_images, pdf_slug
from code.runtime.session import reset_runtime_session


def _make_sample_pdf(path: Path, *, pages: int = 2) -> None:
    doc = fitz.open()
    for index in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Transcript page {index + 1}")
    doc.save(str(path))
    doc.close()


class TestPdfImages(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self._tmpdir.name) / "cache"
        self.pdf_path = Path(self._tmpdir.name) / "sample.pdf"
        _make_sample_pdf(self.pdf_path, pages=2)
        self.session_id = reset_runtime_session().session_id

    def tearDown(self):
        delete_session_cache(self.session_id)
        self._tmpdir.cleanup()

    def test_pdf_slug_is_stable(self):
        slug_a = pdf_slug(str(self.pdf_path))
        slug_b = pdf_slug(str(self.pdf_path))
        self.assertEqual(slug_a, slug_b)

    def test_ensure_pdf_images_creates_png_pages(self):
        with patch.dict("os.environ", {"SESSION_CACHE_DIR": str(self.cache_dir)}):
            paths = ensure_pdf_images(str(self.pdf_path), self.session_id)

        self.assertEqual(len(paths), 2)
        for path in paths:
            self.assertTrue(Path(path).is_file())
            self.assertTrue(path.endswith(".png"))

    def test_ensure_pdf_images_reuses_cache(self):
        with patch.dict("os.environ", {"SESSION_CACHE_DIR": str(self.cache_dir)}):
            first = ensure_pdf_images(str(self.pdf_path), self.session_id)
            second = ensure_pdf_images(str(self.pdf_path), self.session_id)

        self.assertEqual(first, second)

    def test_delete_session_cache_removes_images(self):
        with patch.dict("os.environ", {"SESSION_CACHE_DIR": str(self.cache_dir)}):
            ensure_pdf_images(str(self.pdf_path), self.session_id)
            delete_session_cache(self.session_id)

        self.assertFalse((self.cache_dir / self.session_id).exists())


if __name__ == "__main__":
    unittest.main()
