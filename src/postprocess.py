from __future__ import annotations

from typing import Any, Dict, List, Optional
from collections import Counter
from datetime import datetime
import re
from src.constants import (
    ALLOWED_ACTOR_TYPES, ALLOWED_CONF, ALLOWED_SOURCE_TYPES,
    DISPLAY_REGIONS, FIELD_POLICY, FOOTPRINT_REGIONS, FOOTPRINT_TO_DISPLAY,
    MACRO_THEME_PRIORITY_ESCALATION_THEMES, MACRO_THEME_RULES, PREMIUM_OEMS, STRUCTURAL_ROLLUP_RULES,
)

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
    # United States variants ("us" intentionally omitted — causes pronoun false positives)
    "u.s.": "United States",
    "usa": "United States",
    "united states": "United States",
    # Latin America / South America catch-all
    "latin america": "South America",
    "latam": "South America",
    "south america": "South America",
    # Europe generic catch-all
    "europe": "Europe",
    "eu": "Europe",
    "e.u.": "Europe",
    "europe (including russia)": "Europe",
    # Sub-regional Europe (old long-form names → new short names)
    "western europe": "West Europe",
    "west europe": "West Europe",
    "eastern europe": "East Europe",
    "east europe": "East Europe",
    "central europe": "Central Europe",
    # Individual country aliases
    "russia": "Russia",
    "south korea": "South Korea",
    "korea": "South Korea",
    # Asia generic catch-all
    "asia": "South Asia",
    "asia-pacific": "South Asia",
    "asia pacific": "South Asia",
    "apac": "South Asia",
    "south asia": "South Asia",
    # Sub-regional Asia / Americas
    "asean": "ASEAN",
    "nafta": "NAFTA",
    "north america": "NAFTA",
    # MEA buckets
    "middle east": "Middle East",
    "africa": "Africa",
}

REGULATOR_ENTITY_ALIASES = {
    "european commission": "European Commission",
    "european union": "EU",
    "nhtsa": "NHTSA",
    "epa": "EPA",
    "eu": "EU",
    "e.u.": "EU",
}

# Country -> footprint region mapping (derived from new_country_mapping.csv)
# Rule: if "relevant to Kiekert" != "" → use that value; else use market bucket.
COUNTRY_TO_FOOTPRINT = {
    # --- North America ---
    "United States": "United States",
    "Mexico": "Mexico",
    "Canada": "NAFTA",
    # --- West Europe (individual Kiekert countries) ---
    "France": "France",
    "Germany": "Germany",
    "Italy": "Italy",
    "Portugal": "Portugal",
    "Spain": "Spain",
    "Sweden": "Sweden",
    "United Kingdom": "United Kingdom",
    # --- West Europe (bucket countries) ---
    "Austria": "West Europe",
    "Belgium": "West Europe",
    "Denmark": "West Europe",
    "Finland": "West Europe",
    "Ireland": "West Europe",
    "Netherlands": "West Europe",
    "Norway": "West Europe",
    "Switzerland": "West Europe",
    # --- Central Europe ---
    "Czech Republic": "Czech Republic",  # individual Kiekert entry
    "Bulgaria": "Central Europe",
    "Croatia": "Central Europe",
    "Hungary": "Central Europe",
    "Poland": "Central Europe",
    "Romania": "Central Europe",
    "Serbia": "Central Europe",
    "Slovakia": "Central Europe",
    "Slovenia": "Central Europe",
    # --- East Europe ---
    "Belarus": "East Europe",
    "Kazakhstan": "East Europe",
    "Turkey": "East Europe",
    "Ukraine": "East Europe",
    "Uzbekistan": "East Europe",
    # --- Russia (individual Kiekert entry) ---
    "Russia": "Russia",
    # --- Greater China ---
    "China": "China",
    "Taiwan": "Taiwan",
    # --- Japan/Korea ---
    "Japan": "Japan",
    "South Korea": "South Korea",
    # --- Africa ---
    "Algeria": "Africa",
    "Egypt": "Africa",
    "Kenya": "Africa",
    "Nigeria": "Africa",
    "South Africa": "Africa",
    "Morocco": "Morocco",  # individual Kiekert entry
    # --- Middle East ---
    "Iran": "Middle East",
    "Saudi Arabia": "Middle East",
    # --- South America ---
    "Argentina": "Mercosul",
    "Brazil": "Mercosul",
    "Paraguay": "Mercosul",
    "Uruguay": "Mercosul",
    "Bolivia": "Andean",
    "Chile": "Andean",
    "Colombia": "Andean",
    "Ecuador": "Andean",
    "Peru": "Andean",
    "Venezuela": "Andean",
    # --- Central America ---
    "Costa Rica": "Central America",
    "El Salvador": "Central America",
    "Guatemala": "Central America",
    "Honduras": "Central America",
    "Nicaragua": "Central America",
    "Panama": "Central America",
    # --- South Asia / ASEAN ---
    "India": "India",
    "Pakistan": "Indian Subcontinent",
    "Indonesia": "ASEAN",
    "Malaysia": "ASEAN",
    "Philippines": "ASEAN",
    "Singapore": "ASEAN",
    "Thailand": "Thailand",
    "Vietnam": "ASEAN",
    # --- Oceania ---
    "Australia": "Oceania",
    "New Zealand": "Oceania",
    # --- Rest of World (countries not in any defined market) ---
    "Estonia": "Rest of World",
    "Greece": "Rest of World",
    "Israel": "Rest of World",
    "Kuwait": "Rest of World",
    "Latvia": "Rest of World",
    "Lithuania": "Rest of World",
    "Qatar": "Rest of World",
    "United Arab Emirates": "Rest of World",
}

