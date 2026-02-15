from __future__ import annotations

from typing import Any, Dict, List, Optional
from collections import Counter
from datetime import datetime
import re
from src.constants import ALLOWED_CONF, ALLOWED_SOURCE_TYPES, FIELD_POLICY, FOOTPRINT_REGIONS

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
    "United States": "US",
    "Germany": "Europe (including Russia)",
    "France": "Europe (including Russia)",
    "Italy": "Europe (including Russia)",
    "Spain": "Europe (including Russia)",
    "Czech Republic": "Europe (including Russia)",
    "Turkey": "Europe (including Russia)",
    "United Kingdom": "Europe (including Russia)",
    "Russia": "Europe (including Russia)",
    "Morocco": "Africa",
    "South Africa": "Africa",
    "India": "India",
    "China": "China",
    "Mexico": "Mexico",
    "Thailand": "Thailand",
}


def _norm_token(s: str) -> str:
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _is_iso_date(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except Exception:
        return False


def _ensure_meta(rec: Dict[str, Any]) -> None:
    if not isinstance(rec.get("_provenance"), dict):
        rec["_provenance"] = {}
    if not isinstance(rec.get("_mutations"), list):
        rec["_mutations"] = []
    if not isinstance(rec.get("_rule_impact"), dict):
        rec["_rule_impact"] = {}


def set_field(rec: Dict[str, Any], field: str, value: Any, source: str, reason: Optional[str] = None) -> None:
    _ensure_meta(rec)
    before = rec.get(field)
    if before != value:
        if source != "llm":
            rule_name = reason or source
            rec["_rule_impact"][rule_name] = int(rec["_rule_impact"].get(rule_name, 0)) + 1
        rec["_mutations"].append(
            {
                "field": field,
                "before": before,
                "after": value,
                "source": source,
                "reason": reason,
            }
        )
    rec[field] = value
    rec["_provenance"][field] = {"source": source, "reason": reason}


def _policy_for_field(field: str) -> str:
    if field in FIELD_POLICY.get("python", []):
        return "python"
    if field in FIELD_POLICY.get("hybrid", []):
        return "hybrid"
    return "llm"


def _is_missing_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, list) and len(value) == 0:
        return True
    return False


def _is_invalid_llm_value(field: str, value: Any) -> bool:
    if field == "source_type":
        return value not in ALLOWED_SOURCE_TYPES
    if field == "publish_date_confidence":
        return value not in ALLOWED_CONF
    if field == "publish_date":
        return not (value in (None, "") or _is_iso_date(value))
    if field == "original_url":
        return not (value in (None, "") or (isinstance(value, str) and re.match(r"^https?://\S+$", value)))
    return False


def _apply_field_policy(
    rec: Dict[str, Any], field: str, value: Any, source: str, reason: Optional[str] = None
) -> None:
    policy = _policy_for_field(field)
    current = rec.get(field)
    if policy == "python":
        set_field(rec, field, value, source=source, reason=reason)
        return
    if policy == "llm":
        if _is_missing_value(current) or _is_invalid_llm_value(field, current):
            set_field(rec, field, value, source=source, reason=reason)
        return
    set_field(rec, field, value, source=source, reason=reason)


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


def _record_text(rec: Dict[str, Any], source_text: Optional[str] = None) -> str:
    parts: List[str] = []
    if isinstance(source_text, str) and source_text.strip():
        parts.append(source_text)
    for k in ("title", "notes"):
        v = rec.get(k)
        if isinstance(v, str):
            parts.append(v)
    for k in ("keywords", "evidence_bullets", "key_insights", "strategic_implications"):
        v = rec.get(k)
        if isinstance(v, list):
            parts.extend(str(x) for x in v)
    return " ".join(parts)


_DATE_PATTERNS = [
    (re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})\b"), "dmy"),
    (re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),\s*(\d{4})\b"), "mdy"),
]

_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def _parse_month(token: str) -> Optional[int]:
    return _MONTHS.get(token.strip().lower().rstrip("."))


