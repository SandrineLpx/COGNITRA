from __future__ import annotations
from typing import Tuple

def extract_text_robust(pdf_bytes: bytes, min_chars: int = 500) -> Tuple[str, str]:
    """Return (text, method). Selectable-text PDFs: try PyMuPDF then fallback to pdfplumber."""
    # Lazy imports so the app can start even if deps aren't installed yet.
    try:
        import fitz  # pymupdf
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = "\n".join(page.get_text("text") for page in doc)
    except Exception:
        text = ""

    if len(text.strip()) >= min_chars:
        return text, "pymupdf"

    try:
        import io
        import pdfplumber
        parts = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                parts.append(page.extract_text() or "")
        text2 = "\n".join(parts)
        if len(text2.strip()) > len(text.strip()):
            return text2, "pdfplumber"
    except Exception:
        pass

    return text, "pymupdf"
