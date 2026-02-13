from __future__ import annotations

import re
from copy import deepcopy
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Set, Tuple

STOPWORDS = {
    "report",
    "analysis",
    "outlook",
    "perspective",
    "headline",
    "update",
    "exclusive",
    "interview",
}

PUBLISHER_SCORE = {
    "S&P": 100,
    "Reuters": 95,
    "Bloomberg": 93,
    "Automotive News": 90,
    "MarkLines": 85,
    "Press Release": 75,
    "Patent": 70,
    "Other": 60,
}


def normalize_title(title: str) -> str:
    t = (title or "").lower()
    t = re.sub(r"\bin talks\b", " ", t)
    t = re.sub(r"\breport says\b", " ", t)
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    toks = [tok for tok in t.split() if tok and tok not in STOPWORDS]
    return " ".join(toks)


def token_set(title: str) -> Set[str]:
    return set(normalize_title(title).split())


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _norm_items(values: object, limit: int = 999) -> List[str]:
    if not isinstance(values, list):
        return []
    out: List[str] = []
    seen = set()
    for v in values[:limit]:
        s = str(v).strip().lower()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _first_topic(rec: Dict) -> str:
    topics = rec.get("topics")
    if isinstance(topics, list) and topics:
        return str(topics[0]).strip().lower()
    return ""


def _signature(rec: Dict) -> str:
    title = normalize_title(str(rec.get("title") or ""))
    comps = sorted(_norm_items(rec.get("companies_mentioned"), limit=3))[:3]
    topic = _first_topic(rec)
    pd = str(rec.get("publish_date") or "")
    return "|".join([title, ",".join(comps), topic, pd])


def similarity(a: Dict, b: Dict) -> bool:
    ta = token_set(str(a.get("title") or ""))
    tb = token_set(str(b.get("title") or ""))
    jac = _jaccard(ta, tb)
    rat = _ratio(normalize_title(str(a.get("title") or "")), normalize_title(str(b.get("title") or "")))

    comps_a = set(_norm_items(a.get("companies_mentioned")))
    comps_b = set(_norm_items(b.get("companies_mentioned")))
    topics_a = set(_norm_items(a.get("topics")))
    topics_b = set(_norm_items(b.get("topics")))
    has_shared_entity = bool(comps_a & comps_b) or bool(topics_a & topics_b)

    return ((jac >= 0.75) or (rat >= 0.88)) and has_shared_entity


def _parse_date(v: Optional[str]) -> Optional[date]:
    if not v:
        return None
    try:
        return datetime.strptime(v, "%Y-%m-%d").date()
    except Exception:
        return None


def _parse_created(v: Optional[str]) -> Optional[datetime]:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v)
    except Exception:
        return None


def rank_score(rec: Dict) -> Tuple[Tuple[int, int, int, int, int], Dict[str, int]]:
    pub = PUBLISHER_SCORE.get(str(rec.get("source_type") or "Other"), 60)
    conf = {"High": 8, "Medium": 4, "Low": 0}.get(str(rec.get("publish_date_confidence") or "Low"), 0)
    has_pd = 5 if bool(_parse_date(rec.get("publish_date"))) else 0
    has_url = 3 if bool(str(rec.get("original_url") or "").strip()) else 0

    ev = rec.get("evidence_bullets")
    ev_list = [str(x).strip() for x in ev] if isinstance(ev, list) else []
    ev_word_counts = [len(x.split()) for x in ev_list if x]
    ev_short_quality = 6 if (2 <= len(ev_list) <= 4 and all(wc <= 25 for wc in ev_word_counts)) else 0
    ev_long_penalty = -8 if any(wc > 40 for wc in ev_word_counts) else 0
    ev_dupe_penalty = -3 if len({x.lower() for x in ev_list}) != len(ev_list) else 0

    companies_bonus = 2 if len(_norm_items(rec.get("companies_mentioned"))) >= 2 else 0
    topics_bonus = 2 if len(_norm_items(rec.get("topics"))) >= 2 else 0

    total = pub + conf + has_pd + has_url + ev_short_quality + ev_long_penalty + ev_dupe_penalty + companies_bonus + topics_bonus
    pd_ord = _parse_date(rec.get("publish_date")).toordinal() if _parse_date(rec.get("publish_date")) else -1
    created_ts = int(_parse_created(rec.get("created_at")).timestamp()) if _parse_created(rec.get("created_at")) else -1

    breakdown = {
        "publisher": pub,
        "publish_date_confidence": conf,
        "publish_date_present": has_pd,
        "original_url_present": has_url,
        "evidence_quality": ev_short_quality,
        "evidence_long_penalty": ev_long_penalty,
        "evidence_duplicate_penalty": ev_dupe_penalty,
        "companies_completeness": companies_bonus,
        "topics_completeness": topics_bonus,
        "total": total,
    }
    return (total, pd_ord, created_ts, len(_norm_items(rec.get("companies_mentioned"))), len(_norm_items(rec.get("topics")))), breakdown


def cluster_records(records: List[Dict]) -> List[List[int]]:
    n = len(records)
    if n == 0:
        return []

    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        for j in range(i + 1, n):
            if similarity(records[i], records[j]):
                union(i, j)

    groups: Dict[int, List[int]] = {}
    for i in range(n):
        r = find(i)
        groups.setdefault(r, []).append(i)
    return list(groups.values())


def dedup_and_rank(records: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    working = [deepcopy(r) for r in records]
    clusters = cluster_records(working)

    kept: List[Dict] = []
    excluded: List[Dict] = []

    for idxs in clusters:
        cluster = [working[i] for i in idxs]
        cluster_sources = sorted({str(r.get("source_type") or "Other") for r in cluster})
        scored = []
        for r in cluster:
            score_tuple, breakdown = rank_score(r)
            r["rank_breakdown"] = breakdown
            scored.append((score_tuple, str(r.get("record_id") or ""), r))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

        canonical = scored[0][2]
        canonical["exclude_from_brief"] = False
        canonical["dedup_cluster_size"] = len(cluster)
        canonical["dedup_sources"] = cluster_sources
        canonical["dedup_signature"] = _signature(canonical)
        kept.append(canonical)

        for _, _, r in scored[1:]:
            r["exclude_from_brief"] = True
            r["canonical_record_id"] = canonical.get("record_id")
            r["dedup_reason"] = "duplicate_of_canonical"
            r["dedup_signature"] = _signature(r)
            excluded.append(r)

    kept.sort(key=lambda r: str(r.get("record_id") or ""))
    excluded.sort(key=lambda r: str(r.get("record_id") or ""))
    return kept, excluded
