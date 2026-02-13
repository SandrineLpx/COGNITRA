from __future__ import annotations

import re
from collections import Counter
from typing import List

_DROP_PATTERNS = [
    re.compile(r"publishing partner:", re.IGNORECASE),
    re.compile(r"recommended for you", re.IGNORECASE),
    re.compile(r"sign up for", re.IGNORECASE),
    re.compile(r"^\s*share\s*$", re.IGNORECASE),
]


def _normalize_lines(text: str) -> List[str]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: List[str] = []
    for line in lines:
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            out.append(line)
    return out


def _is_noise_line(line: str) -> bool:
    if re.search(r"https?://|www\.", line, flags=re.IGNORECASE):
        return True
    return any(p.search(line) for p in _DROP_PATTERNS)


def clean_extracted_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    if not text.strip():
        return ""

    lines = _normalize_lines(text)
    lines = [ln for ln in lines if not _is_noise_line(ln)]

    # Remove likely header/footer lines repeated across pages.
    counts = Counter(lines)
    lines = [ln for ln in lines if counts[ln] < 2]

    cleaned = "\n\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned or text.strip()


if __name__ == "__main__":
    sample = """
    Automotive News
    Publishing Partner: ACME
    Sign up for alerts
    Share
    https://example.com/story
    Core editorial paragraph one.
    Automotive News
    Core editorial paragraph two.
    Recommended For You
    www.example.org
    """
    out = clean_extracted_text(sample)
    assert "Publishing Partner:" not in out
    assert "Recommended For You" not in out
    assert "https://example.com/story" not in out
    assert "Core editorial paragraph one." in out
    assert "Core editorial paragraph two." in out