def extract_publish_date_iso(text: str) -> Optional[str]:
    m_iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if m_iso:
        try:
            return datetime(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))).strftime("%Y-%m-%d")
        except ValueError:
            pass

    for pat, mode in _DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        try:
            if mode == "dmy":
                day = int(m.group(1))
                month = _parse_month(m.group(2))
                year = int(m.group(3))
            else:
                month = _parse_month(m.group(1))
                day = int(m.group(2))
                year = int(m.group(3))
            if not month:
                continue
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def infer_publisher(text: str) -> Optional[str]:
    t = text.lower()
    if (
        "s&p global" in t
        or "s&p global mobility" in t
        or "autointelligence | headline analysis" in t
    ):
        return "S&P"
    if "marklines" in t:
        return "MarkLines"
    if "automotive news" in t:
        return "Automotive News"
    if re.search(r"(?:^|\n)\s*reuters\b", text, flags=re.IGNORECASE):
        return "Reuters"
    return None


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
    regions = []
    for c in country_mentions:
        reg = COUNTRY_TO_FOOTPRINT.get(c)
        if reg:
            regions.append(reg)
    regions = [r for r in _dedupe_keep_order(regions) if r in FOOTPRINT_REGIONS]
    return regions


def postprocess_record(rec: Dict[str, Any], source_text: Optional[str] = None) -> Dict[str, Any]:
    """
    - canonicalizes/dedupes country_mentions + regions_mentioned
    - derives regions_relevant_to_kiekert strictly from country_mentions
    - logs provenance/mutations for rule-based edits
    """
    _ensure_meta(rec)
    original_publish_date = rec.get("publish_date")
    original_priority = rec.get("priority")
    set_field(rec, "priority_llm", original_priority, source="llm", reason="raw_model_priority")

    if rec.get("publish_date") == "":
        _apply_field_policy(rec, "publish_date", None, source="postprocess", reason="empty_publish_date_to_null")

    url = rec.get("original_url")
    if isinstance(url, str):
        u = _norm_token(url)
        _apply_field_policy(
            rec,
            "original_url",
            u if re.match(r"^https?://\S+$", u) else None,
            source="postprocess",
            reason="url_normalization",
        )
    elif url == "":
        _apply_field_policy(rec, "original_url", None, source="postprocess", reason="empty_url_to_null")

    combined_text = _record_text(rec, source_text=source_text)
    parsed_date = extract_publish_date_iso(combined_text)
    if parsed_date:
        if not rec.get("publish_date"):
            _apply_field_policy(rec, "publish_date", parsed_date, source="postprocess", reason="regex_fill_publish_date_when_missing")
            _apply_field_policy(
                rec, "publish_date_confidence", "High", source="postprocess", reason="regex_fill_publish_date_when_missing"
            )
        else:
            _apply_field_policy(rec, "event_date", parsed_date, source="postprocess", reason="regex_detected_event_date")

    inferred_source = infer_publisher(combined_text)
    if inferred_source:
        _apply_field_policy(rec, "source_type", inferred_source, source="postprocess", reason="publisher_marker_inference")

    countries = rec.get("country_mentions") or []
    if isinstance(countries, list):
        _apply_field_policy(
            rec,
            "country_mentions",
            _normalize_countries([str(x) for x in countries]),
            source="postprocess",
            reason="country_canonicalization_dedupe",
        )
    else:
        _apply_field_policy(rec, "country_mentions", [], source="postprocess", reason="country_mentions_not_list")

    regions = rec.get("regions_mentioned") or []
    region_items = _normalize_regions([str(x) for x in regions]) if isinstance(regions, list) else []
    region_items = [r for r in region_items if r in FOOTPRINT_REGIONS]

    implied = derive_regions_relevant_to_kiekert(rec["country_mentions"])
    hinted = _regions_from_text_hints(_record_text_for_region_hints(rec))
    merged = region_items + implied + hinted

    _apply_field_policy(
        rec,
        "regions_mentioned",
        _dedupe_keep_order([r for r in _normalize_regions(merged) if r in FOOTPRINT_REGIONS]),
        source="postprocess",
        reason="regions_bucketed_deduped",
    )
    _apply_field_policy(
        rec,
        "regions_relevant_to_kiekert",
        implied,
        source="postprocess",
        reason="derived_from_country_mentions",
    )

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
        _apply_field_policy(
            rec,
            "government_entities",
            _dedupe_keep_order(cleaned),
            source="postprocess",
            reason="government_entity_cleanup",
        )

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
        _apply_field_policy(
            rec,
            "companies_mentioned",
            _dedupe_keep_order(fixed),
            source="postprocess",
            reason="company_canonicalization_dedupe",
        )

    rec = _boost_priority(rec)
    final_priority = rec.get("priority")
    set_field(rec, "priority_final", final_priority, source="postprocess", reason="final_priority_after_rules")
    if final_priority != original_priority:
        priority_reason = (
            rec.get("_provenance", {}).get("priority", {}).get("reason")
            or "rule_adjustment"
        )
        set_field(
            rec,
            "priority_reason",
            priority_reason,
            source="postprocess",
            reason="priority_changed_by_rules",
        )

    _ensure_meta(rec)
    if _is_iso_date(original_publish_date) and rec.get("publish_date") != original_publish_date:
        _apply_field_policy(
            rec, "publish_date", original_publish_date, source="postprocess", reason="preserve_existing_valid_publish_date"
        )

    return rec


