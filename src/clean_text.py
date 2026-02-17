from __future__ import annotations

from src.text_clean_chunk import clean_and_chunk


def clean_extracted_text(text: str) -> str:
    """
    Legacy compatibility wrapper.

    Canonical cleaning lives in `src.text_clean_chunk.clean_and_chunk`.
    """
    if not isinstance(text, str):
        return ""
    original = text.strip()
    if not original:
        return ""
    cleaned = clean_and_chunk(original).get("clean_text", "").strip()
    return cleaned or original