_US_TEXT_RE = re.compile(
    r"\b(?:United States|U\.S\.A\.?|USA)\b",
    re.IGNORECASE,
)


def validate_csv_consistency(csv_path: str = "data/new_country_mapping.csv") -> list[str]:
    """
    Compare COUNTRY_TO_FOOTPRINT and FOOTPRINT_REGIONS against new_country_mapping.csv.

    Returns a list of human-readable warning strings describing any divergence.
    Returns an empty list when everything is in sync (or the CSV is missing).

    Called from Home.py at startup so the analyst sees a visible warning before
    editing either the CSV or the Python constants.
    """
    import csv
    import os

    if not os.path.exists(csv_path):
        return []

    warnings: list[str] = []

    # --- Build expected COUNTRY_TO_FOOTPRINT from CSV country rows ---
    # Rule: if relevant_to_kiekert != "" → use that; else if market != "" → use market; else region.
    csv_country_map: dict[str, str] = {}
    csv_footprint_values: set[str] = set()

    # utf-8-sig strips BOM if present; the first CSV column is named "country"
    # but its values are the row-type tokens ("country", "alias", "footprint_region").
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        # Normalise fieldnames to strip accidental whitespace/BOM residue
        if reader.fieldnames:
            reader.fieldnames = [n.strip() for n in reader.fieldnames]
        # The first column is named "country" and holds the row-type token.
        # The "relevant to Kiekert" column may have a variant spelling in the CSV;
        # detect it by prefix match so the checker isn't fragile to typos.
        _ROW_TYPE_COL = "country"
        _relevant_col = next(
            (f for f in (reader.fieldnames or []) if f.lower().startswith("relevant")),
            "relevant to Kiekert",
        )
        for row in reader:
            row_type = (row.get(_ROW_TYPE_COL) or "").strip()
            entry    = (row.get("entry") or "").strip()
            region   = (row.get("region") or "").strip()
            market   = (row.get("market") or "").strip()
            relevant = (row.get(_relevant_col) or "").strip()
            display  = (row.get("display") or "").strip()

            if row_type == "country" and entry:
                footprint = relevant or market or region
                if footprint:
                    csv_country_map[entry] = footprint

            elif row_type == "footprint_region" and entry:
                csv_footprint_values.add(entry)
                if display:
                    csv_footprint_values.add(display)

            elif row_type == "alias" and display:
                csv_footprint_values.add(display)

    # Check 1: countries in CSV but missing from COUNTRY_TO_FOOTPRINT
    for country, expected in csv_country_map.items():
        actual = COUNTRY_TO_FOOTPRINT.get(country)
        if actual is None:
            warnings.append(f"CSV country '{country}' is not in COUNTRY_TO_FOOTPRINT")
        elif actual != expected:
            warnings.append(
                f"CSV country '{country}': CSV expects '{expected}', "
                f"Python has '{actual}'"
            )

    # Check 2: countries in Python that map to "Rest of World" but aren't in the CSV are expected
    # (they were added as deliberate catch-alls). Only flag genuine unknowns.
    for country, footprint in COUNTRY_TO_FOOTPRINT.items():
        if country not in csv_country_map and footprint != "Rest of World":
            warnings.append(
                f"COUNTRY_TO_FOOTPRINT has '{country}' → '{footprint}' "
                f"but it is not in the CSV"
            )

    # Check 3: footprint values in CSV not in FOOTPRINT_REGIONS
    from src.constants import FOOTPRINT_REGIONS
    fp_set = set(FOOTPRINT_REGIONS)
    for val in sorted(csv_footprint_values):
        if val and val not in fp_set:
            warnings.append(f"CSV display/footprint value '{val}' is not in FOOTPRINT_REGIONS")

    return warnings


def _has_explicit_us_signal(text: str, country_mentions: List[str]) -> bool:
    countries = {str(c).strip().lower() for c in (country_mentions or [])}
    if "united states" in countries or "canada" in countries:
        return True
    if isinstance(text, str):
        if _US_TEXT_RE.search(text):
            return True
        # Accept uppercase token "US" only; ignore lowercase pronoun "us".
        if re.search(r"(?<![A-Za-z])US(?![A-Za-z])", text):
            return True
    return False


