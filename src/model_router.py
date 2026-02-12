from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
import json
import re
import os

from src.constants import (
    REQUIRED_KEYS,
    CANON_TOPICS,
    FOOTPRINT_REGIONS,
    ALLOWED_SOURCE_TYPES,
    ALLOWED_ACTOR_TYPES,
    ALLOWED_PRIORITY,
    ALLOWED_CONF,
    ALLOWED_REVIEW,
)
from src.schema_validate import validate_record
from src.postprocess import postprocess_record
from src.storage import utc_now_iso

AUTO_ORDER = ["gemini", "claude", "chatgpt"]

def record_response_schema() -> Dict[str, Any]:
    return {
        "type": "OBJECT",
        "properties": {
            "title": {"type": "STRING"},
            "source_type": {"type": "STRING", "enum": sorted(ALLOWED_SOURCE_TYPES)},
            "publish_date": {"type": "STRING", "nullable": True, "pattern": r"^\d{4}-\d{2}-\d{2}$"},
            "publish_date_confidence": {"type": "STRING", "enum": sorted(ALLOWED_CONF)},
            "original_url": {"type": "STRING", "nullable": True},
            "actor_type": {"type": "STRING", "enum": sorted(ALLOWED_ACTOR_TYPES)},
            "government_entities": {"type": "ARRAY", "items": {"type": "STRING"}},
            "companies_mentioned": {"type": "ARRAY", "items": {"type": "STRING"}},
            "mentions_our_company": {"type": "BOOLEAN"},
            "topics": {"type": "ARRAY", "items": {"type": "STRING", "enum": CANON_TOPICS}, "minItems": 1, "maxItems": 3},
            "keywords": {"type": "ARRAY", "items": {"type": "STRING"}, "minItems": 5, "maxItems": 12},
            "country_mentions": {"type": "ARRAY", "items": {"type": "STRING"}},
            "regions_mentioned": {"type": "ARRAY", "items": {"type": "STRING"}, "maxItems": 15},
            "regions_relevant_to_kiekert": {
                "type": "ARRAY",
                "items": {"type": "STRING", "enum": FOOTPRINT_REGIONS},
            },
            "region_signal_type": {"type": "STRING"},
            "supply_flow_hint": {"type": "STRING"},
            "priority": {"type": "STRING", "enum": sorted(ALLOWED_PRIORITY)},
            "confidence": {"type": "STRING", "enum": sorted(ALLOWED_CONF)},
            "evidence_bullets": {"type": "ARRAY", "items": {"type": "STRING"}, "minItems": 2, "maxItems": 4},
            "key_insights": {"type": "ARRAY", "items": {"type": "STRING"}, "minItems": 2, "maxItems": 4},
            "strategic_implications": {"type": "ARRAY", "items": {"type": "STRING"}, "minItems": 2, "maxItems": 4},
            "recommended_actions": {"type": "ARRAY", "items": {"type": "STRING"}, "maxItems": 6, "nullable": True},
            "review_status": {"type": "STRING", "enum": sorted(ALLOWED_REVIEW)},
            "notes": {"type": "STRING"},
        },
        "required": REQUIRED_KEYS,
    }

def call_model(provider: str, prompt: str, schema: Dict[str, Any]) -> str:
    """
    Call selected model provider and return JSON text.
    """
    if provider == "gemini":
        return _call_gemini(prompt, schema)
    if provider == "claude":
        raise NotImplementedError("Claude provider is not implemented yet.")
    if provider == "chatgpt":
        raise NotImplementedError("ChatGPT provider is not implemented yet.")
    raise ValueError(f"Unsupported provider: {provider}")

def _call_gemini(prompt: str, schema: Dict[str, Any]) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets.get("GEMINI_API_KEY")
        except Exception:
            api_key = None
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set. Set it in .streamlit/secrets.toml or as an environment variable.")

    try:
        from google import genai
        from google.genai import types
    except Exception as e:
        raise RuntimeError("google-genai is not installed. Install it with: pip install google-genai") from e

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    client = genai.Client(api_key=api_key)
    try:
        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
    except Exception as e:
        raise RuntimeError(f"Gemini API call failed: {e}") from e

    text = (resp.text or "").strip()
    if not text:
        raise RuntimeError("Gemini API returned empty response text.")
    return text

