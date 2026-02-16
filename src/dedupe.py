"""
Deduplication module for same-story detection and canonical record selection.
Groups identical stories across multiple publishers and picks the best source.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

# Publisher ranking (higher = better source)
PUBLISHER_SCORE = {
    "S&P": 100,
    "Bloomberg": 90,
    "Reuters": 80,
    "Automotive News": 75,
    "MarkLines": 70,
    "Press Release": 60,
    "Patent": 55,
    "Other": 50,
}

# Common English stopwords for title fingerprint
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "by", "with", "from", "as", "is", "be", "have", "do", "that",
    "this", "it", "which", "who", "what", "when", "where", "why", "how",
}


def normalize_title(title: str) -> str:
    """Normalize title for exact duplicate checks (legacy helper used by tests)."""
    if not title:
        return ""
    t = title.strip().lower()
    t = re.sub(r"[^a-z0-9\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _normalize_company_name(name: str) -> str:
    """Normalize company name for grouping: lowercase, remove punctuation."""
    if not name:
        return ""
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _title_fingerprint(title: str) -> str:
    """
    Create a fingerprint of the title for grouping same stories.
    - Lowercase
    - Remove punctuation
    - Remove stopwords
    - Keep up to 8 first tokens (order preserved)
    """
    if not title:
        return ""
    title = title.strip().lower()
    title = re.sub(r"[^a-z0-9\s]", "", title)
    tokens = title.split()
    tokens = [t for t in tokens if t and t not in STOPWORDS]
    tokens = tokens[:8]
    return " ".join(tokens)


def build_dedupe_key(rec: Dict) -> str:
    """
    Build a deduplication key from a record.
    
    Key components (in order):
    - publish_date or "unknown"
    - primary topic (topics[0] or "unknown")
    - top companies (first 4, normalized, sorted)
    - title fingerprint
    
    Returns a pipe-delimited string for grouping identical stories.
    """
    publish_date = rec.get("publish_date") or "unknown"
    
    primary_topic = "unknown"
    topics = rec.get("topics") or []
    if isinstance(topics, list) and topics:
        primary_topic = topics[0]
    
    companies = rec.get("companies_mentioned") or []
    if isinstance(companies, list):
        norm_companies = sorted(
            [_normalize_company_name(c) for c in companies[:4] if c]
        )
        company_str = ",".join(norm_companies)
    else:
        company_str = ""
    
    title = rec.get("title") or ""
    title_fp = _title_fingerprint(title)
    
    key = f"{publish_date}|{primary_topic}|{company_str}|{title_fp}"
    return key


def publisher_score(source_type: Optional[str]) -> int:
    """Score a publisher by type. Higher is better."""
    if not source_type:
        return PUBLISHER_SCORE.get("Other", 50)
    return PUBLISHER_SCORE.get(source_type, 50)


def confidence_score(confidence: Optional[str]) -> int:
    """Score confidence level. High=3, Medium=2, Low=1."""
    conf_map = {"High": 3, "Medium": 2, "Low": 1}
    return conf_map.get(confidence, 1)


def completeness_score(rec: Dict) -> int:
    """
    Score record completeness:
    +1 if publish_date present
    +1 if original_url present
    +1 if regions_relevant_to_kiekert non-empty
    +1 if evidence_bullets count >= 3
    """
    score = 0
    if rec.get("publish_date"):
        score += 1
    if rec.get("original_url"):
        score += 1
    if rec.get("regions_relevant_to_kiekert"):
        score += 1
    ev = rec.get("evidence_bullets") or []
    if isinstance(ev, list) and len(ev) >= 3:
        score += 1
    return score


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse YYYY-MM-DD date string. Returns None if invalid."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        return None


def _parse_iso_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO datetime string. Returns None if invalid."""
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None


def pick_canonical(group: List[Dict]) -> Dict:
    """
    Choose the canonical (best) record from a group of duplicates.
    
    Scoring tuple (highest wins):
    1. publisher_score (S&P > Bloomberg > ...)
    2. confidence_score (High > Medium > Low)
    3. completeness_score (more fields filled)
    4. publish_date (newest first)
    5. created_at (newest first)
    6. record_id (deterministic tiebreaker)
    """
    if not group:
        return {}
    
    if len(group) == 1:
        return group[0]
    
    scored = []
    for rec in group:
        pub_score = publisher_score(rec.get("source_type"))
        conf_score = confidence_score(rec.get("confidence"))
        comp_score = completeness_score(rec)
        
        pub_date = _parse_date(rec.get("publish_date"))
        created_at = _parse_iso_datetime(rec.get("created_at"))
        
        record_id = rec.get("record_id", "")
        
        score_tuple = (
            pub_score,
            conf_score,
            comp_score,
            pub_date or datetime.min,
            created_at or datetime.min,
            record_id,
        )
        scored.append((score_tuple, rec))
    
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def dedupe_records(records: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """
    Deduplicate records by grouping on dedupe_key.
    
    Returns:
    - canonical: list of unique canonical records (one per dedupe_key group)
    - dups: list of duplicate records marked with:
      * duplicate_of: canonical record_id
      * duplicate_reason: "same_dedupe_key"
      * canonical_source_type: canonical source_type
    """
    # Group records by dedupe key
    groups: Dict[str, List[Dict]] = defaultdict(list)
    for rec in records:
        key = build_dedupe_key(rec)
        groups[key].append(rec)
    
    canonical = []
    dups = []
    
    for key, group in groups.items():
        if len(group) == 1:
            # No duplicates
            canonical.append(group[0])
        else:
            # Pick best record as canonical
            best = pick_canonical(group)
            canonical.append(best)
            
            # Mark all others as duplicates
            for rec in group:
                if rec.get("record_id") != best.get("record_id"):
                    rec["duplicate_of"] = best.get("record_id")
                    rec["duplicate_reason"] = "same_dedupe_key"
                    rec["canonical_source_type"] = best.get("source_type")
                    dups.append(rec)
    
    return canonical, dups


def score_source_quality(rec: Dict) -> Tuple[int, int, int]:
    """
    Composite quality score for choosing the stronger source.

    Ordering:
    1. publisher_score
    2. confidence_score
    3. completeness_score
    """
    return (
        publisher_score(rec.get("source_type")),
        confidence_score(rec.get("confidence")),
        completeness_score(rec),
    )


def find_exact_title_duplicate(records: List[Dict], title: str) -> Optional[Dict]:
    """Return an existing record when normalized title matches exactly."""
    title_fp = _title_fingerprint(title or "")
    if not title_fp:
        return None
    for rec in records:
        if _title_fingerprint(rec.get("title") or "") == title_fp:
            return rec
    return None


def find_similar_title_records(
    records: List[Dict], title: str, threshold: float = 0.88
) -> List[Tuple[Dict, float]]:
    """
    Return records with title similarity >= threshold.
    Uses deterministic SequenceMatcher on normalized title fingerprints.
    """
    out: List[Tuple[Dict, float]] = []
    title_fp = _title_fingerprint(title or "")
    if not title_fp:
        return out
    for rec in records:
        other_fp = _title_fingerprint(rec.get("title") or "")
        if not other_fp:
            continue
        ratio = SequenceMatcher(None, title_fp, other_fp).ratio()
        if ratio >= threshold:
            out.append((rec, ratio))
    out.sort(key=lambda x: x[1], reverse=True)
    return out