def _norm_token(s: str) -> str:
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _canonicalize_company_name(name: str) -> str:
    c0 = _norm_token(str(name))
    lower = c0.lower()
    if lower in _COMPANY_SPECIAL_CANONICAL:
        return _COMPANY_SPECIAL_CANONICAL[lower]
    if lower in _OEM_CANONICAL_BY_LOWER:
        return _OEM_CANONICAL_BY_LOWER[lower]

    base = re.sub(r"[.,]", "", lower)
    tokens = base.split()
    while tokens and tokens[-1] in _LEGAL_SUFFIX_TOKENS:
        tokens.pop()
    if tokens:
        base_key = " ".join(tokens)
        if base_key in PREMIUM_OEMS or base_key in _KEY_OEMS:
            return _OEM_CANONICAL_BY_LOWER.get(base_key, _norm_token(base_key.title().replace("Benz", "Benz")))
    return c0


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
    if field == "actor_type":
        return value not in ALLOWED_ACTOR_TYPES
    if field == "publish_date_confidence":
        return value not in ALLOWED_CONF
    if field == "publish_date":
        return not (value in (None, "") or _is_iso_date(value))
    if field == "original_url":
        return not (value in (None, "") or (isinstance(value, str) and re.match(r"^https?://\S+$", value)))
    return False


_ACTOR_TYPE_ALIASES = {
    "media": "industry",
    "industry_group": "industry",
    "tech_partner": "other",
    "government": "other",
    "regulator": "other",
}
_SOURCE_TYPE_ALIASES = {
    "marklines": "MarkLines",
}

_OUR_COMPANY_ALIASES = {"kiekert", "kiekert ag", "kiekert group"}

_KEY_OEMS = {
    "vw", "volkswagen", "bmw", "hyundai", "kia", "ford", "gm",
    "general motors", "stellantis", "toyota", "toyota motor", "toyota motor corporation",
    "mercedes", "mercedes-benz",
    "audi", "porsche", "nissan", "honda", "renault", "peugeot",
    "tata", "mahindra", "byd", "geely", "chery", "great wall",
}

_OEM_CANONICAL_BY_LOWER = {
    "bmw": "BMW",
    "byd": "BYD",
    "gm": "GM",
    "mercedes-benz": "Mercedes-Benz",
    "mercedes": "Mercedes",
    "toyota": "Toyota",
    "toyota motor": "Toyota",
    "toyota motor corporation": "Toyota",
    "vw": "Volkswagen",
    "volkswagen": "Volkswagen",
}

_LEGAL_SUFFIX_TOKENS = {
    "group", "ag", "se", "nv", "inc", "inc.", "corp", "corp.",
    "corporation", "co", "co.", "ltd", "llc",
}

_COMPANY_SPECIAL_CANONICAL = {
    "mercedes-benz group ag": "Mercedes-Benz",
    "mercedes-benz ag": "Mercedes-Benz",
    "bmw ag": "BMW",
    "volkswagen group ag": "Volkswagen",
    "volkswagen ag": "Volkswagen",
}


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


def _normalize_regions_with_migrations(regions: List[str]) -> tuple[List[str], List[Dict[str, str]]]:
    out: List[str] = []
    migrations: List[Dict[str, str]] = []
    for r in regions:
        r0 = _norm_token(r)
        key = r0.lower()
        mapped = REGION_ALIASES.get(key, r0)
        if key == "europe (including russia)":
            migrations.append({"from": "Europe (including Russia)", "to": "Europe"})
        out.append(mapped)
    return _dedupe_keep_order(out), migrations


def _append_audit_entry(rec: Dict[str, Any], key: str, value: Any) -> None:
    cur = rec.get(key)
    if not isinstance(cur, list):
        cur = []
    if value not in cur:
        cur.append(value)
    rec[key] = cur


def _record_text(rec: Dict[str, Any], source_text: Optional[str] = None) -> str:
    parts: List[str] = []
    if isinstance(source_text, str) and source_text.strip():
        parts.append(source_text)
    for k in ("title", "notes"):
        v = rec.get(k)
        if isinstance(v, str):
            parts.append(v)
    for k in ("keywords", "evidence_bullets", "key_insights"):
        v = rec.get(k)
        if isinstance(v, list):
            parts.extend(str(x) for x in v)
    return " ".join(parts)


def _contains_company_alias(text: str, aliases: set[str]) -> bool:
    text_l = text.lower()
    for alias in aliases:
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text_l):
            return True
    return False


def _detect_mentions_our_company(rec: Dict[str, Any], source_text: Optional[str] = None) -> bool:
    """Deterministic company mention detection from record evidence fields."""
    parts: List[str] = []
    if isinstance(source_text, str) and source_text.strip():
        parts.append(source_text)
    for k in ("title",):
        v = rec.get(k)
        if isinstance(v, str) and v.strip():
            parts.append(v)
    for k in ("evidence_bullets", "key_insights", "keywords"):
        v = rec.get(k)
        if isinstance(v, list):
            parts.extend(str(x) for x in v if str(x).strip())
    haystack = " ".join(parts)
    return _contains_company_alias(haystack, _OUR_COMPANY_ALIASES)


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