def extraction_prompt(context_pack: str) -> str:
    return (
        "Return JSON only matching the schema. Follow these rules strictly:\n"
        "1) source_type is the PUBLISHER of the document. If 'S&P Global' or 'AutoIntelligence' appears, use 'S&P'. "
        "If the document cites Reuters/Bloomberg, do NOT set source_type to those unless they are the publisher.\n"
        "2) actor_type is the primary actor driving the action. Do not set 'regulator' unless a regulator is issuing the action.\n"
        "3) publish_date: extract the document date and return YYYY-MM-DD if present (for example '4 Feb 2026', '11 Feb 2026'); else null.\n"
        "4) Only use 'Closure Technology & Innovation' when latch/door/handle/digital key/smart entry/cinch is explicitly present.\n"
        "5) evidence_bullets must be 2-4 short factual bullets, each <= 25 words. No long paragraphs.\n"
        "6) Deduplicate all lists. Do not output US/USA/U.S. variants; normalize to one form.\n"
        "Use only the provided text.\n\nINPUT (context pack):\n"
        + context_pack
    )

def fix_json_prompt(broken: str) -> str:
    return (
        "Fix the JSON below so it is valid and matches the schema. "
        "Do not add new information. Return JSON only.\n\nBROKEN JSON:\n"
        + broken
    )

def _extract_from_context(context_pack: str) -> Dict[str, Any]:
    title = _rx1(r"(?mi)^TITLE:\s*(.+)$", context_pack) or "Untitled PDF Brief"
    url = _rx1(r"https?://\S+", context_pack)
    publish_date = _rx1(r"\b(20\d{2}-\d{2}-\d{2})\b", context_pack)
    text_l = context_pack.lower()

    countries = _find_terms(
        text_l,
        [
            "india", "china", "mexico", "thailand", "russia", "germany", "france", "italy",
            "spain", "poland", "turkey", "morocco", "south africa", "united states", "usa", "us",
            "canada", "japan", "korea", "uk", "united kingdom",
        ],
    )

    companies = _find_terms(
        text_l,
        [
            "kiekert", "tesla", "ford", "general motors", "gm", "stellantis", "toyota",
            "volkswagen", "vw", "hyundai", "kia", "bmw", "mercedes", "renault", "geely", "byd",
            "magna", "bosch", "continental", "aptiv", "valeo", "denso", "aisin",
        ],
    )
    companies = [_pretty_term(x) for x in companies]

    gov_entities = _find_terms(
        text_l,
        ["nhtsa", "epa", "eu", "european commission", "ministry", "regulator", "government"],
    )
    gov_entities = [_pretty_term(x) for x in gov_entities]

    source_type = _infer_source_type(text_l)
    actor_type = _infer_actor_type(text_l, gov_entities, companies)
    topics = _infer_topics(text_l)
    keywords = _extract_keywords(context_pack, limit=10)
    regions_rel = _regions_relevant(countries, context_pack)

    rec: Dict[str, Any] = {
        "title": title.strip(),
        "source_type": source_type,
        "publish_date": publish_date,
        "publish_date_confidence": "High" if publish_date else "Low",
        "original_url": url,
        "actor_type": actor_type,
        "government_entities": gov_entities,
        "companies_mentioned": companies,
        "mentions_our_company": ("kiekert" in text_l),
        "topics": topics,
        "keywords": keywords,
        "country_mentions": [_pretty_term(c) for c in countries][:12],
        "regions_mentioned": [_region_bucket(c) for c in countries if _region_bucket(c)],
        "regions_relevant_to_kiekert": regions_rel,
        "region_signal_type": "mixed",
        "supply_flow_hint": "",
        "priority": _infer_priority(text_l, topics),
        "confidence": "Medium",
        "evidence_bullets": _evidence_lines(context_pack),
        "key_insights": _insight_lines(topics),
        "strategic_implications": _implication_lines(topics),
        "recommended_actions": _action_lines(topics),
        "review_status": "Not Reviewed",
        "notes": "Local deterministic extraction (no external model call configured).",
    }
    return _normalize_record(rec)

