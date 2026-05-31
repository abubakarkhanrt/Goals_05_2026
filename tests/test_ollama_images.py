"""Tests for Ollama multimodal message building."""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from code.llm_shared import llm_image_paths, user_message_with_images, _read_image_bytes_for_llm


class TestOllamaImages(unittest.TestCase):
    def test_user_message_without_images_is_plain_text(self):
        message = user_message_with_images("hello", [])
        self.assertEqual(message, "hello")

    def test_user_message_with_images_builds_parts(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            Image.new("RGB", (8, 8), color="white").save(tmp, format="PNG")
            path = tmp.name

        try:
            message = user_message_with_images("analyze", [path])
            assert isinstance(message, list)
            self.assertEqual(message[0]["type"], "text")
            self.assertEqual(message[1]["type"], "image_url")
            self.assertIn("base64", message[1]["image_url"]["url"])
        finally:
            Path(path).unlink(missing_ok=True)

    def test_missing_image_paths_are_skipped(self):
        message = user_message_with_images("analyze", ["/does/not/exist.png"])
        self.assertEqual(message, "analyze")

    def test_llm_image_paths_respects_send_images_flag(self):
        with patch.dict("os.environ", {"OLLAMA_SEND_IMAGES": "false"}):
            self.assertEqual(llm_image_paths(["/tmp/a.png"]), [])

    def test_read_image_bytes_downscales_large_png(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            Image.new("RGB", (2000, 3000), color="white").save(tmp, format="PNG")
            path = tmp.name

        try:
            with patch.dict("os.environ", {"OLLAMA_IMAGE_MAX_EDGE": "1024"}):
                payload, mime = _read_image_bytes_for_llm(path)
            with Image.open(io.BytesIO(payload)) as img:
                self.assertLessEqual(max(img.size), 1024)
            self.assertEqual(mime, "image/png")
        finally:
            Path(path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
