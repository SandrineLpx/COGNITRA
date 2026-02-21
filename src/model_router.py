from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
import json
import os

from src.constants import (
    REQUIRED_KEYS,
    CANON_TOPICS,
    FOOTPRINT_REGIONS,
    ALLOWED_SOURCE_TYPES,
    ALLOWED_ACTOR_TYPES,
    ALLOWED_CONF,
    ALLOWED_REVIEW,
)
from src.quota_tracker import record_call
from src.schema_validate import validate_record
from src.postprocess import postprocess_record
from src.storage import utc_now_iso

# Auto-routing only includes providers implemented in this app.
AUTO_ORDER = ["gemini"]
_NOISE_HIGH_RATIO = 0.18
_NOISE_HIGH_LINES = 250
_NOISE_HIGH_PATTERNS = {"ocr", "table", "header", "footer", "page"}
_NOISE_LOW_RATIO = 0.08
_NOISE_LOW_LINES = 80


def _nullable(schema: Dict[str, Any]) -> Dict[str, Any]:
    return {"any_of": [schema, {"type": "NULL"}]}


def record_response_schema() -> Dict[str, Any]:
    properties = {
        "title": {"type": "STRING"},
        "source_type": {"type": "STRING", "enum": sorted(ALLOWED_SOURCE_TYPES)},
        "publish_date": _nullable({"type": "STRING", "pattern": r"^\d{4}-\d{2}-\d{2}$"}),
        "publish_date_confidence": {"type": "STRING", "enum": sorted(ALLOWED_CONF)},
        "original_url": _nullable({"type": "STRING"}),
        "actor_type": {"type": "STRING", "enum": sorted(ALLOWED_ACTOR_TYPES)},
        "government_entities": {"type": "ARRAY", "items": {"type": "STRING"}},
        "companies_mentioned": {"type": "ARRAY", "items": {"type": "STRING"}},
        "mentions_our_company": {"type": "BOOLEAN"},
        "topics": {
            "type": "ARRAY",
            "items": {"type": "STRING", "enum": CANON_TOPICS},
            "minItems": 1,
            "maxItems": 4,
        },
        "keywords": {"type": "ARRAY", "items": {"type": "STRING"}, "minItems": 3, "maxItems": 15},
        "country_mentions": {"type": "ARRAY", "items": {"type": "STRING"}},
        "regions_mentioned": {"type": "ARRAY", "items": {"type": "STRING"}, "maxItems": 15},
        "regions_relevant_to_apex_mobility": {
            "type": "ARRAY",
            "items": {"type": "STRING", "enum": FOOTPRINT_REGIONS},
        },
        "evidence_bullets": {"type": "ARRAY", "items": {"type": "STRING"}, "minItems": 2, "maxItems": 4},
        "key_insights": {"type": "ARRAY", "items": {"type": "STRING"}, "minItems": 2, "maxItems": 4},
        "review_status": {"type": "STRING", "enum": sorted(ALLOWED_REVIEW)},
        "notes": {"type": "STRING"},
    }
    # Fields added by postprocess, not the LLM — intentionally absent from schema.
    # Only fields that appear in REQUIRED_KEYS need to be here for the guardrail,
    # but we list all computed fields so the whitelist stays complete.
    _COMPUTED_FIELDS = {
        "priority", "confidence",
        "macro_themes_detected",
        "priority_llm", "priority_final", "priority_reason",
        "_publisher_date_override_applied", "_publisher_date_override_source",
        "_confidence_detail",
        "_macro_theme_detail", "_macro_theme_strength", "_macro_theme_rollups",
        "_region_migrations", "_region_ambiguity", "_region_validation_flags",
        "_provenance", "_mutations", "_rule_impact",
    }
    # Guardrail: any REQUIRED_KEY missing from both properties AND the
    # known-computed set is a bug — fail loud at import time.
    unexpected = set(REQUIRED_KEYS) - set(properties.keys()) - _COMPUTED_FIELDS
    if unexpected:
        raise RuntimeError(
            f"Schema misalignment: required keys missing in properties: {sorted(unexpected)}"
        )
    required = [k for k in REQUIRED_KEYS if k in properties]
    return {"type": "OBJECT", "properties": properties, "required": required}