def _repair_to_schema(broken: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(broken)
        if not isinstance(parsed, dict):
            parsed = {}
    except Exception:
        parsed = {}

    merged = _extract_from_context(str(parsed.get("title", "Untitled PDF Brief")))
    for k in REQUIRED_KEYS:
        if k in parsed:
            merged[k] = parsed[k]
    return _normalize_record(merged)

def _normalize_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    # Ensure all required keys exist.
    for k in REQUIRED_KEYS:
        rec.setdefault(k, None)

    if rec["source_type"] not in ALLOWED_SOURCE_TYPES:
        rec["source_type"] = "Other"
    if rec["actor_type"] not in ALLOWED_ACTOR_TYPES:
        rec["actor_type"] = "other"
    if rec["priority"] not in ALLOWED_PRIORITY:
        rec["priority"] = "Medium"
    if rec["confidence"] not in ALLOWED_CONF:
        rec["confidence"] = "Medium"
    if rec["publish_date_confidence"] not in ALLOWED_CONF:
        rec["publish_date_confidence"] = "Low"
    if rec["review_status"] not in ALLOWED_REVIEW:
        rec["review_status"] = "Not Reviewed"

    rec["title"] = str(rec.get("title") or "Untitled PDF Brief")
    rec["original_url"] = rec.get("original_url")
    rec["notes"] = str(rec.get("notes") or "")

    rec["government_entities"] = _as_list(rec.get("government_entities"), max_len=8)
    rec["companies_mentioned"] = _as_list(rec.get("companies_mentioned"), max_len=20)
    rec["country_mentions"] = _as_list(rec.get("country_mentions"), max_len=20)
    rec["regions_mentioned"] = _as_list(rec.get("regions_mentioned"), max_len=20)
    rec["regions_relevant_to_kiekert"] = [
        x for x in _as_list(rec.get("regions_relevant_to_kiekert"), max_len=7) if x in FOOTPRINT_REGIONS
    ]

    topics = [t for t in _as_list(rec.get("topics"), max_len=3) if t in CANON_TOPICS]
    if not topics:
        topics = ["Market & Competition"]
    rec["topics"] = topics[:3]

    rec["keywords"] = _as_list(rec.get("keywords"), max_len=12)
    rec["keywords"] = _fill_to_min(rec["keywords"], min_len=5, filler=["automotive", "closures", "supply", "program", "market"])

    rec["evidence_bullets"] = _as_list(rec.get("evidence_bullets"), max_len=4)
    rec["evidence_bullets"] = _fill_to_min(rec["evidence_bullets"], min_len=2, filler=["Source text references market/industry developments."])

    rec["key_insights"] = _as_list(rec.get("key_insights"), max_len=4)
    rec["key_insights"] = _fill_to_min(rec["key_insights"], min_len=2, filler=["Signal suggests potential impact on closure-system demand planning."])

    rec["strategic_implications"] = _as_list(rec.get("strategic_implications"), max_len=4)
    rec["strategic_implications"] = _fill_to_min(
        rec["strategic_implications"], min_len=2, filler=["Track for downstream effects on platform and sourcing decisions."]
    )

    ra = rec.get("recommended_actions")
    rec["recommended_actions"] = None if ra is None else _as_list(ra, max_len=6)
    rec["mentions_our_company"] = bool(rec.get("mentions_our_company"))
    rec["region_signal_type"] = str(rec.get("region_signal_type") or "mixed")
    rec["supply_flow_hint"] = str(rec.get("supply_flow_hint") or "")

    ok, errs = validate_record(rec)
    if not ok:
        # Final hard-safe defaults to guarantee downstream app flow.
        rec["topics"] = ["Market & Competition"]
        rec["keywords"] = ["automotive", "market", "program", "supplier", "closures"]
        rec["evidence_bullets"] = ["Article text was processed from uploaded PDF.", "Record generated with deterministic fallback extraction."]
        rec["key_insights"] = ["The document contains automotive industry signals.", "Further analyst review is needed for precision."]
        rec["strategic_implications"] = ["Potential relevance to closure systems and OEM/supplier dynamics.", "Track for changes in regional manufacturing or sourcing."]
        rec["regions_relevant_to_kiekert"] = []
        rec["priority"] = "Medium"
        rec["confidence"] = "Low"
        rec["notes"] = (rec.get("notes") or "") + f" Validation auto-correct applied: {'; '.join(errs)}"

    return rec

def _rx1(pattern: str, text: str) -> Optional[str]:
    m = re.search(pattern, text)
    return m.group(1).strip() if (m and m.groups()) else (m.group(0).strip() if m else None)

def _find_terms(text_l: str, terms: List[str]) -> List[str]:
    found: List[str] = []
    for t in terms:
        if t in text_l:
            found.append(t)
    return list(dict.fromkeys(found))

def _pretty_term(s: str) -> str:
    return " ".join(w.capitalize() if w.isalpha() else w for w in s.split())

def _infer_source_type(text_l: str) -> str:
    if "reuters" in text_l:
        return "Reuters"
    if "bloomberg" in text_l:
        return "Bloomberg"
    if "automotive news" in text_l:
        return "Automotive News"
    if "patent" in text_l:
        return "Patent"
    if "press release" in text_l:
        return "Press Release"
    return "Other"

def _infer_actor_type(text_l: str, gov_entities: List[str], companies: List[str]) -> str:
    reg_verbs = ["mandate", "fine", "ban", "approval", "investigation", "compliance order"]
    reg_score = sum(1 for v in reg_verbs if v in text_l)

    if companies:
        if gov_entities and reg_score >= 1:
            return "regulator"
        return "oem"
    if gov_entities and reg_score >= 1:
        return "regulator"
    return "other"

def _infer_topics(text_l: str) -> List[str]:
    topic_map = [
        ("OEM Strategy & Powertrain Shifts", ["ev", "electric", "hybrid", "powertrain", "platform strategy"]),
        ("Closure Technology & Innovation", ["latch", "door handle", "digital key", "smart entry", "cinch", "access"]),
        ("OEM Programs & Vehicle Platforms", ["program", "vehicle platform", "launch", "facelift", "model year"]),
        ("Regulatory & Safety", ["regulation", "nhtsa", "safety", "compliance", "standard"]),
        ("Supply Chain & Manufacturing", ["plant", "factory", "capacity", "sourcing", "supply chain", "manufacturing"]),
        ("Technology Partnerships & Components", ["partnership", "joint venture", "supplier", "component", "software"]),
        ("Market & Competition", ["market", "competition", "share", "price", "demand"]),
        ("Financial & Business Performance", ["revenue", "profit", "margin", "guidance", "forecast"]),
        ("Executive & Organizational", ["ceo", "executive", "leadership", "organization", "appointed"]),
    ]
    chosen: List[str] = []
    for topic, terms in topic_map:
        if any(t in text_l for t in terms):
            chosen.append(topic)
    if not chosen:
        chosen = ["Market & Competition"]
    return chosen[:3]

def _extract_keywords(text: str, limit: int = 10) -> List[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9\-]{3,}", text.lower())
    stop = {
        "this", "that", "with", "from", "have", "will", "into", "their", "about", "input", "title",
        "first", "section", "paragraphs", "only", "provided", "return", "json", "context", "pack",
    }
    out: List[str] = []
    for w in words:
        if w in stop:
            continue
        if w not in out:
            out.append(w)
        if len(out) >= limit:
            break
    return _fill_to_min(out, min_len=5, filler=["automotive", "closures", "supply", "program", "market"])[:12]

def _region_bucket(country: str) -> Optional[str]:
    c = country.lower()
    if c in {"us", "usa", "united states"}:
        return "US"
    if c == "mexico":
        return "Mexico"
    if c == "thailand":
        return "Thailand"
    if c in {"india"}:
        return "India"
    if c in {"china"}:
        return "China"
    if c in {"russia", "germany", "france", "italy", "spain", "poland", "turkey", "uk", "united kingdom"}:
        return "Europe (including Russia)"
    if c in {"morocco", "south africa"}:
        return "Africa"
    return None

def _regions_relevant(countries: List[str], context_pack: str) -> List[str]:
    regions = []
    for c in countries:
        r = _region_bucket(c)
        if r and r not in regions:
            regions.append(r)
    # include direct region mentions if present
    txt = context_pack.lower()
    for r in FOOTPRINT_REGIONS:
        if r.lower() in txt and r not in regions:
            regions.append(r)
    return regions[:7]

def _infer_priority(text_l: str, topics: List[str]) -> str:
    if "urgent" in text_l or "recall" in text_l or "regulatory & safety" in [t.lower() for t in topics]:
        return "High"
    if "oem programs & vehicle platforms" in [t.lower() for t in topics] or "supply chain & manufacturing" in [t.lower() for t in topics]:
        return "Medium"
    return "Low"

def _evidence_lines(context_pack: str) -> List[str]:
    lines = [ln.strip() for ln in context_pack.splitlines() if ln.strip()]
    candidates = [ln for ln in lines if len(ln.split()) >= 6 and not ln.startswith("TITLE:")]
    out = candidates[:2]
    if len(out) < 2:
        out.extend(["Content extracted from uploaded PDF source text."] * (2 - len(out)))
    return out[:4]

def _insight_lines(topics: List[str]) -> List[str]:
    t1 = topics[0] if topics else "Market & Competition"
    return [
        f"The strongest detected signal aligns with '{t1}'.",
        "The article likely affects near-term planning assumptions for automotive suppliers.",
    ][:4]

def _implication_lines(topics: List[str]) -> List[str]:
    return [
        "Monitor platform/program timing for knock-on effects to closure component demand.",
        "Validate sourcing and regional capacity assumptions against these signals.",
    ][:4]

def _action_lines(topics: List[str]) -> List[str]:
    return [
        "Tag this item for analyst review and confirmation of entities/dates.",
        "Cross-check this signal against current OEM program trackers.",
    ][:6]

def _as_list(v: Any, max_len: int) -> List[str]:
    if v is None:
        return []
    if isinstance(v, list):
        vals = v
    else:
        vals = [v]
    out = [str(x).strip() for x in vals if str(x).strip()]
    return out[:max_len]

def _fill_to_min(items: List[str], min_len: int, filler: List[str]) -> List[str]:
    out = list(items)
    for f in filler:
        if len(out) >= min_len:
            break
        if f not in out:
            out.append(f)
    while len(out) < min_len:
        out.append(filler[-1])
    return out

def try_one_provider(provider: str, context_pack: str) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    log: Dict[str, Any] = {"provider": provider, "attempted_at": utc_now_iso(), "repair_used": False, "errors": []}
    schema = record_response_schema()

    try:
        raw = call_model(provider, extraction_prompt(context_pack), schema)
    except Exception as e:
        log["errors"].append(f"provider_call_error: {e}")
        return None, log
    try:
        rec = json.loads(raw)
    except Exception as e:
        log["errors"].append(f"json_parse_error: {e}")
        rec = None

    if rec is not None:
        rec = postprocess_record(rec)
        ok, errs = validate_record(rec)
        if ok:
            return rec, log
        log["errors"].extend(errs)

    log["repair_used"] = True
    try:
        raw2 = call_model(provider, fix_json_prompt(raw), schema)
    except Exception as e:
        log["errors"].append(f"provider_call_error_after_repair: {e}")
        return None, log
    try:
        rec2 = json.loads(raw2)
    except Exception as e:
        log["errors"].append(f"json_parse_error_after_repair: {e}")
        return None, log

    rec2 = postprocess_record(rec2)
    ok2, errs2 = validate_record(rec2)
    if ok2:
        return rec2, log
    log["errors"].extend(errs2)
    return None, log

def route_and_extract(context_pack: str, provider_choice: str = "auto") -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    chain = AUTO_ORDER if provider_choice == "auto" else [provider_choice]
    router_log: Dict[str, Any] = {"provider_choice": provider_choice, "providers_tried": [], "fallback_used": False}

    for idx, prov in enumerate(chain):
        rec, log = try_one_provider(prov, context_pack)
        router_log["providers_tried"].append(log)
        if rec is not None:
            router_log["fallback_used"] = (idx > 0)
            return rec, router_log

    return None, router_log