def parse_publish_date_from_text(text: str) -> Optional[str]:
    """Parse document publish date from free text and return ISO date only."""
    return extract_publish_date_iso(text)


def _header_zone(text: str, max_lines: int = 60, max_chars: int = 5000) -> str:
    lines = text.splitlines()[:max_lines]
    return "\n".join(lines)[:max_chars]


def _body_zone_excluding_header(text: str, skip_lines: int = 60) -> str:
    lines = text.splitlines()
    if len(lines) <= skip_lines:
        return ""
    return "\n".join(lines[skip_lines:])


_PUBLISH_TIMESTAMP_LINE_RE = re.compile(
    r"\bat\s+\d{1,2}:\d{2}\s*(?:AM|PM)\s*(?:PST|PDT|EST|EDT|CST|CDT|MST|MDT|UTC|GMT)\b",
    re.IGNORECASE,
)


def _event_date_scan_text(text: str) -> str:
    """Remove publisher-header/timestamp lines before event-date sniffing."""
    body = _body_zone_excluding_header(text)
    zone = body or text
    keep: List[str] = []
    for ln in zone.splitlines():
        if _PUBLISH_TIMESTAMP_LINE_RE.search(ln):
            continue
        keep.append(ln)
    return "\n".join(keep)


def _extract_date_from_pattern_list(text: str, patterns: List[re.Pattern]) -> Optional[str]:
    for pat in patterns:
        m = pat.search(text)
        if not m:
            continue
        month = _parse_month(m.group("month"))
        if not month:
            continue
        try:
            return datetime(int(m.group("year")), int(month), int(m.group("day"))).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _extract_bloomberg_header_publish_date(text: str) -> Optional[str]:
    """Extract Bloomberg-style header timestamp date (e.g., 'February 1, 2026 at 9:00 PM PST')."""
    header = _header_zone(text)
    patterns = [
        re.compile(
            r"\b(?P<month>[A-Za-z]{3,9})\s+(?P<day>\d{1,2}),\s*(?P<year>\d{4})\s+at\s+"
            r"\d{1,2}:\d{2}\s*(?:AM|PM)\s*(?:PST|PDT|EST|EDT|CST|CDT|MST|MDT|UTC|GMT)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?P<month>[A-Za-z]{3,9})\s+(?P<day>\d{1,2}),\s*(?P<year>\d{4})\s+at\s+"
            r"\d{1,2}:\d{2}\s*(?:AM|PM)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?P<month>[A-Za-z]{3,9})\s+(?P<day>\d{1,2}),\s*(?P<year>\d{4})\b",
            re.IGNORECASE,
        ),
    ]
    return _extract_date_from_pattern_list(header, patterns)


def _extract_reuters_header_publish_date(text: str) -> Optional[str]:
    """Extract Reuters-style header date/timestamp in article header."""
    header = _header_zone(text)
    patterns = [
        re.compile(
            r"\b(?P<month>[A-Za-z]{3,9})\s+(?P<day>\d{1,2}),\s*(?P<year>\d{4})(?:\s+at)?\s+"
            r"\d{1,2}:\d{2}\s*(?:AM|PM)(?:\s*(?:PST|PDT|EST|EDT|CST|CDT|MST|MDT|UTC|GMT))?\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?P<month>[A-Za-z]{3,9})\s+(?P<day>\d{1,2}),\s*(?P<year>\d{4})\b",
            re.IGNORECASE,
        ),
    ]
    return _extract_date_from_pattern_list(header, patterns)


def _extract_auto_news_header_publish_date(text: str) -> Optional[str]:
    """Extract Automotive News style header date/timestamp."""
    header = _header_zone(text)
    patterns = [
        re.compile(
            r"\b(?P<month>[A-Za-z]{3,9})\s+(?P<day>\d{1,2}),\s*(?P<year>\d{4})\s+at\s+"
            r"\d{1,2}:\d{2}\s*(?:AM|PM)?\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b(?P<month>[A-Za-z]{3,9})\s+(?P<day>\d{1,2}),\s*(?P<year>\d{4})\b",
            re.IGNORECASE,
        ),
    ]
    return _extract_date_from_pattern_list(header, patterns)


def _extract_sp_header_publish_date(text: str) -> Optional[str]:
    """Extract S&P-style header timestamp/date."""
    return _extract_auto_news_header_publish_date(text)


def _extract_marklines_header_publish_date(text: str) -> Optional[str]:
    """Extract MarkLines-style header timestamp/date."""
    return _extract_auto_news_header_publish_date(text)


def _extract_press_release_header_publish_date(text: str) -> Optional[str]:
    """Extract press release header timestamp/date."""
    return _extract_auto_news_header_publish_date(text)


