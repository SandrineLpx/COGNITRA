from __future__ import annotations

from src.text_clean_chunk import clean_and_chunk


def clean_text_for_llm(raw_text: str) -> str:
    """
    Legacy compatibility wrapper.

    Canonical cleaning lives in `src.text_clean_chunk.clean_and_chunk`.
    """
    if not isinstance(raw_text, str):
        return ""

    original = raw_text.strip()
    if not original:
        return ""

    cleaned = clean_and_chunk(original).get("clean_text", "").strip()

    # Keep historical safety behavior to avoid over-cleaning long inputs.
    if len(cleaned) < 2000 and len(original) >= 2000:
        return original
    return cleaned or original