def call_model(provider: str, prompt: str, schema: Dict[str, Any]) -> str:
    """
    Call selected model provider and return JSON text.
    """
    if provider == "gemini":
        text, _usage = _call_gemini(prompt, schema, model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
        return text
    if provider == "claude":
        raise NotImplementedError("Claude provider is not implemented yet.")
    if provider == "chatgpt":
        raise NotImplementedError("ChatGPT provider is not implemented yet.")
    raise ValueError(f"Unsupported provider: {provider}")


def _extract_usage(resp: Any, model_used: str) -> Dict[str, Any]:
    # Gemini API does not return remaining quota; only per-call usage.
    # Quotas/rate limits are checked in AI Studio / GCP.
    usage = getattr(resp, "usage_metadata", None)
    if usage is None:
        return {
            "model": model_used,
            "prompt_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
        }
    return {
        "model": model_used,
        "prompt_tokens": getattr(usage, "prompt_token_count", None),
        "output_tokens": getattr(usage, "candidates_token_count", None),
        "total_tokens": getattr(usage, "total_token_count", None),
    }


def _call_gemini(prompt: str, schema: Dict[str, Any], model: str) -> Tuple[str, Dict[str, Any]]:
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

    record_call(model)
    text = (resp.text or "").strip()
    if not text:
        raise RuntimeError("Gemini API returned empty response text.")
    return text, _extract_usage(resp, model)


def _call_gemini_text(prompt: str, model: str, use_google_search: bool = False) -> Tuple[str, Dict[str, Any]]:
    """Call Gemini for plain-text output (no JSON schema constraint)."""
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

    client = genai.Client(api_key=api_key)
    try:
        config_kwargs: Dict[str, Any] = {"response_mime_type": "text/plain"}
        if use_google_search:
            try:
                config_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]
            except Exception as e:
                raise RuntimeError(f"Gemini web grounding setup failed: {e}") from e

        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(**config_kwargs),
        )
    except Exception as e:
        raise RuntimeError(f"Gemini API call failed: {e}") from e

    record_call(model)
    text = (resp.text or "").strip()
    if not text:
        raise RuntimeError("Gemini API returned empty response text.")
    usage = _extract_usage(resp, model)
    usage["web_check_enabled"] = bool(use_google_search)
    return text, usage


def _should_retry_strong(error_message: str) -> bool:
    m = (error_message or "").lower()
    markers = [
        "schema",
        "response_schema",
        "structured",
        "validation",
        "invalid_argument",
        "json_parse_error",
    ]
    return any(x in m for x in markers)


def choose_extraction_strategy(meta: Dict[str, Any]) -> Dict[str, Any]:
    raw = max(int(meta.get("raw_chars", 1) or 1), 1)
    removed = int(meta.get("removed_chars", 0) or 0)
    removed_ratio = removed / raw
    removed_lines = int(meta.get("removed_line_count", 0) or 0)
    chunks_count = int(meta.get("chunks_count", 0) or 0)
    patterns = {str(p).lower() for p, _ in (meta.get("top_removed_patterns") or [])}

    if removed_ratio > _NOISE_HIGH_RATIO or removed_lines > _NOISE_HIGH_LINES or (patterns & _NOISE_HIGH_PATTERNS):
        noise_level = "high"
    elif removed_ratio < _NOISE_LOW_RATIO and removed_lines < _NOISE_LOW_LINES:
        noise_level = "low"
    else:
        noise_level = "normal"

    lite_model = os.getenv("GEMINI_MODEL_LITE", "gemini-2.5-flash-lite")
    strong_model = os.getenv("GEMINI_MODEL_STRONG", "gemini-2.5-flash")
    primary_model = strong_model if noise_level == "high" else lite_model
    fallback_model = strong_model
    chunked_mode = chunks_count > 1
    routing_reason = "high_noise_use_strong" if noise_level == "high" else "default_lite_then_strong"

    return {
        "primary_model": primary_model,
        "fallback_model": fallback_model,
        "chunked_mode": chunked_mode,
        "routing_reason": routing_reason,
        "routing_metrics": {
            "noise_level": noise_level,
            "chunks_count": chunks_count,
            "raw_chars": raw,
            "clean_chars": int(meta.get("clean_chars", raw - removed) or 0),
            "removed_ratio": round(removed_ratio, 3),
            "removed_line_count": removed_lines,
            "top_removed_patterns": meta.get("top_removed_patterns", []),
        },
    }


