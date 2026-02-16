from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Tuple

# Config
JUNK_PATTERNS = {
    "nav": [
        r"subscribe",
        r"sign in",
        r"log in",
        r"newsletter",
        r"cookie",
        r"privacy policy",
        r"\bterms\b",
        r"contact us",
        r"follow us",
    ],
    "promo": [
        r"advertisement",
        r"sponsored",
        r"promoted",
        r"our partners",
    ],
    "related": [
        r"related articles?",
        r"recommended",
        r"read next",
        r"you may also like",
    ],
    "social": [
        r"share on",
        r"\bfacebook\b",
        r"\btwitter\b",
        r"\blinkedin\b",
        r"copy link",
    ],
    "paywall": [
        r"already a subscriber",
        r"create an account",
        r"for unlimited access",
        r"subscribe to continue",
    ],
}

URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
PHOTO_CREDIT_RE = re.compile(r"\b(photo|credit|getty|stock|source)\b", re.IGNORECASE)
PUBLISH_TS_RE = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|"
    r"January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},\s+\d{4}\s+at\s+\d{1,2}:\d{2}\s*(?:AM|PM)\s*"
    r"(?:PST|PDT|EST|EDT|CST|CDT|MST|MDT|UTC|GMT)\b",
    re.IGNORECASE,
)


def _fix_hyphen_breaks(text: str) -> str:
    return re.sub(r"([A-Za-z])-\s*\n\s*([A-Za-z])", r"\1\2", text)


def _normalize_text(raw_text: str) -> str:
    txt = _fix_hyphen_breaks(raw_text or "")
    txt = txt.replace("\r\n", "\n").replace("\r", "\n")
    txt = re.sub(r"[ \t]+", " ", txt)
    return txt


def _normalize_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def _title_caseish(line: str) -> bool:
    words = re.findall(r"[A-Za-z][A-Za-z\-']*", line)
    if not (6 <= len(words) <= 20):
        return False
    up = sum(1 for w in words if w[:1].isupper())
    all_caps = sum(1 for w in words if w.isupper())
    return (up / len(words) >= 0.55) and (all_caps / len(words) < 0.7)


def _detect_title(lines: List[str]) -> str:
    for line in lines[:40]:
        ln = _normalize_line(line)
        if not ln:
            continue
        if URL_RE.search(ln):
            continue
        if " - " in ln and 6 <= len(ln.split()) <= 30:
            return ln
        if _title_caseish(ln):
            return ln
    return ""


def _line_is_table_fact(line: str) -> bool:
    return bool(re.search(r"\d", line) and ("|" in line or re.search(r"\s{2,}", line)))


def _looks_like_publish_timestamp(line: str) -> bool:
    return bool(PUBLISH_TS_RE.search(line))


def _non_letter_ratio(line: str) -> float:
    s = re.sub(r"\s+", "", line)
    if not s:
        return 0.0
    non_letters = sum(1 for c in s if not c.isalpha())
    return non_letters / len(s)


def _is_short_allcaps_menu(line: str) -> bool:
    words = re.findall(r"[A-Za-z]+", line)
    if not words:
        return False
    if len(words) > 6 or len(line) > 60:
        return False
    letters = "".join(words)
    return letters.isupper()


def _match_pattern_group(line_l: str) -> str:
    for group, patterns in JUNK_PATTERNS.items():
        for p in patterns:
            if re.search(p, line_l, re.IGNORECASE):
                return group
    return ""


def _trim_word_boundary(text: str, start_idx: int) -> str:
    if start_idx <= 0:
        return text
    i = start_idx
    n = len(text)
    while i < n and i > 0 and text[i - 1].isalnum() and text[i].isalnum():
        i += 1
    return text[i:]