PUBLISHER_HEADER_RULES = {
    "Bloomberg": ("rule:bloomberg_header_publish_date", _extract_bloomberg_header_publish_date),
    "Reuters": ("rule:reuters_header_publish_date", _extract_reuters_header_publish_date),
    "Automotive News": ("rule:automotive_news_header_publish_date", _extract_auto_news_header_publish_date),
    "S&P": ("rule:sp_header_publish_date", _extract_sp_header_publish_date),
    "MarkLines": ("rule:marklines_header_publish_date", _extract_marklines_header_publish_date),
    "Press Release": ("rule:press_release_header_publish_date", _extract_press_release_header_publish_date),
}


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


_CITY_REGION_HINTS: Dict[str, List[str]] = {
    "tokyo": ["Japan"],
    "osaka": ["Japan"],
    "nagoya": ["Japan"],
    "seoul": ["South Korea"],
    "taipei": ["Taiwan"],
    "jakarta": ["ASEAN"],
}


def _regions_from_text_hints(text_l: str) -> List[str]:
    out: List[str] = []
    for alias, region in REGION_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", text_l):
            out.append(region)
    for region in FOOTPRINT_REGIONS:
        if region.lower() in text_l:
            out.append(region)
    for city, regions in _CITY_REGION_HINTS.items():
        if city in text_l:
            out.extend(regions)
    return _dedupe_keep_order(out)


_GENERIC_EUROPE_RE = re.compile(r"\b(europe|eu|e\.u\.)\b", re.IGNORECASE)


def _has_generic_europe_mention(text_l: str) -> bool:
    if not isinstance(text_l, str):
        return False
    if not _GENERIC_EUROPE_RE.search(text_l):
        return False
    # Generic "Europe" with no explicit sub-region marker defaults to catch-all "Europe".
    if re.search(r"\b(west(?:ern)?\s*europe|east(?:ern)?\s*europe|central\s*europe|russia)\b", text_l):
        return False
    return True


def derive_regions_relevant_to_kiekert(country_mentions: List[str]) -> List[str]:
    regions = []
    for c in country_mentions:
        reg = COUNTRY_TO_FOOTPRINT.get(c)
        if reg:
            regions.append(reg)
    regions = [r for r in _dedupe_keep_order(regions) if r in FOOTPRINT_REGIONS]
    return regions


