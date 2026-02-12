from __future__ import annotations
import re
from typing import List, Tuple

DEFAULT_MAX_WORDS_HEAD = 1000
DEFAULT_TOP_PARAS = 8

CLOSURE_KEYWORDS = [
    "latch","cinch","cinching","handle","door module","window regulator",
    "smart entry","digital key","uwb","ultra-wideband","access","anti-theft"
]

def split_paragraphs(text: str) -> List[str]:
    text = re.sub(r"\n{3,}", "\n\n", text)
    return [p.strip() for p in text.split("\n\n") if p.strip()]

def score_paragraph(p: str, watch_terms: List[str], country_terms: List[str]) -> int:
    lp = p.lower()
    score = 0
    for t in watch_terms:
        if t and t.lower() in lp:
            score += 4
    for k in CLOSURE_KEYWORDS:
        if k in lp:
            score += 2
    for c in country_terms:
        if c and c.lower() in lp:
            score += 1
    return score

def build_context_pack(title: str, full_text: str, watch_terms: List[str], country_terms: List[str],
                       max_head_words: int = DEFAULT_MAX_WORDS_HEAD, top_paras: int = DEFAULT_TOP_PARAS) -> str:
    paras = split_paragraphs(full_text)
    head_words = " ".join(full_text.split()[:max_head_words])

    scored: List[Tuple[int, str]] = []
    for p in paras:
        s = score_paragraph(p, watch_terms, country_terms)
        if s > 0:
            scored.append((s, p))
    scored.sort(key=lambda x: x[0], reverse=True)

    top = [p for _, p in scored[:top_paras]]

    pack = []
    pack.append(f"TITLE: {title}\n")
    pack.append("HEAD (first section):\n")
    pack.append(head_words + "\n")
    if top:
        pack.append("\nTOP HIT PARAGRAPHS:\n")
        for i, p in enumerate(top, 1):
            pack.append(f"[P{i}] {p}\n")
    return "\n".join(pack)
