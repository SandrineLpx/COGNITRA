from __future__ import annotations

from collections import Counter
import re
from typing import List

NOISE_SUBSTRINGS = [
    "advertisement",
    "sponsored",
    "subscribe",
    "sign in",
    "already a subscriber",
    "read more:",
    "related articles",
    "most popular",
    "recommended",
    "click here",
    "privacy policy",
    "terms of service",
    "cookie",
    "consent",
    "all rights reserved",
    "no portion of this report may be reproduced",
]

NAV_WORDS = {
    "home", "news", "analysis", "markets", "industry", "business", "latest", "video",
    "podcast", "opinion", "careers", "contact", "about", "search", "menu", "login",
}


def _normalize_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def _is_link_heavy_line(line: str) -> bool:
    lower = line.lower()
    url_hits = len(re.findall(r"https?://|www\.", lower))
    if url_hits == 0:
        return False
    words = re.findall(r"[A-Za-z0-9]+", line)
    # Mostly URL-like and little regular text.
    return url_hits >= 1 and len(words) <= 8


def _looks_nav_line(line: str) -> bool:
    words = re.findall(r"[A-Za-z]+", line)
    if not words:
        return False
    if len(words) > 8:
        return False
    title_or_upper = sum(1 for w in words if w[:1].isupper() or w.isupper())
    navish = sum(1 for w in words if w.lower() in NAV_WORDS)
    return (title_or_upper / len(words) >= 0.7) or (navish / len(words) >= 0.5)


def _line_is_noise(line: str) -> bool:
    lower = line.lower()
    if any(s in lower for s in NOISE_SUBSTRINGS):
        return True
    if _is_link_heavy_line(line):
        return True
    if len(line) <= 80 and _looks_nav_line(line):
        return True
    return False


def _split_blocks(text: str) -> List[str]:
    blocks = re.split(r"\n{2,}", text)
    return [b.strip() for b in blocks if b.strip()]


def clean_text_for_llm(raw_text: str) -> str:
    """Conservative cleanup for noisy PDF extraction before context selection."""
    if not isinstance(raw_text, str):
        return ""

    original = raw_text.strip()
    if not original:
        return ""

    # 1) Line normalization + drop empties.
    raw_lines = original.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    norm_lines = [_normalize_line(x) for x in raw_lines]
    norm_lines = [x for x in norm_lines if x]

    # 2) Remove obvious line-level noise.
    filtered = [x for x in norm_lines if not _line_is_noise(x)]

    # 3) Remove repeating header/footer lines (>=3), with conservative keep for short title-like lines.
    counts = Counter(filtered)
    kept: List[str] = []
    for line in filtered:
        c = counts[line]
        if c >= 3:
            shortish = len(line) <= 60
            looks_title = bool(re.match(r"^[A-Z][A-Za-z0-9&'(),:/\-]*(?: [A-Z][A-Za-z0-9&'(),:/\-]*)*$", line))
            if shortish and looks_title and c <= 4:
                kept.append(line)
            continue
        kept.append(line)

    # 4) Paragraph/block dedupe (exact match ignoring whitespace).
    text_once = "\n".join(kept)
    blocks = _split_blocks(text_once)
    deduped_blocks: List[str] = []
    seen = set()
    for b in blocks:
        key = re.sub(r"\s+", " ", b).strip().lower()
        if key in seen:
            continue
        seen.add(key)
        deduped_blocks.append(b)

    cleaned = "\n\n".join(deduped_blocks).strip()

    # 5) Safety fallback: avoid over-cleaning.
    if len(cleaned) < 2000 and len(original) >= 2000:
        return original
    return cleaned or original