def extraction_prompt(context_pack: str) -> str:
    return (
        "You are extracting structured intelligence for Apex Mobility, an automotive closure systems supplier "
        "(door latches, strikers, handles, smart entry, cinch systems). "
        "Return JSON only matching the schema. Follow these rules strictly:\n\n"
        # --- source & actor rules ---
        "1) source_type is the PUBLISHER of the document. If 'S&P Global', 'S&P Global Mobility', "
        "'AutoIntelligence | Headline Analysis', or '(c) S&P Global' appears, set source_type='S&P'. "
        "If MarkLines is the publisher, set source_type='MarkLines'.\n"
        "2) If Reuters or Bloomberg is only cited inside the article, do NOT set source_type to Reuters/Bloomberg "
        "unless they are clearly the publisher. "
        "Use 'Financial News' for financial publications (WSJ, FT, CNBC, Nikkei) and "
        "'Industry Publication' for automotive trade press (Automotive Logistics, Just Auto, Wards Auto, etc.) "
        "that are not Automotive News. Use 'Other' only when no specific type fits.\n"
        "3) actor_type must be one of: oem, supplier, technology, industry, other. "
        "Use 'supplier' for the closure system competitors listed below. "
        "Use 'technology' for tech companies (Nvidia, Qualcomm, Huawei, Google, etc.); "
        "use 'industry' for broad market/sector items not tied to one company; "
        "use 'oem' for vehicle manufacturers; use 'other' when none of the above fit.\n\n"
        # --- competitor context (adjacent to actor_type rule) ---
        "CLOSURE SYSTEMS COMPETITORS — set actor_type='supplier' for these companies:\n"
        "Tier 1: Hi-Lex, Aisin, Brose, Huf, Magna (Magna Closures/Mechatronics), Inteva, Mitsui Kinzoku\n"
        "Tier 2: Ushin, Witte, Mitsuba, Fudi (BYD subsidiary), PHA, Cebi, Tri-Circle\n"
        "Our company: Apex Mobility (set mentions_our_company=true if mentioned)\n\n"
        "4) publish_date: extract and normalize to YYYY-MM-DD when present. Handle patterns like '4 Feb 2026', "
        "'11 Feb 2026', 'Feb. 4, 2026', 'February 4, 2026'. Else return null.\n\n"
        # --- topic classification guidance ---
        "TOPIC CLASSIFICATION — pick 1-4 topics using these rules:\n"
        "- 'OEM Strategy & Powertrain Shifts': broad OEM strategic pivots (BEV/ICE mix, vertical integration, "
        "platform resets, localization). NOT single program updates.\n"
        "- 'Closure Technology & Innovation': ONLY when latch/door/handle/digital key/smart entry/cinch "
        "appears explicitly. NOT general vehicle electronics.\n"
        "- 'OEM Programs & Vehicle Platforms': specific program announcements (launches, refreshes, platform "
        "rollouts, sourcing decisions). NOT broad strategy narratives.\n"
        "- 'Regulatory & Safety': regulations, standards, recalls, cybersecurity rules. NOT general political news.\n"
        "- 'Supply Chain & Manufacturing': plant openings/closures, disruptions, logistics, labor, tariffs "
        "impacting supply execution. NOT pure financial performance.\n"
        "- 'Technology Partnerships & Components': partnerships and component sourcing where tech is central "
        "(chips, sensors, connectivity). NOT purely commercial alliances.\n"
        "- 'Market & Competition': demand, registrations, pricing, share shifts, competitor comparisons. "
        "NOT internal exec changes.\n"
        "- 'Financial & Business Performance': earnings, guidance, M&A, restructurings, insolvency (financial lens). "
        "NOT exec churn without financial angle.\n"
        "- 'Executive & Organizational': leadership changes, governance, org restructuring.\n\n"
        # --- evidence & output rules ---
        "5) evidence_bullets must be 2-4 short factual bullets, each <= 25 words. "
        "Extract verbatim facts and data points directly from the source text. No interpretation.\n"
        "6) key_insights must be 2-4 analytical bullets interpreting what the facts mean — "
        "implications for OEMs, suppliers, or the automotive market. "
        "Do NOT repeat evidence_bullets verbatim; add analytical value (e.g., 'This signals...', 'Risk for...', 'Opportunity in...').\n"
        "7) If numeric facts are present in the article, at least one evidence_bullet must include a specific numeric value verbatim "
        "(e.g., percentage change, margin %, profit forecast, sales delta, production volume, year-over-year change, ranking gap). "
        "Prefer financial/competitive metrics over feature numbers. "
        "Do not fabricate, infer, or calculate numbers. "
        "If no numeric facts are present, proceed normally.\n"
        "8) government_entities: list ONLY government bodies, regulators, or agencies explicitly named in the text "
        "(e.g. 'NHTSA', 'European Commission', 'French Ministry of Industry'). "
        "Do NOT infer entities from country context alone — if the text says 'the government' in a France/Spain context "
        "but never names the EU or a specific agency, return an empty list. "
        "If none are explicitly named, return [].\n"
        "9) If the article mentions major software/AI features (e.g., AI voice controls, SDV, infotainment, autonomy), "
        "include at least one evidence_bullet on that feature.\n"
        "10) country_mentions: list ONLY countries where the article explicitly reports operational market data "
        "(production volumes, vehicle registrations, plant locations, sales, revenue for that country). "
        "Do NOT include a country mentioned only as geopolitical backdrop, tariff reference, or macro context "
        "(e.g., 'US tariff conflicts' with no US market data → do not include United States). "
        "regions_mentioned: list the geographic regions covered by the article's scope. "
        "Use only these valid values — sub-regional buckets: West Europe, Central Europe, East Europe, "
        "Africa, Middle East, NAFTA, ASEAN, Indian Subcontinent, Andean, Mercosul, Central America, "
        "Oceania, Rest of World; generic catch-alls: Europe, South America, South Asia; "
        "individual Apex Mobility-relevant countries: Czech Republic, France, Germany, Italy, Morocco, Mexico, "
        "Portugal, Russia, Spain, Sweden, United Kingdom, United States, Thailand, India, "
        "China, Taiwan, Japan, South Korea.\n"
        "11) keywords: capture the key topics, technologies, policies, and actors of the article. "
        "Include brand and company names that play a material role in the article (OEMs, suppliers, tech companies) "
        "even if already in companies_mentioned — they anchor the thematic context. "
        "Do NOT include country or region names (already in country_mentions/regions_mentioned), "
        "publisher names (already in source_type), "
        "or generic measurement phrases ('year over year', month names, 'Q1', 'fiscal year').\n"
        "12) Deduplicate all list fields. Normalize common abbreviations to canonical form: "
        "US/USA/U.S. → 'United States', UK/U.K. → 'United Kingdom', EU/E.U. → 'European Union'.\n"
        "13) notes: leave empty unless there is important context not captured by other fields "
        "(e.g., conflicting data in the article, a quality concern about the source, or a key caveat). "
        "Do not repeat evidence bullets here.\n"
        "Use only the provided text.\n\nINPUT (context pack):\n"
        + context_pack
    )