def _build_chunks(clean_text: str, detected_title: str, max_chars_per_chunk: int, overlap_chars: int) -> List[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n+", clean_text) if p.strip()]
    if not paras:
        return []

    header_lines = 3
    header_template = "CHUNK {i}/{n}\nDOC TITLE (if detected): {t}\nIMPORTANT: Use only this chunk.\n\n"
    reserve = len(header_template.format(i=1, n=1, t=detected_title or "")) + 32
    body_limit = max(1000, max_chars_per_chunk - reserve)

    bodies: List[str] = []
    cur: List[str] = []
    cur_len = 0
    for p in paras:
        add = len(p) + (2 if cur else 0)
        if cur and (cur_len + add > body_limit):
            bodies.append("\n\n".join(cur))
            cur = [p]
            cur_len = len(p)
        else:
            cur.append(p)
            cur_len += add
    if cur:
        bodies.append("\n\n".join(cur))

    with_overlap: List[str] = []
    for i, body in enumerate(bodies):
        if i == 0:
            with_overlap.append(body)
            continue
        prev = with_overlap[-1]
        tail_start = max(0, len(prev) - overlap_chars)
        tail = _trim_word_boundary(prev, tail_start).strip()
        if tail:
            with_overlap.append(f"{tail}\n\n{body}")
        else:
            with_overlap.append(body)

    n = len(with_overlap)
    chunks = []
    for i, body in enumerate(with_overlap, 1):
        header = header_template.format(i=i, n=n, t=detected_title or "")
        chunks.append(header + body)
    return chunks


def clean_and_chunk(raw_text: str, *, max_chars_per_chunk: int = 9000, overlap_chars: int = 800) -> Dict[str, Any]:
    raw = raw_text or ""
    norm = _normalize_text(raw)
    raw_lines = norm.split("\n")
    detected_title = _detect_title(raw_lines)

    norm_lines = [_normalize_line(x) for x in raw_lines]
    norm_lines = [x for x in norm_lines if x]

    # Remove repeated header/footer-like lines.
    counts = Counter(norm_lines)
    many_threshold = max(3, int(len(norm_lines) * 0.015))
    repeated = {ln for ln, c in counts.items() if c >= many_threshold}

    removed_line_count = 0
    removed_pattern_counts: Counter[str] = Counter()
    cleaned_lines: List[str] = []
    kept_short_caps_in_top = False

    for idx, ln in enumerate(norm_lines):
        ln_l = ln.lower()
        drop_reason = ""

        if ln in repeated and len(ln.split()) <= 12:
            drop_reason = "repeated_header_footer"
        elif URL_RE.findall(ln_l) and len(URL_RE.findall(ln_l)) >= 2:
            drop_reason = "link_heavy"
        elif _non_letter_ratio(ln) > 0.35 and not _line_is_table_fact(ln) and not _looks_like_publish_timestamp(ln):
            drop_reason = "symbol_heavy"
        else:
            g = _match_pattern_group(ln_l)
            if g:
                drop_reason = g

        if not drop_reason and PHOTO_CREDIT_RE.search(ln_l):
            if len(ln.split()) < 8:
                drop_reason = "image_credit_short"

        if not drop_reason and _is_short_allcaps_menu(ln):
            if idx < 20 and not kept_short_caps_in_top:
                kept_short_caps_in_top = True
            else:
                drop_reason = "short_allcaps_menu"

        if drop_reason:
            removed_line_count += 1
            removed_pattern_counts[drop_reason] += 1
            continue

        cleaned_lines.append(ln)

    # Preserve paragraph-like structure.
    clean_text = "\n".join(cleaned_lines)
    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text).strip()
    chunks = _build_chunks(clean_text, detected_title, max_chars_per_chunk, overlap_chars)

    meta = {
        "raw_chars": len(raw),
        "clean_chars": len(clean_text),
        "removed_chars": max(0, len(raw) - len(clean_text)),
        "removed_line_count": removed_line_count,
        "chunks_count": len(chunks),
        "detected_title": detected_title,
        "top_removed_patterns": removed_pattern_counts.most_common(8),
        "chunk_ids": [f"{i+1}/{len(chunks)}" for i in range(len(chunks))],
    }
    return {"clean_text": clean_text, "chunks": chunks, "meta": meta}