_CLOSURE_KEYWORDS = re.compile(
    r"\b(latch|latches|door\s*system|door\s*handle|handle|digital\s*key|smart\s*entry|cinch|striker|closure)\b",
    re.IGNORECASE,
)

_KEY_OEMS = {
    "vw", "volkswagen", "bmw", "hyundai", "kia", "ford", "gm",
    "general motors", "stellantis", "toyota", "mercedes", "mercedes-benz",
    "audi", "porsche", "nissan", "honda", "renault", "peugeot",
    "tata", "mahindra", "byd", "geely", "chery", "great wall",
}


def _boost_priority(rec: Dict[str, Any]) -> Dict[str, Any]:
    if rec.get("priority") == "High":
        return rec

    if rec.get("mentions_our_company"):
        set_field(rec, "priority", "High", source="postprocess", reason="mentions_our_company")
        return rec

    regions = rec.get("regions_relevant_to_kiekert") or []
    topics = rec.get("topics") or []
    topics_lower = {t.lower() for t in topics if isinstance(t, str)}
    has_footprint = bool(regions)
    has_closure_topic = "closure technology & innovation" in topics_lower

    if has_footprint and has_closure_topic:
        set_field(rec, "priority", "High", source="postprocess", reason="footprint_and_closure_topic")
        return rec

    text_parts = []
    for field in ("evidence_bullets", "key_insights", "strategic_implications"):
        v = rec.get(field)
        if isinstance(v, list):
            text_parts.extend(str(x) for x in v)
    title = rec.get("title") or ""
    full_text = title + " " + " ".join(text_parts)
    has_closure_keyword = bool(_CLOSURE_KEYWORDS.search(full_text))

    if has_footprint and has_closure_keyword:
        set_field(rec, "priority", "High", source="postprocess", reason="footprint_and_closure_keyword")
        return rec

    companies = rec.get("companies_mentioned") or []
    companies_lower = {c.lower() for c in companies if isinstance(c, str)}
    has_key_oem = bool(companies_lower & _KEY_OEMS)

    if has_footprint and has_key_oem:
        set_field(rec, "priority", "High", source="postprocess", reason="footprint_and_key_oem")
        return rec

    return rec


def summarize_rule_impact(records: List[Dict[str, Any]], date_range=None) -> Dict[str, Any]:
    rule_counts: Counter = Counter()
    field_counts: Counter = Counter()

    start = end = None
    if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
        start, end = date_range
        if isinstance(start, str):
            start = datetime.fromisoformat(start).date()
        if isinstance(end, str):
            end = datetime.fromisoformat(end).date()

    for rec in records:
        if start and end:
            created = rec.get("created_at")
            try:
                created_date = datetime.fromisoformat(str(created).replace("Z", "+00:00")).date()
            except Exception:
                continue
            if created_date < start or created_date > end:
                continue

        impact = rec.get("_rule_impact")
        if isinstance(impact, dict):
            for rule, count in impact.items():
                try:
                    rule_counts[str(rule)] += int(count)
                except Exception:
                    continue

        mutations = rec.get("_mutations")
        if isinstance(mutations, list):
            for m in mutations:
                if isinstance(m, dict) and "field" in m:
                    field_counts[str(m["field"])] += 1

    return {
        "rules_total": int(sum(rule_counts.values())),
        "fields_total": int(sum(field_counts.values())),
        "top_rules": dict(rule_counts.most_common(10)),
        "top_fields": dict(field_counts.most_common(10)),
    }