def extract_single_pass(context_pack: str, model: str) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """One-shot extraction with a specific model. No fallback/repair."""
    log: Dict[str, Any] = {"model": model, "attempted_at": utc_now_iso(), "errors": []}
    schema = record_response_schema()
    prompt = extraction_prompt(context_pack)
    try:
        raw, usage = _call_gemini(prompt, schema, model=model)
        log["usage"] = usage
    except Exception as e:
        log["errors"].append(f"call_error: {e}")
        return None, log
    try:
        rec = json.loads(raw)
    except Exception as e:
        log["errors"].append(f"json_parse: {e}")
        return None, log
    if not isinstance(rec, dict):
        log["errors"].append("not_a_dict")
        return None, log
    rec = postprocess_record(rec, source_text=context_pack)
    ok, errs = validate_record(rec)
    if ok:
        return rec, log
    log["errors"].extend(errs)
    return None, log


def fix_json_prompt(broken: str, validation_errors: List[str]) -> str:
    err_block = "\n".join(f"- {e}" for e in validation_errors[:30])
    return (
        "Fix the JSON below so it is valid and matches the schema exactly. "
        "Do not invent facts. Keep existing facts, only repair schema/format issues. Return JSON only.\n\n"
        "Validation errors:\n"
        + err_block
        + "\n\nBROKEN JSON:\n"
        + broken
    )