def postprocess_record(
    rec: Dict[str, Any],
    source_text: Optional[str] = None,
    publish_date_hint: Optional[str] = None,
    publish_date_hint_source: Optional[str] = None,
) -> Dict[str, Any]:
    """
    - canonicalizes/dedupes country_mentions + regions_mentioned
    - derives regions_relevant_to_kiekert strictly from country_mentions
    - logs provenance/mutations for rule-based edits
    """
    _ensure_meta(rec)
    rec.setdefault("priority", "Medium")
    rec.setdefault("confidence", "Medium")
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
    source_type_raw = str(rec.get("source_type") or "").strip()
    if source_type_raw:
        source_type_norm = _SOURCE_TYPE_ALIASES.get(source_type_raw.lower(), source_type_raw)
        if source_type_norm in ALLOWED_SOURCE_TYPES and source_type_norm != source_type_raw:
            _apply_field_policy(
                rec,
                "source_type",
                source_type_norm,
                source="postprocess",
                reason="source_type_alias_normalization",
            )

    mentions_our_company = _detect_mentions_our_company(rec, source_text=source_text)
    set_field(
        rec,
        "mentions_our_company",
        mentions_our_company,
        source="postprocess",
        reason="company_alias_detected" if mentions_our_company else "company_alias_not_found",
    )

    rec["_publisher_date_override_applied"] = False
    rec["_publisher_date_override_source"] = None
    publisher = str(rec.get("source_type") or "")
    publisher_rule = PUBLISHER_HEADER_RULES.get(publisher)
    if publisher_rule:
        publish_rule_source, publish_parser = publisher_rule
        before_publish = rec.get("publish_date")
        header_date = publish_parser(combined_text)
        if header_date and before_publish != header_date:
            _apply_field_policy(
                rec,
                "publish_date",
                header_date,
                source=publish_rule_source,
                reason="publisher_header_timestamp_preferred",
            )
            _apply_field_policy(
                rec,
                "publish_date_confidence",
                "High",
                source=publish_rule_source,
                reason="publisher_header_timestamp_preferred",
            )
            if _is_iso_date(before_publish):
                rec["_publisher_date_override_applied"] = True
                rec["_publisher_date_override_source"] = publish_rule_source

    if _is_iso_date(publish_date_hint):
        before_publish = rec.get("publish_date")
        hint_source = str(publish_date_hint_source or "pdf_publish_date_hint")
        source_tag = f"rule:{hint_source}"
        if before_publish != publish_date_hint:
            _apply_field_policy(
                rec,
                "publish_date",
                publish_date_hint,
                source=source_tag,
                reason="pdf_publish_date_hint_preferred",
            )
            _apply_field_policy(
                rec,
                "publish_date_confidence",
                "High" if hint_source == "pdf_header_publish_date" else "Medium",
                source=source_tag,
                reason="pdf_publish_date_hint_preferred",
            )
            if _is_iso_date(before_publish) and before_publish != publish_date_hint:
                _apply_field_policy(
                    rec,
                    "event_date",
                    before_publish,
                    source=source_tag,
                    reason="prior_publish_date_reclassified_as_event_date",
                )
                rec["_publisher_date_override_applied"] = True
                rec["_publisher_date_override_source"] = source_tag

    parsed_date = parse_publish_date_from_text(combined_text)
    if parsed_date:
        if not rec.get("publish_date"):
            _apply_field_policy(
                rec,
                "publish_date",
                parsed_date,
                source="rule:regex_publish_date",
                reason="publish_date_missing_backfill",
            )
            _apply_field_policy(
                rec,
                "publish_date_confidence",
                "High",
                source="rule:regex_publish_date",
                reason="publish_date_missing_backfill",
            )
        else:
            event_scan_text = _event_date_scan_text(combined_text)
            event_date = parse_publish_date_from_text(event_scan_text)
            if event_date and event_date != rec.get("publish_date"):
                _apply_field_policy(rec, "event_date", event_date, source="postprocess", reason="regex_detected_event_date")

    inferred_source = infer_publisher(combined_text)
    if inferred_source:
        _apply_field_policy(rec, "source_type", inferred_source, source="postprocess", reason="publisher_marker_inference")

    actor = str(rec.get("actor_type") or "").strip().lower()
    if actor:
        actor = _ACTOR_TYPE_ALIASES.get(actor, actor)
        if actor not in ALLOWED_ACTOR_TYPES:
            actor = "other"
        _apply_field_policy(rec, "actor_type", actor, source="postprocess", reason="actor_type_normalization")

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
    region_items: List[str] = []
    if isinstance(regions, list):
        region_items, region_migrations = _normalize_regions_with_migrations([str(x) for x in regions])
        for mig in region_migrations:
            _append_audit_entry(rec, "_region_migrations", mig)
    region_items = [r for r in region_items if r in FOOTPRINT_REGIONS]

    legacy_relevant = rec.get("regions_relevant_to_kiekert") or []
    legacy_relevant_items: List[str] = []
    if isinstance(legacy_relevant, list):
        legacy_relevant_items, rel_migrations = _normalize_regions_with_migrations([str(x) for x in legacy_relevant])
        for mig in rel_migrations:
            _append_audit_entry(rec, "_region_migrations", mig)
    legacy_relevant_items = [r for r in legacy_relevant_items if r in FOOTPRINT_REGIONS]

    implied = _dedupe_keep_order(derive_regions_relevant_to_kiekert(rec["country_mentions"]) + legacy_relevant_items)
    hints_text = _record_text_for_region_hints(rec)
    hinted = _regions_from_text_hints(hints_text)
    if not rec["country_mentions"] and _has_generic_europe_mention(hints_text):
        _append_audit_entry(rec, "_region_ambiguity", "Europe_generic_defaulted_to_Europe")
        if "Europe" not in hinted:
            hinted.append("Europe")
    merged = region_items + implied + hinted
    merged = _dedupe_keep_order([r for r in _normalize_regions(merged) if r in FOOTPRINT_REGIONS])

    # Use only LLM-extracted record fields (not raw source text) so that a contextual
    # "US tariff conflicts" mention in the PDF doesn't falsely confirm a US market signal.
    record_fields_text = _record_text(rec)
    if "United States" in merged and not _has_explicit_us_signal(record_fields_text, rec["country_mentions"]):
        merged = [r for r in merged if r != "United States"]
        _append_audit_entry(rec, "_region_validation_flags", "us_region_removed_no_us_evidence")

    # Same principle for China: _regions_from_text_hints() can inject "China" via bare keyword
    # substring matching (e.g. "chinese ev", "byd" in keywords/evidence triggers "china" match).
    # Only keep "China" if it was derived from country_mentions (i.e. is already in implied).
    # Articles that mention Chinese EV competition as context — but report no Chinese market
    # data — should not have China promoted to a footprint region.
    if "China" in merged and "China" not in implied:
        merged = [r for r in merged if r != "China"]
        _append_audit_entry(rec, "_region_validation_flags", "china_region_removed_no_china_country_mention")

    # Collapse country-level footprint entries to display-region buckets
    # so regions_mentioned contains only regions, not individual countries.
    display = _dedupe_keep_order(
        FOOTPRINT_TO_DISPLAY.get(r, r) for r in merged
    )
    display = [r for r in display if r in DISPLAY_REGIONS]

    _apply_field_policy(
        rec,
        "regions_mentioned",
        display,
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
        fixed = [_canonicalize_company_name(str(c)) for c in comps]
        _apply_field_policy(
            rec,
            "companies_mentioned",
            _dedupe_keep_order(fixed),
            source="postprocess",
            reason="company_canonicalization_dedupe",
        )

    rec = _boost_priority(rec)
    rec = _detect_macro_themes(rec)
    rec = _escalate_priority_from_macro_themes(rec)

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
    publish_source = rec.get("_provenance", {}).get("publish_date", {}).get("source")
    if (
        _is_iso_date(original_publish_date)
        and rec.get("publish_date") != original_publish_date
        and not (
            str(publish_source or "").endswith("_header_publish_date")
            or str(publish_source or "") == "rule:pdf_metadata_publish_date"
        )
    ):
        _apply_field_policy(
            rec, "publish_date", original_publish_date, source="postprocess", reason="preserve_existing_valid_publish_date"
        )

    rec = _compute_confidence(rec)
    return rec


def _compute_confidence(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Compute confidence from observable extraction signals, replacing the LLM self-assessment."""
    _ensure_meta(rec)
    llm_original = rec.get("confidence", "Medium")
    signals: Dict[str, int] = {}

    # +2 if publish_date is present
    signals["publish_date_present"] = 2 if rec.get("publish_date") else 0

    # +2 if source_type is a known publisher (not "Other")
    signals["source_type_known"] = 2 if rec.get("source_type", "Other") != "Other" else 0

    # +1 or +2 based on evidence_bullets count
    bullets = rec.get("evidence_bullets") or []
    signals["evidence_bullets"] = 2 if len(bullets) >= 3 else (1 if len(bullets) >= 2 else 0)

    # +1 if at least 2 key_insights
    insights = rec.get("key_insights") or []
    signals["key_insights"] = 1 if len(insights) >= 2 else 0

    # +1 if regions_relevant_to_kiekert is non-empty
    signals["kiekert_regions"] = 1 if rec.get("regions_relevant_to_kiekert") else 0

    # -1 per 3 postprocess rule corrections
    rule_impact = rec.get("_rule_impact") or {}
    total_rules = sum(int(v) for k, v in rule_impact.items() if str(k) != "computed_confidence")
    signals["rule_corrections"] = -(total_rules // 3)

    # -1 if publish_date was backfilled by regex (LLM missed it)
    provenance = rec.get("_provenance") or {}
    pd_prov = provenance.get("publish_date", {})
    signals["date_backfilled"] = -1 if pd_prov.get("source") == "rule:regex_publish_date" else 0

    score = sum(signals.values())
    if score >= 7:
        computed = "High"
    elif score >= 4:
        computed = "Medium"
    else:
        computed = "Low"

    rec["_confidence_detail"] = {
        "llm_original": llm_original,
        "computed": computed,
        "score": score,
        "signals": signals,
    }
    set_field(rec, "confidence", computed, source="postprocess", reason="computed_confidence")
    return rec


_CLOSURE_KEYWORDS = re.compile(
    r"\b(latch|latches|door\s*system|door\s*handle|handle|digital\s*key|smart\s*entry|cinch|striker|closure)\b",
    re.IGNORECASE,
)

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
    for field in ("evidence_bullets", "key_insights"):
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


def _escalate_priority_from_macro_themes(rec: Dict[str, Any]) -> Dict[str, Any]:
    if rec.get("priority") == "High":
        return rec

    regions = rec.get("regions_relevant_to_kiekert") or []
    if not isinstance(regions, list) or len(regions) == 0:
        return rec

    themes = rec.get("macro_themes_detected") or []
    if not isinstance(themes, list):
        return rec

    matched = [t for t in themes if t in MACRO_THEME_PRIORITY_ESCALATION_THEMES]
    if not matched:
        return rec

    theme = str(matched[0])
    set_field(
        rec,
        "priority",
        "High",
        source="postprocess",
        reason=f"footprint_and_macro_theme:{theme}",
    )
    return rec


# ---------------------------------------------------------------------------
# Macro-theme detection helpers
# ---------------------------------------------------------------------------

def _build_field_map(rec: Dict[str, Any]) -> Dict[str, List[str]]:
    """Build a map of field_name -> list of lowercased text fragments for matching."""
    fm: Dict[str, List[str]] = {}
    for k in ("title",):
        v = rec.get(k)
        if isinstance(v, str) and v.strip():
            fm[k] = [v.lower()]
    for k in ("evidence_bullets", "key_insights", "keywords"):
        v = rec.get(k)
        if isinstance(v, list):
            fm[k] = [str(x).lower() for x in v]
    return fm


def _find_terms_in_fields(
    patterns: List[str], field_map: Dict[str, List[str]],
) -> Dict[str, Any]:
    """Search regex patterns across a field map. Returns matched terms and field locations."""
    terms_found: List[str] = []
    fields_hit: List[str] = []
    for pat in patterns:
        for field_name, fragments in field_map.items():
            for idx, frag in enumerate(fragments):
                if re.search(pat, frag):
                    terms_found.append(pat)
                    loc = f"{field_name}[{idx}]" if len(fragments) > 1 else field_name
                    if loc not in fields_hit:
                        fields_hit.append(loc)
                    break  # one hit per field per pattern is enough
    return {"terms": _dedupe_keep_order(terms_found), "fields": _dedupe_keep_order(fields_hit)}


def _match_companies(
    companies_l: set, rule_companies: set, field_name: str = "companies_mentioned",
) -> Dict[str, Any]:
    """Check company overlap; return matched terms and field locations."""
    overlap = companies_l & rule_companies
    if overlap:
        return {"terms": sorted(overlap), "fields": [field_name]}
    return {"terms": [], "fields": []}


def _match_set(
    record_set: set, rule_set: set, field_name: str,
) -> Dict[str, Any]:
    """Check set overlap for topics or regions."""
    overlap = record_set & rule_set
    if overlap:
        return {"terms": sorted(overlap), "fields": [field_name]}
    return {"terms": [], "fields": []}


def _detect_macro_themes(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Tag record with macro-themes derived from keyword/company/topic/region signals."""
    field_map = _build_field_map(rec)
    companies_l = {c.lower() for c in (rec.get("companies_mentioned") or []) if isinstance(c, str)}
    topics_set = set(rec.get("topics") or [])
    regions_set = set(rec.get("regions_mentioned") or []) | set(rec.get("regions_relevant_to_kiekert") or [])

    matched: List[str] = []
    detail_by_theme: Dict[str, Any] = {}
    strength_by_theme: Dict[str, int] = {}
    rollups: List[str] = []

    for rule in MACRO_THEME_RULES:
        name = rule["name"]
        signals = rule["signals"]
        min_groups = rule["min_groups"]
        groups_matched: List[str] = []
        matches: Dict[str, Any] = {}

        # --- companies ---
        if "companies" in signals:
            cm = _match_companies(companies_l, signals["companies"])
            if cm["terms"]:
                groups_matched.append("companies")
                matches["companies"] = cm

        # --- keywords ---
        if "keywords" in signals:
            km = _find_terms_in_fields(signals["keywords"], field_map)
            if km["terms"]:
                groups_matched.append("keywords")
                matches["keywords"] = km

        # --- topics ---
        if "topics" in signals:
            tm = _match_set(topics_set, signals["topics"], "topics")
            if tm["terms"]:
                groups_matched.append("topics")
                matches["topics"] = tm

        # --- regions ---
        if "regions" in signals:
            rm = _match_set(regions_set, signals["regions"], "regions_mentioned")
            if rm["terms"]:
                groups_matched.append("regions")
                matches["regions"] = rm

        groups_count = len(groups_matched)

        # --- anti_keywords suppression ---
        anti_hit: Dict[str, Any] = {"terms": [], "fields": []}
        anti_patterns = rule.get("anti_keywords") or []
        if anti_patterns and groups_count >= min_groups:
            anti_hit = _find_terms_in_fields(anti_patterns, field_map)
            if anti_hit["terms"] and groups_count < 3:
                # Suppress: anti-keyword matched and signal not strong enough
                detail_by_theme[name] = {
                    "fired": False,
                    "groups_matched": groups_matched,
                    "matches": matches,
                    "anti_keyword_hits": anti_hit,
                    "suppressed_by_anti_keyword": True,
                    "min_groups": min_groups,
                }
                strength_by_theme[name] = 0
                continue

        # --- premium_company_gate ---
        if rule.get("premium_company_gate"):
            if not (companies_l & PREMIUM_OEMS):
                detail_by_theme[name] = {
                    "fired": False,
                    "groups_matched": groups_matched,
                    "matches": matches,
                    "anti_keyword_hits": anti_hit,
                    "suppressed_by_premium_gate": True,
                    "min_groups": min_groups,
                }
                strength_by_theme[name] = 0
                continue

        # --- region_requirements ---
        req_regions = rule.get("region_requirements")
        if req_regions:
            if not (regions_set & req_regions):
                detail_by_theme[name] = {
                    "fired": False,
                    "groups_matched": groups_matched,
                    "matches": matches,
                    "anti_keyword_hits": anti_hit,
                    "suppressed_by_region_requirement": True,
                    "min_groups": min_groups,
                }
                strength_by_theme[name] = 0
                continue

        # --- min_groups threshold ---
        fired = groups_count >= min_groups

        # --- strength ---
        if fired:
            if name == "Software-Defined Premium Shift":
                strength = 2 if groups_count >= 3 else 1
            elif groups_count >= 4:
                strength = 3
            elif groups_count == 3:
                strength = 2
            else:
                strength = 1
        else:
            strength = 0

        detail_by_theme[name] = {
            "fired": fired,
            "groups_matched": groups_matched,
            "matches": matches,
            "anti_keyword_hits": anti_hit,
            "min_groups": min_groups,
        }
        strength_by_theme[name] = strength

        if fired:
            matched.append(name)
            rollup = rule.get("rollup")
            if rollup and rollup not in rollups:
                rollups.append(rollup)

    matched_set = set(matched)
    for rollup_rule in STRUCTURAL_ROLLUP_RULES:
        themes = set(rollup_rule.get("themes") or [])
        label = rollup_rule.get("rollup")
        if label and themes and themes.issubset(matched_set) and label not in rollups:
            rollups.append(label)

    rec["macro_themes_detected"] = matched
    rec["_macro_theme_detail"] = detail_by_theme
    rec["_macro_theme_strength"] = strength_by_theme
    rec["_macro_theme_rollups"] = rollups
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
