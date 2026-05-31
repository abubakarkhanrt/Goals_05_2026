"""
OCR fallback for image-based (scanned) PDFs.
Uses Tesseract via pytesseract. Requires Tesseract to be installed on the system
(e.g. apt install tesseract-ocr, or https://github.com/tesseract-ocr/tesseract).
"""

from pathlib import Path

import fitz  # PyMuPDF

try:
    import pytesseract
    from PIL import Image
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False

# Minimum text length from native PDF to skip OCR (avoid running OCR on digital PDFs)
_MIN_NATIVE_TEXT_LEN = 50


def is_ocr_available() -> bool:
    """Return True if pytesseract and Pillow are installed and Tesseract is on PATH."""
    if not _OCR_AVAILABLE:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def ocr_pdf_to_text(pdf_path: str) -> str:
    """
    Run OCR on each page of an image-based PDF and return concatenated text.
    Each page is rendered to an image, then passed to Tesseract.
    Returns empty string on error or if OCR is not available.
    """
    if not _OCR_AVAILABLE or not is_ocr_available():
        return ""
    path = Path(pdf_path)
    if not path.exists():
        return ""
    try:
        doc = fitz.open(pdf_path)
        parts = []
        for page in doc:
            pix = page.get_pixmap(dpi=150, alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = pytesseract.image_to_string(img)
            if text:
                parts.append(text)
        doc.close()
        return "\n".join(parts)
    except Exception:
        return ""


def ocr_pdf_to_spans(pdf_path: str) -> list[dict]:
    """
    Run OCR on each page and return word-level spans with bbox and text.
    Format matches _extract_spans_from_pdf: {"bbox": (x0,y0,x1,y1), "text": str, "font": "", "size": 0}.
    Font/size are not available from Tesseract and are left empty/zero.
    """
    if not _OCR_AVAILABLE or not is_ocr_available():
        return []
    path = Path(pdf_path)
    if not path.exists():
        return []
    spans = []
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            pix = page.get_pixmap(dpi=150, alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            n = len(data.get("text", []))
            for i in range(n):
                text = (data.get("text") or [""])[i]
                if not (text and text.strip()):
                    continue
                left = data["left"][i]
                top = data["top"][i]
                w = data["width"][i]
                h = data["height"][i]
                # bbox in same order as PyMuPDF (x0, y0, x1, y1)
                bbox = (float(left), float(top), float(left + w), float(top + h))
                spans.append({
                    "bbox": bbox,
                    "text": text.strip(),
                    "font": "",
                    "size": 0.0,
                })
        doc.close()
    except Exception:
        pass
    return spans


def pdf_has_little_text(pdf_path: str) -> bool:
    """Return True if the PDF yields very little native text (likely scanned)."""
    try:
        doc = fitz.open(pdf_path)
        total = 0
        for page in doc:
            total += len(page.get_text() or "")
            if total >= _MIN_NATIVE_TEXT_LEN:
                doc.close()
                return False
        doc.close()
        return total < _MIN_NATIVE_TEXT_LEN
    except Exception:
        return True