def try_one_provider(
    provider: str,
    context_pack: str,
    primary_model: Optional[str] = None,
    fallback_model: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    log: Dict[str, Any] = {
        "provider": provider,
        "attempted_at": utc_now_iso(),
        "repair_used": False,
        "errors": [],
    }
    schema = record_response_schema()
    if provider != "gemini":
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

        if isinstance(rec, dict):
            rec = postprocess_record(rec, source_text=context_pack)
            ok, errs = validate_record(rec)
            if ok:
                return rec, log
            log["errors"].extend(errs)
        elif rec is not None:
            log["errors"].append("json_parse_error: model response must be a JSON object")

        log["repair_used"] = True
        try:
            raw2 = call_model(provider, fix_json_prompt(raw, log["errors"]), schema)
        except Exception as e:
            log["errors"].append(f"provider_call_error_after_repair: {e}")
            return None, log

        try:
            rec2 = json.loads(raw2)
        except Exception as e:
            log["errors"].append(f"json_parse_error_after_repair: {e}")
            return None, log

        if not isinstance(rec2, dict):
            log["errors"].append("json_parse_error_after_repair: model response must be a JSON object")
            return None, log

        rec2 = postprocess_record(rec2, source_text=context_pack)
        ok2, errs2 = validate_record(rec2)
        if ok2:
            return rec2, log
        log["errors"].extend(errs2)
        return None, log

    # Gemini 2-stage strategy: flash-lite then flash.
    lite_model = primary_model or os.getenv("GEMINI_MODEL_LITE", "gemini-2.5-flash-lite")
    strong_model = fallback_model or os.getenv("GEMINI_MODEL_STRONG", "gemini-2.5-flash")
    log["model_strategy"] = [lite_model, strong_model]
    log["calls"] = []

    prompt = extraction_prompt(context_pack)
    raw_for_repair = ""
    need_strong = False

    try:
        raw, usage = _call_gemini(prompt, schema, model=lite_model)
        raw_for_repair = raw
        log["usage"] = usage
        log["calls"].append({"stage": "initial", "model": lite_model, "usage": usage, "status": "ok"})
    except Exception as e:
        err = f"provider_call_error: {e}"
        log["errors"].append(err)
        log["calls"].append({"stage": "initial", "model": lite_model, "usage": None, "status": "error", "error": str(e)})
        need_strong = _should_retry_strong(err)
        if not need_strong:
            return None, log
    else:
        try:
            rec = json.loads(raw)
        except Exception as e:
            log["errors"].append(f"json_parse_error: {e}")
            rec = None
            need_strong = True

        if isinstance(rec, dict):
            rec = postprocess_record(rec, source_text=context_pack)
            ok, errs = validate_record(rec)
            if ok:
                return rec, log
            log["errors"].extend(errs)
            need_strong = True
        elif rec is not None:
            log["errors"].append("json_parse_error: model response must be a JSON object")
            need_strong = True

    if not need_strong:
        return None, log

    log["repair_used"] = True
    repair_prompt = fix_json_prompt(raw_for_repair, log["errors"])
    try:
        raw2, usage2 = _call_gemini(repair_prompt, schema, model=strong_model)
        log["usage"] = usage2
        log["calls"].append({"stage": "repair", "model": strong_model, "usage": usage2, "status": "ok"})
    except Exception as e:
        log["errors"].append(f"provider_call_error_after_repair: {e}")
        log["calls"].append({"stage": "repair", "model": strong_model, "usage": None, "status": "error", "error": str(e)})
        return None, log

    try:
        rec2 = json.loads(raw2)
    except Exception as e:
        log["errors"].append(f"json_parse_error_after_repair: {e}")
        return None, log

    if not isinstance(rec2, dict):
        log["errors"].append("json_parse_error_after_repair: model response must be a JSON object")
        return None, log

    rec2 = postprocess_record(rec2, source_text=context_pack)
    ok2, errs2 = validate_record(rec2)
    if ok2:
        return rec2, log

    log["errors"].extend(errs2)
    return None, log


def route_and_extract(
    context_pack: str,
    provider_choice: str = "auto",
    primary_model: Optional[str] = None,
    fallback_model: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    chain = AUTO_ORDER if provider_choice == "auto" else [provider_choice]
    router_log: Dict[str, Any] = {"provider_choice": provider_choice, "providers_tried": [], "fallback_used": False}

    for idx, prov in enumerate(chain):
        rec, log = try_one_provider(
            prov,
            context_pack,
            primary_model=primary_model,
            fallback_model=fallback_model,
        )
        router_log["providers_tried"].append(log)
        if rec is not None:
            router_log["fallback_used"] = idx > 0
            return rec, router_log

    return None, router_log
