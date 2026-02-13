from __future__ import annotations

from typing import Any, Dict, List
import re

PUBLISHER_MARKERS = [
    "s&p global",
    "autointelligence",
    "marklines",
    "automotive news",
    "reuters",
    "bloomberg",
]

COPYRIGHT_MARKERS = [
    "©",
    "no portion of this report may be reproduced",
]

NOISE_MARKERS = [
    "recommended for you",
    "publishing partner",
    "subscribe",
    "sign in",
    "newsletter",
    "cookie",
    "terms",
    "privacy",
]

NAV_WORDS = {
    "home", "news", "markets", "opinion", "video", "contact", "about",
    "login", "register", "more", "menu", "search", "latest", "topics",
}

DATE_PATTERNS = [
    re.compile(r"\b20\d{2}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+20\d{2}\b", re.I),
    re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+\d{1,2},\s+20\d{2}\b", re.I),
    re.compile(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+20\d{2}\b", re.I),
]

NUMERIC_MARKERS = ["$", "us$", "%", "million", "billion", "units"]


def split_into_chunks(text: str) -> List[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    chunks: List[str] = []

    for p in paras:
        if len(p) <= 1200:
            chunks.append(p)
            continue

        # Split long paragraphs into sentence-bounded chunks around 800-1200 chars.
        sents = re.split(r"(?<=[.!?])\s+", p)
        cur: List[str] = []
        cur_len = 0
        for s in sents:
            s = s.strip()
            if not s:
                continue
            s_len = len(s) + (1 if cur else 0)
            if cur and (cur_len + s_len > 1200):
                chunks.append(" ".join(cur).strip())
                cur = [s]
                cur_len = len(s)
            else:
                cur.append(s)
                cur_len += s_len
                if cur_len >= 800:
                    chunks.append(" ".join(cur).strip())
                    cur = []
                    cur_len = 0
        if cur:
            chunks.append(" ".join(cur).strip())

    return [c.strip() for c in chunks if c and c.strip()]


def _looks_like_nav_link_farm(chunk: str) -> bool:
    lines = [ln.strip() for ln in chunk.splitlines() if ln.strip()]
    if not lines:
        return False
    short_lines = sum(1 for ln in lines if len(ln) < 25)

    title_nav_lines = 0
    for ln in lines:
        words = [w for w in re.findall(r"[A-Za-z]+", ln)]
        if not words:
            continue
        if len(words) <= 5 and all((w.lower() in NAV_WORDS or w.istitle()) for w in words):
            title_nav_lines += 1

    return ((short_lines / len(lines)) > 0.4) or ((title_nav_lines / len(lines)) > 0.4)


def score_chunk(chunk: str, watch_terms: List[str], topic_terms: List[str]) -> Dict[str, Any]:
    text_l = chunk.lower()
    score = 0
    flags: List[str] = []

    if any(p.search(chunk) for p in DATE_PATTERNS):
        score += 5
        flags.append("date_marker")

    if any(m in text_l for m in PUBLISHER_MARKERS):
        score += 5
        flags.append("publisher_marker")

    if any(m in text_l for m in COPYRIGHT_MARKERS):
        score += 3
        flags.append("copyright_marker")

    if any(t and t.lower() in text_l for t in watch_terms):
        score += 3
        flags.append("watch_term")

    if any(t and t.lower() in text_l for t in topic_terms):
        score += 2
        flags.append("topic_term")

    if any(m in text_l for m in NUMERIC_MARKERS):
        score += 1
        flags.append("numeric_signal")

    if any(m in text_l for m in NOISE_MARKERS):
        score -= 5
        flags.append("noise_marker")

    if len(re.findall(r"https?://", text_l)) >= 2:
        score -= 3
        flags.append("many_urls")

    if _looks_like_nav_link_farm(chunk):
        score -= 3
        flags.append("nav_like")

    return {"score": score, "flags": flags}


def select_context_chunks(
    title: str,
    text: str,
    watch_terms: List[str],
    topic_terms: List[str],
    header_k: int = 2,
    body_k: int = 6,
    max_chars: int = 12000,
) -> Dict[str, Any]:
    chunks = split_into_chunks(text)
    scored: List[Dict[str, Any]] = []
    for idx, ch in enumerate(chunks):
        meta = score_chunk(ch, watch_terms, topic_terms)
        scored.append(
            {
                "idx": idx,
                "chunk": ch,
                "score": meta["score"],
                "flags": meta["flags"],
            }
        )

    header_candidates = [
        r
        for r in scored
        if (
            "date_marker" in r["flags"]
            or "publisher_marker" in r["flags"]
            or "copyright_marker" in r["flags"]
        )
    ]
    header_top = sorted(header_candidates, key=lambda r: (-r["score"], r["idx"]))[:header_k]
    header_ids = {r["idx"] for r in header_top}

    body_candidates = [r for r in scored if r["idx"] not in header_ids]
    body_top = sorted(body_candidates, key=lambda r: (-r["score"], r["idx"]))[:body_k]

    header_sel = sorted(header_top, key=lambda r: r["idx"])
    body_sel = sorted(body_top, key=lambda r: r["idx"])

    def render_pack(headers: List[Dict[str, Any]], bodies: List[Dict[str, Any]]) -> str:
        lines: List[str] = []
        lines.append(f"TITLE: {title}\n")
        lines.append("DOC_HEADER_CHUNKS:")
        for i, r in enumerate(headers, 1):
            lines.append(f"[H{i}] {r['chunk']}")
        lines.append("")
        lines.append("DOC_BODY_CHUNKS:")
        for i, r in enumerate(bodies, 1):
            lines.append(f"[B{i}] {r['chunk']}")
        lines.append("")
        lines.append("CONSTRAINTS:")
        lines.append("Use only these chunks. Ignore ads/sidebars/navigation.")
        return "\n".join(lines)

    context_pack = render_pack(header_sel, body_sel)
    while len(context_pack) > max_chars and body_sel:
        drop_idx = min(range(len(body_sel)), key=lambda i: (body_sel[i]["score"], -body_sel[i]["idx"]))
        body_sel.pop(drop_idx)
        context_pack = render_pack(header_sel, body_sel)

    if len(context_pack) > max_chars:
        context_pack = context_pack[:max_chars]

    return {
        "context_pack": context_pack,
        "header_chunks": header_sel,
        "body_chunks": body_sel,
        "all_scored_chunks": scored,
    }


def build_context_pack(
    title: str,
    text: str,
    watch_terms: List[str],
    topic_terms: List[str],
    header_k: int = 2,
    body_k: int = 6,
    max_chars: int = 12000,
) -> str:
    result = select_context_chunks(
        title=title,
        text=text,
        watch_terms=watch_terms,
        topic_terms=topic_terms,
        header_k=header_k,
        body_k=body_k,
        max_chars=max_chars,
    )
    return result["context_pack"]


if __name__ == "__main__":
    sample = """
Automotive News
Published: February 12, 2026

Recommended For You
Subscribe now and sign in for newsletter updates.

Ford and Geely expanded production in Valencia amid tariffs and supplier pressure.
The plan affects units and capacity across multiple plants.
"""
    watch = ["Ford", "Geely"]
    topics = ["tariff", "plant", "capacity", "joint venture", "platform", "EV", "battery", "latch", "door handle", "supplier", "production", "recall", "regulation"]
    result = select_context_chunks("Fake Test Doc", sample, watch, topics, header_k=2, body_k=4, max_chars=3000)
    print("HEADER CHUNKS:")
    for h in result["header_chunks"]:
        print(f"- score={h['score']} flags={h['flags']} text={h['chunk'][:120]}")
    print("\nBODY CHUNKS:")
    for b in result["body_chunks"]:
        print(f"- score={b['score']} flags={b['flags']} text={b['chunk'][:120]}")
    print("\nCONTEXT PACK:\n")
    print(result["context_pack"])
