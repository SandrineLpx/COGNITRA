from __future__ import annotations
from typing import Optional, Tuple
from datetime import datetime
import re

_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def _parse_month(token: str) -> Optional[int]:
    return _MONTHS.get(str(token).strip().lower().rstrip("."))


def _to_iso(year: int, month: int, day: int) -> Optional[str]:
    try:
        return datetime(year, month, day).strftime("%Y-%m-%d")
    except Exception:
        return None


def _extract_header_publish_date_iso(text: str, max_lines: int = 60) -> Optional[str]:
    if not isinstance(text, str) or not text.strip():
        return None

    header_lines = text.splitlines()[:max_lines]
    mdy = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),\s*(\d{4})\b")
    dmy = re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\.?\s+(\d{4})\b")
    iso = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

    def _is_fiscal_year_end(year: int, month: int, day: int) -> bool:
        """Filter out common fiscal year-end dates (Dec 31) that aren't publication dates."""
        return month == 12 and day == 31

    for line in header_lines:
        m_iso = iso.search(line)
        if m_iso:
            year, month, day = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
            if not _is_fiscal_year_end(year, month, day):
                parsed = _to_iso(year, month, day)
                if parsed:
                    return parsed

        m_mdy = mdy.search(line)
        if m_mdy:
            month = _parse_month(m_mdy.group(1))
            if month:
                year, day = int(m_mdy.group(3)), int(m_mdy.group(2))
                if not _is_fiscal_year_end(year, month, day):
                    parsed = _to_iso(year, month, day)
                    if parsed:
                        return parsed

        m_dmy = dmy.search(line)
        if m_dmy:
            month = _parse_month(m_dmy.group(2))
            if month:
                year, day = int(m_dmy.group(3)), int(m_dmy.group(1))
                if not _is_fiscal_year_end(year, month, day):
                    parsed = _to_iso(year, month, day)
                    if parsed:
                        return parsed

    return None


def _parse_pdf_metadata_date(value: Optional[str]) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()

    m_pdf = re.search(r"D:(\d{4})(\d{2})(\d{2})", raw)
    if m_pdf:
        parsed = _to_iso(int(m_pdf.group(1)), int(m_pdf.group(2)), int(m_pdf.group(3)))
        if parsed:
            return parsed

    m_iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", raw)
    if m_iso:
        parsed = _to_iso(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)))
        if parsed:
            return parsed

    return None


def _extract_pdf_metadata_publish_date_iso(pdf_bytes: bytes) -> Optional[str]:
    if not pdf_bytes:
        return None
    try:
        import fitz  # pymupdf

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        meta = doc.metadata or {}
        for key in ("creationDate", "CreationDate", "modDate", "ModDate"):
            parsed = _parse_pdf_metadata_date(meta.get(key))
            if parsed:
                return parsed
    except Exception:
        return None
    return None


def extract_pdf_publish_date_hint(
    pdf_bytes: bytes,
    extracted_text: str = "",
    metadata_date_hint: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Return (publish_date_iso, source_tag) with priority:
    1) top-of-document visible header date from extracted text
    2) PDF metadata date (creation/modification date)
    """
    header_date = _extract_header_publish_date_iso(extracted_text)
    if header_date:
        return header_date, "pdf_header_publish_date"

    parsed_hint = _parse_pdf_metadata_date(metadata_date_hint)
    if parsed_hint:
        return parsed_hint, "pdf_metadata_publish_date"

    meta_date = _extract_pdf_metadata_publish_date_iso(pdf_bytes)
    if meta_date:
        return meta_date, "pdf_metadata_publish_date"

    return None, None

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


def _short_exception(exc: Exception, max_len: int = 180) -> str:
    line = (str(exc) or exc.__class__.__name__).strip().splitlines()[0]
    if len(line) <= max_len:
        return line
    return line[: max_len - 3].rstrip() + "..."


def explain_no_text_extraction(pdf_bytes: bytes) -> str:
    """Return a deterministic reason when PDF text extraction yields an empty string."""
    size_bytes = len(pdf_bytes or b"")
    if size_bytes == 0:
        return "The file is empty (0 bytes)."

    pymupdf_chars = 0
    pymupdf_pages = 0
    pymupdf_error: Optional[str] = None
    encrypted = False

    try:
        import fitz  # pymupdf

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            pymupdf_pages = len(doc)
            encrypted = bool(getattr(doc, "needs_pass", False))
            if not encrypted:
                text = "\n".join(page.get_text("text") or "" for page in doc)
                pymupdf_chars = len(text.strip())
        finally:
            doc.close()
    except Exception as exc:
        pymupdf_error = _short_exception(exc)

    pdfplumber_chars = 0
    pdfplumber_pages = 0
    pdfplumber_error: Optional[str] = None
    try:
        import io
        import pdfplumber

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pdfplumber_pages = len(pdf.pages)
            parts = [(p.extract_text() or "") for p in pdf.pages]
            pdfplumber_chars = len("\n".join(parts).strip())
    except Exception as exc:
        pdfplumber_error = _short_exception(exc)

    if encrypted:
        return "The PDF is password-protected/encrypted, so text extraction is blocked."

    if pymupdf_error and pdfplumber_error:
        return (
            "Both PDF extractors failed to parse this file "
            f"(PyMuPDF: {pymupdf_error}; pdfplumber: {pdfplumber_error})."
        )

    best_chars = max(pymupdf_chars, pdfplumber_chars)
    best_pages = max(pymupdf_pages, pdfplumber_pages)

    if best_chars == 0:
        if best_pages > 0:
            return (
                f"No selectable text layer was found across {best_pages} page(s); "
                "this is likely a scanned/image-only PDF."
            )
        return "No selectable text layer was found."

    return (
        "Only whitespace text was extracted "
        f"(PyMuPDF={pymupdf_chars} chars, pdfplumber={pdfplumber_chars} chars)."
    )
