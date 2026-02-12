from __future__ import annotations

from typing import Any, Dict, List
import re
from src.constants import FOOTPRINT_REGIONS

# Minimal canonicalization maps (extend as you see patterns)
COUNTRY_ALIASES = {
    "u.s.": "United States",
    "u.s": "United States",
    "usa": "United States",
    "us": "United States",
    "united states of america": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "russia": "Russia",
    "czechia": "Czech Republic",
}

REGION_ALIASES = {
    "u.s.": "US",
    "usa": "US",
    "us": "US",
    "united states": "US",
    "europe": "Europe (including Russia)",
    "eu": "Europe (including Russia)",
    "e.u.": "Europe (including Russia)",
}

REGULATOR_ENTITY_ALIASES = {
    "european commission": "European Commission",
    "european union": "EU",
    "nhtsa": "NHTSA",
    "epa": "EPA",
    "eu": "EU",
    "e.u.": "EU",
}

# Country -> footprint region mapping (only for your footprint lens)
COUNTRY_TO_FOOTPRINT = {
    # US footprint
    "United States": "US",
    # Europe footprint (broad)
    "Germany": "Europe (including Russia)",
    "France": "Europe (including Russia)",
    "Italy": "Europe (including Russia)",
    "Spain": "Europe (including Russia)",
    "Czech Republic": "Europe (including Russia)",
    "Turkey": "Europe (including Russia)",
    "United Kingdom": "Europe (including Russia)",
    "Russia": "Europe (including Russia)",
    # Africa footprint (focus countries)
    "Morocco": "Africa",
    "South Africa": "Africa",
    # Explicit footprints
    "India": "India",
    "China": "China",
    "Mexico": "Mexico",
    "Thailand": "Thailand",
}

def _norm_token(s: str) -> str:
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return s

def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        key = x.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(x)
    return out

def _normalize_countries(countries: List[str]) -> List[str]:
    out = []
    for c in countries:
        c0 = _norm_token(c)
        key = c0.lower()
        out.append(COUNTRY_ALIASES.get(key, c0))
    return _dedupe_keep_order(out)

def _normalize_regions(regions: List[str]) -> List[str]:
    out = []
    for r in regions:
        r0 = _norm_token(r)
        key = r0.lower()
        out.append(REGION_ALIASES.get(key, r0))
    return _dedupe_keep_order(out)

def _record_text_for_region_hints(rec: Dict[str, Any]) -> str:
    parts: List[str] = []
    for k in ("title", "notes"):
        v = rec.get(k)
        if isinstance(v, str):
            parts.append(v)
    for k in ("keywords", "evidence_bullets", "key_insights", "strategic_implications"):
        v = rec.get(k)
        if isinstance(v, list):
            parts.extend(str(x) for x in v)
    return " ".join(parts).lower()

def _regions_from_text_hints(text_l: str) -> List[str]:
    out: List[str] = []
    for alias, region in REGION_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", text_l):
            out.append(region)
    for region in FOOTPRINT_REGIONS:
        if region.lower() in text_l:
            out.append(region)
    return _dedupe_keep_order(out)

def derive_regions_relevant_to_kiekert(country_mentions: List[str]) -> List[str]:
    # Strict footprint subset derived from country mentions
    regions = []
    for c in country_mentions:
        reg = COUNTRY_TO_FOOTPRINT.get(c)
        if reg:
            regions.append(reg)
    # Dedupe while preserving order, and enforce strict set
    regions = [r for r in _dedupe_keep_order(regions) if r in FOOTPRINT_REGIONS]
    return regions

def postprocess_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mutates as little as possible:
    - canonicalizes/dedupes country_mentions + regions_mentioned
    - ensures regions_mentioned includes footprint regions implied by country_mentions
    - derives regions_relevant_to_kiekert strictly from country_mentions
    """
    # Countries
    if rec.get("publish_date") == "":
        rec["publish_date"] = None
    url = rec.get("original_url")
    if isinstance(url, str):
        u = _norm_token(url)
        rec["original_url"] = u if re.match(r"^https?://\S+$", u) else None
    elif url == "":
        rec["original_url"] = None

    countries = rec.get("country_mentions") or []
    if isinstance(countries, list):
        rec["country_mentions"] = _normalize_countries([str(x) for x in countries])
    else:
        rec["country_mentions"] = []

    # Regions mentioned: keep only strict footprint buckets.
    regions = rec.get("regions_mentioned") or []
    region_items = _normalize_regions([str(x) for x in regions]) if isinstance(regions, list) else []
    region_items = [r for r in region_items if r in FOOTPRINT_REGIONS]

    # Add footprint regions implied by country mentions and explicit region hints in text.
    implied = derive_regions_relevant_to_kiekert(rec["country_mentions"])
    hinted = _regions_from_text_hints(_record_text_for_region_hints(rec))
    merged = region_items + implied + hinted
    rec["regions_mentioned"] = _dedupe_keep_order([r for r in _normalize_regions(merged) if r in FOOTPRINT_REGIONS])

    # Derive strict footprint relevance (supports importance flag)
    rec["regions_relevant_to_kiekert"] = implied

    # Clean government entities: drop country names, keep regulator bodies.
    ge = rec.get("government_entities") or []
    if isinstance(ge, list):
        cleaned: List[str] = []
        country_set = {c.lower() for c in rec["country_mentions"]}
        for ent in ge:
            e0 = _norm_token(str(ent))
            key = e0.lower()
            if key in country_set:
                continue
            if key in COUNTRY_ALIASES and COUNTRY_ALIASES[key].lower() in country_set:
                continue
            if key in REGULATOR_ENTITY_ALIASES:
                cleaned.append(REGULATOR_ENTITY_ALIASES[key])
            elif key in {"regulator", "government", "ministry"}:
                cleaned.append(e0)
            else:
                cleaned.append(e0)
        rec["government_entities"] = _dedupe_keep_order(cleaned)

    # Optional: normalize common company casing you keep seeing (add more as needed)
    comps = rec.get("companies_mentioned") or []
    if isinstance(comps, list):
        fixed = []
        for c in comps:
            c0 = _norm_token(str(c))
            if c0.lower() == "gm":
                fixed.append("GM")
            elif c0.lower() == "byd":
                fixed.append("BYD")
            elif c0.lower() == "vw":
                fixed.append("VW")
            else:
                fixed.append(c0)
        rec["companies_mentioned"] = _dedupe_keep_order(fixed)

    return rec
