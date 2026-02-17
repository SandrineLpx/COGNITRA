from __future__ import annotations
from typing import Tuple, List, Dict, Any
from datetime import datetime

from src.constants import (
    CANON_TOPICS,
    DISPLAY_REGIONS,
    FOOTPRINT_REGIONS,
    ALLOWED_SOURCE_TYPES,
    ALLOWED_ACTOR_TYPES,
    ALLOWED_PRIORITY,
    ALLOWED_CONF,
    ALLOWED_REVIEW,
    _LEGACY_REVIEW_MAP,
    REQUIRED_KEYS,
)

def _is_iso_date(s: str) -> bool:
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except Exception:
        return False

def validate_record(rec: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errs: List[str] = []

    for k in REQUIRED_KEYS:
        if k not in rec:
            errs.append(f"Missing key: {k}")

    if errs:
        return False, errs

    if rec["source_type"] not in ALLOWED_SOURCE_TYPES:
        errs.append(f"source_type must be one of {sorted(ALLOWED_SOURCE_TYPES)}")

    if rec["actor_type"] not in ALLOWED_ACTOR_TYPES:
        errs.append(f"actor_type must be one of {sorted(ALLOWED_ACTOR_TYPES)}")

    if rec["publish_date"] is not None and rec["publish_date"] != "":
        if not isinstance(rec["publish_date"], str) or not _is_iso_date(rec["publish_date"]):
            errs.append("publish_date must be YYYY-MM-DD, empty string, or null")

    if rec["original_url"] is not None and rec["original_url"] != "" and not isinstance(rec["original_url"], str):
        errs.append("original_url must be a string, empty string, or null")

    if rec["publish_date_confidence"] not in ALLOWED_CONF:
        errs.append(f"publish_date_confidence must be one of {sorted(ALLOWED_CONF)}")

    if rec["priority"] not in ALLOWED_PRIORITY:
        errs.append(f"priority must be one of {sorted(ALLOWED_PRIORITY)}")

    if rec["confidence"] not in ALLOWED_CONF:
        errs.append(f"confidence must be one of {sorted(ALLOWED_CONF)}")

    rs = rec["review_status"]
    if rs in _LEGACY_REVIEW_MAP:
        rs = _LEGACY_REVIEW_MAP[rs]
    if rs not in ALLOWED_REVIEW:
        errs.append(f"review_status must be one of {sorted(ALLOWED_REVIEW)}")

    topics = rec["topics"]
    if not isinstance(topics, list) or not (1 <= len(topics) <= 4):
        errs.append("topics must be a list of 1-4 items")
    else:
        bad = [t for t in topics if t not in CANON_TOPICS]
        if bad:
            errs.append(f"topics contains non-canonical labels: {bad}")

    kw = rec["keywords"]
    if not isinstance(kw, list) or not (3 <= len(kw) <= 15):
        errs.append("keywords must be a list of 3-15 items")

    ev = rec["evidence_bullets"]
    if not isinstance(ev, list) or not (2 <= len(ev) <= 4):
        errs.append("evidence_bullets must be a list of 2-4 items")

    ki = rec["key_insights"]
    if not isinstance(ki, list) or not (2 <= len(ki) <= 4):
        errs.append("key_insights must be a list of 2-4 items")

    rm = rec["regions_mentioned"]
    if not isinstance(rm, list):
        errs.append("regions_mentioned must be a list")
    else:
        if len(rm) != len(set(rm)):
            errs.append("regions_mentioned must not contain duplicates")
        if len(rm) > 15:
            errs.append("regions_mentioned must have at most 15 items")
        badrm = [r for r in rm if r not in DISPLAY_REGIONS]
        if badrm:
            errs.append(f"regions_mentioned contains invalid labels: {badrm}")

    rr = rec["regions_relevant_to_kiekert"]
    if not isinstance(rr, list):
        errs.append("regions_relevant_to_kiekert must be a list")
    else:
        badr = [r for r in rr if r not in FOOTPRINT_REGIONS]
        if badr:
            errs.append(f"regions_relevant_to_kiekert contains invalid labels: {badr}")

    return len(errs) == 0, errs
