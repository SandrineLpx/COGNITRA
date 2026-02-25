from __future__ import annotations

import base64
from collections import Counter
from datetime import datetime, timezone
import html
import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

import src.ui as ui
from src.context_pack import select_context_chunks
from src.model_router import choose_extraction_strategy, extract_single_pass, route_and_extract
from src.pdf_extract import extract_pdf_publish_date_hint, extract_text_robust
from src.postprocess import postprocess_record
from src.render_brief import render_intelligence_brief
from src.schema_validate import ALLOWED_SOURCE_TYPES, validate_record
from src.text_clean_chunk import clean_and_chunk
from src.storage import PDF_DIR, overwrite_records
from src.ui_helpers import (
    best_record_link,
    clear_records_cache,
    enforce_navigation_lock,
    join_list,
    latest_brief_entry_for_record,
    load_brief_history,
    load_records_cached,
    normalize_review_status,
    render_navigation_lock_notice,
    safe_list,
    set_navigation_lock,
)

_RULE_LABELS = {
    "url_normalization": "URL normalized",
    "regions_bucketed_deduped": "Regions bucketed/deduped",
    "footprint_and_key_oem": "Priority boost: footprint + key OEM",
    "final_priority_after_rules": "Final priority set",
    "priority_changed_by_rules": "Priority changed by rules",
    "computed_confidence": "Confidence recomputed",
}
_PT_TZ = ZoneInfo("America/Los_Angeles")
_HAS_STREAMLIT_PDF = bool(importlib.util.find_spec("streamlit_pdf"))

def _friendly_rule_name(rule: str) -> str:
    key = str(rule or "")
    if key in _RULE_LABELS:
        return _RULE_LABELS[key]
    return key.replace("_", " ").strip().capitalize() or "Unknown rule"


def _render_rule_impact_summary(rule_counts: dict, max_rows: int = 5) -> None:
    if not isinstance(rule_counts, dict) or not rule_counts:
        st.caption("No overrides yet.")
        return
    top = sorted(rule_counts.items(), key=lambda x: int(x[1]), reverse=True)[:max_rows]
    total = sum(int(v) for _k, v in top)
    st.caption(f"{total} override(s) across {len(top)} top rule(s).")
    for rule, count in top:
        rule_key = str(rule)
        label = _friendly_rule_name(rule_key)
        st.caption(f"- {label}: {int(count)}")


def _normalize_filter_tokens(query: str) -> List[str]:
    normalized = " ".join(str(query or "").lower().replace(",", " ").split())
    return [tok for tok in normalized.split(" ") if tok]


def _unique_non_empty(values: List[Any]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for value in values:
        s = str(value or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _brief_entry_file_name(entry: Dict[str, Any]) -> str:
    return Path(str(entry.get("file") or "")).name


def _brief_entry_label(entry: Dict[str, Any]) -> str:
    file_name = _brief_entry_file_name(entry)
    week_range = str(entry.get("week_range") or "").strip()
    if file_name and week_range:
        return f"{file_name} ({week_range})"
    return file_name or week_range


def _brief_membership_labels(entries: List[Dict[str, Any]]) -> List[str]:
    labels = [_brief_entry_label(entry) for entry in entries if isinstance(entry, dict)]
    return _unique_non_empty(labels)


def _brief_membership_summary(entries: List[Dict[str, Any]], max_items: int = 2) -> str:
    labels = _brief_membership_labels(entries)
    if not labels:
        return ""
    if len(labels) <= max_items:
        return "; ".join(labels)
    return "; ".join(labels[:max_items]) + f"; +{len(labels) - max_items} more"


def _review_filter_blob(row: pd.Series) -> str:
    parts: List[str] = []
    scalar_fields = [
        "record_id",
        "title",
        "source_type",
        "publish_date",
        "created_at",
        "priority",
        "confidence",
        "review_status",
        "latest_brief_week_range",
        "brief_membership_summary",
    ]
    list_fields = [
        "regions_relevant_to_apex_mobility",
        "macro_themes_detected",
        "topics",
        "brief_files",
        "brief_week_ranges",
    ]
    for key in scalar_fields:
        value = str(row.get(key) or "").strip()
        if value:
            parts.append(value)
    for key in list_fields:
        values = row.get(key) or []
        if isinstance(values, list):
            parts.extend(str(v).strip() for v in values if str(v).strip())

    companies = str(row.get("_companies_joined") or "").strip()
    if companies:
        parts.append(companies)
    in_brief = "yes" if bool(row.get("in_brief")) else "no"
    parts.append(f"in_brief {in_brief}")
    return " ".join(parts).lower()


def _review_matches_tokens(row: pd.Series, tokens: List[str]) -> bool:
    if not tokens:
        return True
    blob = _review_filter_blob(row)
    return all(token in blob for token in tokens)



st.set_page_config(page_title="Cognitra", page_icon="assets/logo/cognitra-icon.png", layout="wide")
enforce_navigation_lock("review")
ui.init_page(active_step="Review")
ui.render_page_header(
    "Review",
    subtitle="Validate structured intelligence records before approval. Each record is scored and requires analyst confirmation.",
    active_step="Review",
)
render_navigation_lock_notice("review")

ui.render_sidebar_utilities(
    model_label="auto",
    overrides=st.session_state.get("rule_impact_review_run", {}),
)

def _is_valid_iso_date(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except Exception:
        return False


def _render_pdf_embed(pdf_path: Optional[Path], height: int = 620) -> None:
    if not pdf_path:
        st.caption("No original PDF attached.")
        return

    try:
        pdf_bytes = pdf_path.read_bytes()
    except Exception as exc:
        st.caption(f"PDF exists but could not be read: {exc}")
        return

    if not pdf_bytes:
        st.caption("Original PDF is empty.")
        return

    native_error = ""
    try:
        # Native Streamlit PDF viewer (requires streamlit-pdf extra package).
        if _HAS_STREAMLIT_PDF:
            st.pdf(pdf_bytes, height=int(height))
            return
    except Exception as exc:
        native_error = str(exc)

    # Fallback: browser iframe data URI.
    try:
        pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
        st.markdown(
            (
                f'<iframe src="data:application/pdf;base64,{pdf_b64}" '
                f'width="100%" height="{int(height)}px" style="border:0;"></iframe>'
            ),
            unsafe_allow_html=True,
        )
        if not _HAS_STREAMLIT_PDF:
            st.caption("Using fallback viewer (install `streamlit[pdf]` for native PDF rendering).")
        elif native_error:
            st.caption("Using fallback viewer (native renderer unavailable for this file).")
        return
    except Exception as exc:
        st.caption(f"PDF exists but could not be rendered. {exc}")


def _resolve_record_pdf_path(rec: Optional[Dict[str, Any]]) -> tuple[str, Optional[Path], str]:
    """Resolve attached PDF path from record field, then fallback by record_id in data/pdfs."""
    if not isinstance(rec, dict):
        return "", None, "none"

    raw = str(rec.get("source_pdf_path") or "").strip()
    if raw:
        direct = Path(raw).expanduser()
        if direct.exists():
            return raw, direct, "record_path"
        # Fallback: keep filename, resolve under canonical PDF_DIR.
        by_name = PDF_DIR / direct.name
        if by_name.exists():
            return raw, by_name, "path_filename_fallback"

    rid = str(rec.get("record_id") or "").strip()
    if rid:
        matches = sorted(PDF_DIR.glob(f"{rid}__*.pdf"), key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
        if matches:
            return raw, matches[0], "record_id_fallback"

    return raw, None, "none"


def _postprocess_with_checks(
    rec: Dict[str, Any],
    source_text: str,
    publish_date_hint: Optional[str] = None,
    publish_date_hint_source: Optional[str] = None,
) -> Dict[str, Any]:
    before_publish = rec.get("publish_date")
    rec = postprocess_record(
        rec,
        source_text=source_text,
        publish_date_hint=publish_date_hint,
        publish_date_hint_source=publish_date_hint_source,
    )
    if not isinstance(rec.get("_provenance"), dict):
        rec["_provenance"] = {}
    if not isinstance(rec.get("_mutations"), list):
        rec["_mutations"] = []
    if not isinstance(rec.get("_rule_impact"), dict):
        rec["_rule_impact"] = {}
    publish_source = str(rec.get("_provenance", {}).get("publish_date", {}).get("source") or "")
    if (
        _is_valid_iso_date(before_publish)
        and rec.get("publish_date") != before_publish
        and not (
            publish_source.endswith("_header_publish_date")
            or publish_source == "rule:pdf_metadata_publish_date"
        )
    ):
        raise ValueError("postprocess changed existing valid publish_date")
    review_run_impact = st.session_state.setdefault("rule_impact_review_run", {})
    for rule, count in rec.get("_rule_impact", {}).items():
        review_run_impact[rule] = int(review_run_impact.get(rule, 0)) + int(count or 0)
    return rec


def _dedupe_keep_order(values: Any) -> List[str]:
    out: List[str] = []
    seen = set()
    for v in values:
        s = str(v).strip()
        if not s:
            continue
        k = s.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out


def _pick_publish_date(recs: List[Dict[str, Any]]) -> tuple[str, str]:
    conf_rank = {"High": 3, "Medium": 2, "Low": 1}
    best = ("", "Low")
    best_key = (-1, datetime.min)
    for row in recs:
        pd = row.get("publish_date")
        if not pd:
            continue
        try:
            dt = datetime.strptime(str(pd), "%Y-%m-%d")
        except Exception:
            continue
        conf = str(row.get("publish_date_confidence") or "Low")
        key = (conf_rank.get(conf, 0), dt)
        if key > best_key:
            best_key = key
            best = (str(pd), conf)
    return best


def _merge_chunk_records(chunk_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    source_votes = [str(r.get("source_type") or "Other") for r in chunk_records]
    non_other = [s for s in source_votes if s != "Other"]
    source_type = Counter(non_other).most_common(1)[0][0] if non_other else Counter(source_votes).most_common(1)[0][0]

    actor_votes = [str(r.get("actor_type") or "") for r in chunk_records if r.get("actor_type")]
    actor_counts = Counter(actor_votes)
    if actor_counts:
        max_votes = max(actor_counts.values())
        top_actors = [k for k, v in actor_counts.items() if v == max_votes]
        if len(top_actors) == 1:
            actor_choice = top_actors[0]
        else:
            has_companies = any((r.get("companies_mentioned") or []) for r in chunk_records)
            actor_choice = "oem" if has_companies else "media"
    else:
        actor_choice = "media"

    title = next((str(r.get("title")).strip() for r in chunk_records if str(r.get("title") or "").strip()), "Untitled PDF Brief")
    original_url = next((str(r.get("original_url")).strip() for r in chunk_records if str(r.get("original_url") or "").strip()), None)
    publish_date, publish_date_conf = _pick_publish_date(chunk_records)

    merged = {
        "title": title,
        "source_type": source_type,
        "publish_date": publish_date or None,
        "publish_date_confidence": publish_date_conf,
        "original_url": original_url,
        "actor_type": actor_choice,
        "government_entities": _dedupe_keep_order(x for r in chunk_records for x in (r.get("government_entities") or [])),
        "companies_mentioned": _dedupe_keep_order(x for r in chunk_records for x in (r.get("companies_mentioned") or [])),
        "mentions_our_company": any(bool(r.get("mentions_our_company")) for r in chunk_records),
        "topics": _dedupe_keep_order(x for r in chunk_records for x in (r.get("topics") or []))[:3],
        "keywords": _dedupe_keep_order(x for r in chunk_records for x in (r.get("keywords") or []))[:12],
        "country_mentions": _dedupe_keep_order(x for r in chunk_records for x in (r.get("country_mentions") or [])),
        "regions_mentioned": _dedupe_keep_order(x for r in chunk_records for x in (r.get("regions_mentioned") or [])),
        "regions_relevant_to_apex_mobility": _dedupe_keep_order(x for r in chunk_records for x in (r.get("regions_relevant_to_apex_mobility") or [])),
        "priority": "Medium",
        "confidence": "Medium",
        "key_insights": _dedupe_keep_order(x for r in chunk_records for x in (r.get("key_insights") or []))[:4],
        "review_status": "Pending",
        "notes": f"Merged from {len(chunk_records)} chunk extractions.",
    }

    all_bullets = _dedupe_keep_order(x for r in chunk_records for x in (r.get("evidence_bullets") or []))
    short_bullets = [b for b in all_bullets if len(b.split()) <= 25]
    merged["evidence_bullets"] = (short_bullets or all_bullets)[:4]
    if len(merged["evidence_bullets"]) < 2:
        merged["evidence_bullets"] = (merged["evidence_bullets"] + ["Evidence extracted from cleaned document chunks."])[:2]

    if actor_choice == "other":
        merged["actor_type"] = "oem" if merged["companies_mentioned"] else "media"
    return merged


def _humanize_router_failure(router_log: Dict[str, Any]) -> str:
    providers = router_log.get("providers_tried", []) if isinstance(router_log, dict) else []
    if not providers:
        return "Failed: model extraction failed."
    lines: List[str] = []
    saw_gemini_503 = False
    for prov in providers:
        name = str(prov.get("provider", "unknown")).lower()
        errs = prov.get("errors") or []
        if not errs:
            continue
        top = str(errs[0])
        top_lower = top.lower()
        if name == "gemini" and ("503" in top_lower or "unavailable" in top_lower):
            saw_gemini_503 = True
            lines.append("Gemini: temporarily unavailable (503 high demand). Retry shortly.")
            continue
        if name in ("claude", "chatgpt") and "not implemented yet" in top_lower:
            lines.append(f"{name.capitalize()}: provider is not implemented in this app.")
            continue
        lines.append(f"{name.capitalize()}: {top}")
    if not lines:
        return "Failed: model extraction failed. Check provider logs."
    prefix = "Failed: model extraction failed."
    if saw_gemini_503:
        prefix = "Failed: Gemini is temporarily overloaded (503)."
    return prefix + " " + " ".join(lines)


def _reset_record_editor_state(record_id: str) -> None:
    rid = str(record_id or "")
    if not rid:
        return
    for prefix in ("status_", "exclude_", "reviewed_by_", "notes_", "json_editor_"):
        st.session_state.pop(f"{prefix}{rid}", None)


def _parse_iso_date(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if len(s) == 10:
        try:
            return datetime.strptime(s, "%Y-%m-%d")
        except Exception:
            return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _created_date_pt_label(value: Any) -> str:
    dt = _parse_iso_date(value)
    if dt is None:
        return "-"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        dt = dt.astimezone(_PT_TZ)
    except Exception:
        pass
    return dt.strftime("%Y-%m-%d")


def _auto_approve_eligible(rec: Dict[str, Any]) -> bool:
    return (
        str(rec.get("confidence") or "") in ("High", "Medium")
        and bool(rec.get("publish_date"))
        and str(rec.get("source_type") or "Other") != "Other"
        and len(rec.get("evidence_bullets") or []) >= 2
    )


def _priority_reason_sentence(rec: Dict[str, Any]) -> str:
    explicit = str(rec.get("priority_reason") or "").strip()
    if explicit:
        return explicit
    impact = rec.get("_rule_impact") or {}
    if isinstance(impact, dict) and impact:
        top = sorted(impact.items(), key=lambda x: int(x[1]), reverse=True)[0][0]
        return _friendly_rule_name(str(top))
    prov = rec.get("_provenance") or {}
    if isinstance(prov, dict):
        p = prov.get("priority_final") or {}
        reason = str((p.get("reason") if isinstance(p, dict) else "") or "").strip()
        if reason:
            return reason
    return "No priority boost rule recorded."


def _confidence_driver_lines(rec: Dict[str, Any]) -> List[str]:
    detail = rec.get("_confidence_detail") or {}
    signals = detail.get("signals") if isinstance(detail, dict) else {}
    if not isinstance(signals, dict) or not signals:
        return []
    rows: List[str] = []
    for k, v in sorted(signals.items(), key=lambda x: abs(float(x[1] or 0)), reverse=True):
        key = str(k).replace("_", " ")
        try:
            score = int(v)
        except Exception:
            score = 0
        sign = "+" if score > 0 else ""
        rows.append(f"{key}: {sign}{score}")
    return rows[:8]


def _macro_theme_diag(rec: Dict[str, Any]) -> List[Dict[str, str]]:
    detail = rec.get("_macro_theme_detail") or {}
    if not isinstance(detail, dict) or not detail:
        return []
    rows: List[Dict[str, str]] = []
    for theme_name, meta in detail.items():
        if not isinstance(meta, dict):
            continue
        groups = ", ".join(str(x) for x in (meta.get("groups_matched") or [])) or "-"
        gates: List[str] = []
        if meta.get("suppressed_by_premium_gate"):
            gates.append("premium gate")
        if meta.get("suppressed_by_region_requirement"):
            gates.append("region requirement")
        rows.append(
            {
                "Theme": str(theme_name),
                "Fired": "Yes" if bool(meta.get("fired")) else "No",
                "Groups matched": groups,
                "Gate checks": ", ".join(gates) if gates else "-",
            }
        )
    return rows


def _json_editor_hints(errs: List[str]) -> List[str]:
    hints: List[str] = []
    if not errs:
        return hints

    missing = [str(e).split("Missing key:", 1)[1].strip() for e in errs if str(e).startswith("Missing key:")]
    if missing:
        hints.append("Missing required keys: " + ", ".join(sorted(set(missing))))

    if any("source_type must be one of" in str(e) for e in errs):
        hints.append("Invalid `source_type`. Allowed values: " + ", ".join(sorted(ALLOWED_SOURCE_TYPES)))

    if any("publish_date must be YYYY-MM-DD" in str(e) for e in errs):
        hints.append("`publish_date` must use `YYYY-MM-DD` format (for example `2026-02-20`), empty string, or null.")

    if any("review_status must be one of" in str(e) for e in errs):
        hints.append("`review_status` must be one of: Pending, Approved, Disapproved.")

    if any("topics contains non-canonical labels" in str(e) for e in errs):
        hints.append("`topics` has non-canonical labels. Use topic values already present in valid records.")

    if any("regions_mentioned contains invalid labels" in str(e) for e in errs):
        hints.append("`regions_mentioned` contains unsupported display-region labels.")

    if any("regions_relevant_to_apex_mobility contains invalid labels" in str(e) for e in errs):
        hints.append("`regions_relevant_to_apex_mobility` contains unsupported footprint-region labels.")

    return hints


def _process_one_pdf_reingest(
    pdf_bytes: bytes,
    filename: str,
    provider_choice: str,
    override_title: str = "",
    override_url: str = "",
) -> tuple[Optional[Dict[str, Any]], Dict[str, Any], str]:
    extracted_text, _method = extract_text_robust(pdf_bytes)
    if not extracted_text.strip():
        return None, {}, "Failed: no text extracted"
    publish_date_hint, publish_date_hint_source = extract_pdf_publish_date_hint(pdf_bytes, extracted_text)

    cleaned = clean_and_chunk(extracted_text)
    cleaned_text = cleaned["clean_text"]
    cleaned_chunks = cleaned["chunks"]
    strategy = choose_extraction_strategy(cleaned.get("meta", {}))
    effective_chunked = bool(strategy.get("chunked_mode"))

    if effective_chunked and cleaned_chunks:
        initial_model = strategy["primary_model"]
        strong_model = strategy["fallback_model"]
        used_lite = initial_model != strong_model

        chunk_records: Dict[int, Dict[str, Any]] = {}
        chunk_logs: List[Dict[str, Any]] = []
        failed_idxs: List[int] = []
        for idx, chunk in enumerate(cleaned_chunks):
            rec_i, log_i = extract_single_pass(chunk, model=initial_model)
            log_i["chunk_id"] = f"{idx + 1}/{len(cleaned_chunks)}"
            log_i["phase"] = "initial"
            chunk_logs.append(log_i)
            if rec_i is not None:
                chunk_records[idx] = rec_i
            else:
                failed_idxs.append(idx)

        if failed_idxs and used_lite:
            for idx in failed_idxs:
                rec_i, log_i = extract_single_pass(cleaned_chunks[idx], model=strong_model)
                log_i["chunk_id"] = f"{idx + 1}/{len(cleaned_chunks)}"
                log_i["phase"] = "repair"
                chunk_logs.append(log_i)
                if rec_i is not None:
                    chunk_records[idx] = rec_i

        if not chunk_records:
            return None, {"chunked_mode": True, "chunk_logs": chunk_logs}, "Failed: all chunk extractions failed validation"

        rec = _merge_chunk_records(list(chunk_records.values()))
        router_log: Dict[str, Any] = {
            "provider_choice": provider_choice,
            "chunked_mode": True,
            "routing_reason": strategy.get("routing_reason"),
            "routing_metrics": strategy.get("routing_metrics", {}),
            "initial_model": initial_model,
            "chunks_total": len(cleaned_chunks),
            "chunks_succeeded_initial": len(cleaned_chunks) - len(failed_idxs),
            "chunks_repaired": len(chunk_records) - (len(cleaned_chunks) - len(failed_idxs)),
            "chunks_failed_final": len(cleaned_chunks) - len(chunk_records),
            "chunk_logs": chunk_logs,
        }
        if override_url and not rec.get("original_url"):
            rec["original_url"] = override_url
        rec = _postprocess_with_checks(
            rec,
            source_text=cleaned_text,
            publish_date_hint=publish_date_hint,
            publish_date_hint_source=publish_date_hint_source,
        )
        ok, errs = validate_record(rec)
        if not ok:
            return None, router_log, f"Failed: validation errors: {'; '.join(errs[:3])}"
    else:
        watch_terms: List[str] = []
        topic_terms = [
            "tariff", "plant", "capacity", "joint venture", "platform", "EV", "battery",
            "latch", "door handle", "supplier", "production", "recall", "regulation",
        ]
        selected = select_context_chunks(
            override_title or filename,
            cleaned_text,
            watch_terms,
            topic_terms,
            user_provided_url=override_url,
        )
        context_pack = selected["context_pack"]
        rec, router_log = route_and_extract(
            context_pack,
            provider_choice=provider_choice,
            primary_model=strategy["primary_model"],
            fallback_model=strategy["fallback_model"],
        )
        router_log["routing_reason"] = strategy.get("routing_reason")
        router_log["routing_metrics"] = strategy.get("routing_metrics", {})
        router_log["chunked_mode"] = False

        if rec is None:
            return None, router_log, _humanize_router_failure(router_log)
        if override_url and not rec.get("original_url"):
            rec["original_url"] = override_url
        try:
            rec = _postprocess_with_checks(
                rec,
                source_text=context_pack,
                publish_date_hint=publish_date_hint,
                publish_date_hint_source=publish_date_hint_source,
            )
        except Exception:
            pass

    if override_title:
        rec["title"] = override_title
    return rec, router_log, "OK"

records = load_records_cached()
if not records:
    st.info("No records yet. Go to Ingest to process a PDF.")
    st.stop()

rows = []
brief_history = load_brief_history()
for rec in records:
    created_dt_raw = pd.to_datetime(rec.get("created_at"), errors="coerce", utc=True)
    created_dt = (
        created_dt_raw.tz_convert(_PT_TZ).tz_localize(None)
        if pd.notna(created_dt_raw)
        else pd.NaT
    )
    publish_dt = pd.to_datetime(rec.get("publish_date"), errors="coerce")
    rec_id = str(rec.get("record_id") or "")
    shared_rows = [x for x in (brief_history.get(rec_id) or []) if isinstance(x, dict)]
    latest_shared = latest_brief_entry_for_record(brief_history, rec_id)
    brief_labels = _brief_membership_labels(shared_rows)
    brief_files = _unique_non_empty([_brief_entry_file_name(entry) for entry in shared_rows])
    brief_week_ranges = _unique_non_empty([entry.get("week_range") for entry in shared_rows])
    rows.append(
        {
            "record_id": rec_id,
            "title": str(rec.get("title") or "Untitled"),
            "source_type": str(rec.get("source_type") or "Other"),
            "publish_date": str(rec.get("publish_date") or ""),
            "created_at": str(rec.get("created_at") or ""),
            "priority": str(rec.get("priority") or "Medium"),
            "confidence": str(rec.get("confidence") or "Medium"),
            "review_status": normalize_review_status(rec.get("review_status")),
            "is_duplicate": bool(rec.get("is_duplicate", False)),
            "regions_relevant_to_apex_mobility": safe_list(rec.get("regions_relevant_to_apex_mobility")),
            "macro_themes_detected": safe_list(rec.get("macro_themes_detected")),
            "topics": safe_list(rec.get("topics")),
            "in_brief": bool(shared_rows),
            "brief_count": len(brief_labels),
            "brief_files": brief_files,
            "brief_week_ranges": brief_week_ranges,
            "brief_membership_summary": _brief_membership_summary(shared_rows),
            "latest_brief_file": str(latest_shared.get("file") or ""),
            "latest_brief_week_range": str(latest_shared.get("week_range") or ""),
            "_auto_approve_eligible": _auto_approve_eligible(rec),
            "_created_dt": created_dt,
            "_publish_dt": publish_dt,
            "_sort_dt": created_dt if pd.notna(created_dt) else publish_dt,
            "_companies_joined": " ".join(str(x) for x in safe_list(rec.get("companies_mentioned"))).lower(),
        }
    )

df = pd.DataFrame(rows)
today = pd.Timestamp.now().normalize()
created_dates = pd.to_datetime(df["_created_dt"], errors="coerce")
valid_created_dates = created_dates.dropna()
publish_dates = pd.to_datetime(df["_publish_dt"], errors="coerce")
valid_publish_dates = publish_dates.dropna()
default_record_from = (today - pd.Timedelta(days=7)).date()
default_record_to = max(
    today.date(),
    (valid_created_dates.max().date() if not valid_created_dates.empty else today.date()),
)
default_publish_from = (today - pd.Timedelta(days=7)).date()
default_publish_to = max(
    today.date(),
    (valid_publish_dates.max().date() if not valid_publish_dates.empty else today.date()),
)

status_vals = ["Pending", "Approved", "Disapproved"]
pri_vals = ["High", "Medium", "Low"]
conf_vals = ["High", "Medium", "Low"]
source_vals = sorted(df["source_type"].dropna().astype(str).unique().tolist())
all_regions = sorted({str(x) for v in df.get("regions_relevant_to_apex_mobility", []) for x in (v or []) if str(x).strip()})
all_themes = sorted({str(x) for v in df.get("macro_themes_detected", []) for x in (v or []) if str(x).strip()})
all_topics = sorted({str(x) for v in df.get("topics", []) for x in (v or []) if str(x).strip()})

if st.session_state.pop("review_clear_filters_requested", False):
    st.session_state["review_query"] = ""
    st.session_state["review_hide_briefed"] = True
    st.session_state["review_quick_region"] = "All Regions"
    st.session_state["review_quick_topic"] = "All Topics"
    st.session_state["review_adv_status"] = "All Statuses"
    st.session_state["review_adv_priority"] = "All Priorities"
    st.session_state["review_adv_conf"] = "All Confidence Levels"
    st.session_state["review_adv_source"] = "All Sources"
    st.session_state["review_adv_regions"] = []
    st.session_state["review_sel_themes"] = []
    st.session_state["review_sel_topics"] = []
    st.session_state["review_record_from"] = default_record_from
    st.session_state["review_record_to"] = default_record_to
    st.session_state["review_apply_publish_range"] = False
    st.session_state["review_publish_from"] = default_publish_from
    st.session_state["review_publish_to"] = default_publish_to
    st.session_state["review_date_basis"] = "Upload date"

st.session_state.setdefault("review_query", "")
st.session_state.setdefault("review_hide_briefed", True)
st.session_state.setdefault("review_quick_region", "All Regions")
st.session_state.setdefault("review_quick_topic", "All Topics")
st.session_state.setdefault("review_adv_status", "All Statuses")
st.session_state.setdefault("review_adv_priority", "All Priorities")
st.session_state.setdefault("review_adv_conf", "All Confidence Levels")
st.session_state.setdefault("review_adv_source", "All Sources")
st.session_state.setdefault("review_adv_regions", [])
st.session_state.setdefault("review_sel_themes", [])
st.session_state.setdefault("review_sel_topics", [])
st.session_state.setdefault("review_record_from", default_record_from)
st.session_state.setdefault("review_record_to", default_record_to)
st.session_state.setdefault("review_apply_publish_range", False)
st.session_state.setdefault("review_publish_from", default_publish_from)
st.session_state.setdefault("review_publish_to", default_publish_to)
st.session_state.setdefault("review_date_basis", "Upload date")

# One-time defaults migration so existing sessions pick up current filter defaults
# and don't keep stale query/date/region values from prior UI versions.
if not st.session_state.get("_review_filter_defaults_v6_applied", False):
    st.session_state["review_query"] = ""
    st.session_state["review_hide_briefed"] = True
    st.session_state["review_quick_region"] = "All Regions"
    st.session_state["review_quick_topic"] = "All Topics"
    st.session_state["review_adv_status"] = "All Statuses"
    st.session_state["review_adv_priority"] = "All Priorities"
    st.session_state["review_adv_conf"] = "All Confidence Levels"
    st.session_state["review_adv_source"] = "All Sources"
    st.session_state["review_adv_regions"] = []
    st.session_state["review_sel_themes"] = []
    st.session_state["review_sel_topics"] = []
    st.session_state["review_record_from"] = default_record_from
    st.session_state["review_record_to"] = default_record_to
    st.session_state["review_apply_publish_range"] = False
    st.session_state["review_publish_from"] = default_publish_from
    st.session_state["review_publish_to"] = default_publish_to
    st.session_state["review_date_basis"] = "Upload date"
    st.session_state["_review_filter_defaults_v6_applied"] = True

quick_region_options = ["All Regions"] + all_regions
quick_topic_options = ["All Topics"] + all_topics
f1, f2, f3, f4, f5 = st.columns([2.2, 1.3, 1.4, 1.0, 1.6])
with f1:
    query = st.text_input(
        "Search records",
        key="review_query",
        placeholder="Search records...",
        label_visibility="collapsed",
        help=(
            "Searches title, source, priority/confidence, status, record ID, "
            "topics, regions, themes, companies, and brief status."
        ),
    )
with f2:
    quick_region = st.selectbox(
        "Region",
        quick_region_options,
        key="review_quick_region",
        label_visibility="collapsed",
    )
with f3:
    quick_topic = st.selectbox(
        "Topic",
        quick_topic_options,
        key="review_quick_topic",
        label_visibility="collapsed",
    )
with f4:
    date_basis = st.selectbox(
        "Date basis",
        options=["Published date", "Upload date"],
        key="review_date_basis",
        label_visibility="collapsed",
    )
with f5:
    date_range = st.date_input(
        "Date range",
        value=(default_record_from, default_record_to),
        key="review_date_range",
        label_visibility="collapsed",
    )
    # Handle incomplete date range selection
    if isinstance(date_range, tuple):
        if len(date_range) == 2:
            filter_date_from, filter_date_to = date_range
        elif len(date_range) == 1:
            st.warning("⚠️ Please select both start and end dates for the range.")
            filter_date_from = filter_date_to = date_range[0]
        else:
            filter_date_from = filter_date_to = default_record_from
    else:
        filter_date_from = filter_date_to = date_range

hide_briefed = st.checkbox(
    "Hide records already included in a brief",
    key="review_hide_briefed",
)

with st.expander("Advanced", expanded=False):
    mf1, mf2 = st.columns(2)
    with mf1:
        adv_status = st.selectbox(
            "Status",
            options=["All Statuses"] + status_vals,
            key="review_adv_status",
        )
        adv_priority = st.selectbox(
            "Priority",
            options=["All Priorities"] + pri_vals,
            key="review_adv_priority",
        )
        adv_conf = st.selectbox(
            "Confidence",
            options=["All Confidence Levels"] + conf_vals,
            key="review_adv_conf",
        )
        adv_source = st.selectbox(
            "Source type",
            options=["All Sources"] + source_vals,
            key="review_adv_source",
        )
    with mf2:
        adv_regions = st.multiselect(
            "Regions (multi-select override)",
            all_regions,
            key="review_adv_regions",
        )
        sel_themes = st.multiselect(
            "Macro theme",
            all_themes,
            key="review_sel_themes",
        )
        sel_topics = st.multiselect(
            "Topic",
            all_topics,
            key="review_sel_topics",
        )
    
    if st.button("Clear", key="review_clear_filters", type="secondary", width="stretch"):
        st.session_state["review_clear_filters_requested"] = True
        st.rerun()

if adv_status == "All Statuses":
    sel_status = list(status_vals)
else:
    sel_status = [adv_status]

if adv_priority == "All Priorities":
    sel_pri = list(pri_vals)
else:
    sel_pri = [adv_priority]

if adv_conf == "All Confidence Levels":
    sel_conf = list(conf_vals)
else:
    sel_conf = [adv_conf]

if adv_source == "All Sources" or not source_vals:
    sel_source: List[str] = []
else:
    sel_source = [adv_source]

sel_regions: List[str] = []
if quick_region != "All Regions":
    sel_regions = [quick_region]
if adv_regions:
    sel_regions = list(adv_regions)

mask = pd.Series(True, index=df.index)
mask = mask & df["review_status"].isin(sel_status) & df["priority"].isin(sel_pri)
mask = mask & df["confidence"].isin(sel_conf)
if sel_source:
    mask = mask & df["source_type"].isin(sel_source)

# Apply date range filter based on selected basis
if date_basis == "Upload date":
    date_column = df["_created_dt"]
else:
    date_column = df["_publish_dt"]
mask = mask & (date_column.dt.date >= filter_date_from) & (date_column.dt.date <= filter_date_to)

if hide_briefed:
    mask = mask & (~df["in_brief"].fillna(False))
if query.strip():
    query_tokens = _normalize_filter_tokens(query)
    if query_tokens:
        mask = mask & df.apply(lambda row: _review_matches_tokens(row, query_tokens), axis=1)
if sel_regions:
    region_set = set(sel_regions)
    mask = mask & df["regions_relevant_to_apex_mobility"].apply(lambda vals: bool(region_set & set(vals or [])))
if sel_themes:
    theme_set = set(sel_themes)
    mask = mask & df["macro_themes_detected"].apply(lambda vals: bool(theme_set & set(vals or [])))
effective_topics = list(sel_topics or [])
if quick_topic != "All Topics":
    effective_topics = [quick_topic]
if effective_topics:
    topic_set = set(effective_topics)
    mask = mask & df["topics"].apply(lambda vals: bool(topic_set & set(vals or [])))

fdf = df[mask].copy().sort_values(by="_sort_dt", ascending=False, na_position="last")

pending_count = int((fdf["review_status"] == "Pending").sum()) if not fdf.empty else 0
low_conf_pending_count = int(((fdf["review_status"] == "Pending") & (fdf["confidence"] == "Low")).sum()) if not fdf.empty else 0

if fdf.empty:
    st.warning("No records match current selection.")
    st.stop()


def _truncate(text: Any, n: int = 96) -> str:
    s = str(text or "").strip()
    if len(s) <= n:
        return s
    return s[: max(0, n - 3)].rstrip() + "..."


def _priority_help_text(priority: str) -> str:
    p = str(priority or "").strip()
    if p == "High":
        return "Priority High: strong potential business impact based on deterministic postprocess rules."
    if p == "Medium":
        return "Priority Medium: meaningful signal, but less immediate impact than High."
    if p == "Low":
        return "Priority Low: informational signal with limited operational impact."
    return "Priority level assigned by deterministic postprocess rules."


def _confidence_help_text(confidence: str) -> str:
    c = str(confidence or "").strip()
    if c == "High":
        return "Confidence High: strong extraction signals (date/source/evidence) with low correction burden."
    if c == "Medium":
        return "Confidence Medium: moderate extraction support; usable but not strongest certainty."
    if c == "Low":
        return "Confidence Low: weak or incomplete extraction signals; review carefully."
    return "Confidence score computed from deterministic extraction-quality signals."


queue_col = st.container()
detail_col, pdf_col = st.columns([1.95, 1.35], gap="large")
with queue_col:
    with ui.card("Record Queue"):
        queue = fdf.copy()
        queue_ids = queue["record_id"].astype(str).tolist()
        selected_id: str = str(st.session_state.get("selected_record_id") or "")
        if selected_id not in queue_ids:
            selected_id = queue_ids[0]

        display_queue = queue

        st.markdown(
            f"**Pending: {pending_count} | "
            f"Low-confidence pending: {low_conf_pending_count} | "
            f"High priority: {int((fdf['priority'] == 'High').sum())} | "
            f"Marked duplicate: {int(fdf['is_duplicate'].fillna(False).sum())}**"
        )

        st.markdown("<div style='height:0.2rem'></div>", unsafe_allow_html=True)
        with st.container(border=False):
            hdr_info, hdr_pri, hdr_conf, hdr_status, hdr_action = st.columns([5.4, 1.0, 1.1, 1.1, 0.7])
            with hdr_info:
                st.caption("Record Info")
            with hdr_pri:
                st.caption("Priority")
            with hdr_conf:
                st.caption("Confidence")
            with hdr_status:
                st.caption("Status")
            with hdr_action:
                st.caption("Review Record")

            for _, row in display_queue.iterrows():
                rid = str(row["record_id"])
                status = str(row["review_status"])
                prio = str(row["priority"])
                conf = str(row["confidence"])
                pub = str(row.get("publish_date") or "")
                date_label = pub or "-"
                source = str(row.get("source_type") or "-")
                row_main, row_pri, row_conf, row_status, row_action = st.columns([5.4, 1.0, 1.1, 1.1, 0.7])
                with row_main:
                    title = _truncate(row.get("title"), 96) or "Untitled"
                    title_style = "font-weight:700;" if rid == selected_id else "font-weight:600;"
                    meta = f"{source} | {date_label} | Priority {prio} | Confidence {conf}"
                    brief_summary = str(row.get("brief_membership_summary") or "").strip()
                    brief_line = (
                        f"<div style='font-size:0.74rem;color:#475569;'>In briefs: {html.escape(brief_summary)}</div>"
                        if bool(row.get("in_brief")) and brief_summary
                        else ""
                    )
                    st.markdown(
                        (
                            "<div style='line-height:1.15;margin-bottom:0.15rem;'>"
                            f"<div style='{title_style}'>{html.escape(title)}</div>"
                            f"<div style='font-size:0.76rem;color:#64748b;'>{html.escape(meta)}</div>"
                            f"{brief_line}"
                            "</div>"
                        ),
                        unsafe_allow_html=True,
                    )
                with row_pri:
                    ui.status_badge(
                        prio,
                        kind=("danger" if prio == "High" else "warning" if prio == "Medium" else "info"),
                    )
                with row_conf:
                    ui.status_badge(
                        conf,
                        kind=("success" if conf == "High" else "danger" if conf == "Low" else "info"),
                    )
                with row_status:
                    badge_kind = "warning"
                    if status == "Approved":
                        badge_kind = "success"
                    elif status == "Disapproved":
                        badge_kind = "danger"
                    ui.status_badge(status, kind=badge_kind)
                    if bool(row.get("in_brief")):
                        st.caption(f"Briefed ({int(row.get('brief_count') or 1)})")
                with row_action:
                    if st.button(
                        "",
                        key=f"select_{rid}",
                        type="tertiary",
                        icon=":material/visibility:",
                        help="Review record",
                        width="content",
                    ):
                        st.session_state["selected_record_id"] = rid
                        st.rerun()

        selected_id = str(st.session_state.get("selected_record_id") or selected_id)
        if selected_id not in queue_ids:
            selected_id = queue_ids[0]
            st.session_state["selected_record_id"] = selected_id

        current_idx = queue_ids.index(selected_id)

records_by_id: Dict[str, Dict[str, Any]] = {str(r.get("record_id") or ""): r for r in records}
record_id = str(st.session_state.get("selected_record_id") or "")
rec = records_by_id.get(record_id)
source_pdf_path, pdf_path, pdf_path_source = _resolve_record_pdf_path(rec)
pdf_exists = bool(pdf_path and pdf_path.exists())

if rec:
    navd1, navd2, navd3 = st.columns([1, 1, 5])
    with navd1:
        if st.button("Previous", type="secondary", disabled=current_idx == 0, key="review_detail_prev"):
            st.session_state["selected_record_id"] = queue_ids[current_idx - 1]
            st.rerun()
    with navd2:
        if st.button("Next", type="secondary", disabled=current_idx >= (len(queue_ids) - 1), key="review_detail_next"):
            st.session_state["selected_record_id"] = queue_ids[current_idx + 1]
            st.rerun()
    with navd3:
        st.caption(f"Record {current_idx + 1} of {len(queue_ids)}")

with detail_col:
    with ui.card("Record Detail"):
        if not rec:
            st.info("Select a record from the queue.")
            st.stop()

        latest_shared = latest_brief_entry_for_record(brief_history, record_id)
        current_status = normalize_review_status(rec.get("review_status"))
        status_options = ["Pending", "Approved", "Disapproved"]
        status_key = f"status_{record_id}"
        exclude_key = f"exclude_{record_id}"
        reviewed_by_key = f"reviewed_by_{record_id}"
        notes_key = f"notes_{record_id}"
        json_key = f"json_editor_{record_id}"
        edit_mode_key = f"edit_mode_{record_id}"
        raw_json_tools_key = f"raw_json_tools_{record_id}"

        status_value = str(
            st.session_state.get(
                status_key,
                current_status if current_status in status_options else "Pending",
            )
        )
        if status_value not in status_options:
            status_value = current_status if current_status in status_options else "Pending"
        exclude_value = bool(st.session_state.get(exclude_key, bool(rec.get("is_duplicate", False))))
        reviewed_by = str(st.session_state.get(reviewed_by_key, str(rec.get("reviewed_by") or "")))
        notes = str(st.session_state.get(notes_key, str(rec.get("notes") or "")))
        raw_default = json.dumps(rec, ensure_ascii=False, indent=2)
        edit_mode = bool(st.session_state.get(edit_mode_key, False))
        raw_json_tools_enabled = bool(st.session_state.get(raw_json_tools_key, False))

        st.markdown(f"### {rec.get('title', 'Untitled')}")
        header_badge_cols = st.columns([1.2, 1.2, 1.2, 1.2])
        with header_badge_cols[0]:
            ui.status_badge(
                current_status,
                kind=("success" if current_status == "Approved" else "warning" if current_status == "Pending" else "danger"),
            )
        with header_badge_cols[1]:
            _prio = str(rec.get("priority") or "-")
            ui.status_badge(
                f"Priority: {_prio}",
                kind=("danger" if _prio == "High" else "warning" if _prio == "Medium" else "info"),
                help_text=_priority_help_text(_prio),
            )
        with header_badge_cols[2]:
            _conf = str(rec.get("confidence") or "-")
            ui.status_badge(
                f"Confidence: {_conf}",
                kind=("success" if _conf == "High" else "danger" if _conf == "Low" else "info"),
                help_text=_confidence_help_text(_conf),
            )
        with header_badge_cols[3]:
            if bool(brief_history.get(record_id)):
                ui.status_badge("Briefed", kind="info")

        shared_entries = [x for x in (brief_history.get(record_id) or []) if isinstance(x, dict)]
        st.markdown("**Included in saved briefs**")
        if shared_entries:
            shown = list(reversed(shared_entries))
            max_rows = 6
            for entry in shown[:max_rows]:
                file_name = _brief_entry_file_name(entry) or "(unknown brief)"
                week_range = str(entry.get("week_range") or "").strip()
                created_label = _created_date_pt_label(entry.get("created_at"))
                parts = [f"`{file_name}`"]
                if week_range:
                    parts.append(week_range)
                if created_label != "-":
                    parts.append(f"created {created_label}")
                st.markdown("- " + " | ".join(parts))
            if len(shown) > max_rows:
                st.caption(f"+ {len(shown) - max_rows} older brief entr{'y' if len(shown) - max_rows == 1 else 'ies'}")
        else:
            st.caption("Not included in any saved brief yet.")

        decision_status_key = f"decision_status_{record_id}"
        if decision_status_key not in st.session_state:
            st.session_state[decision_status_key] = current_status if current_status in status_options else "Pending"

        decision_left, _decision_spacer = st.columns([1.35, 2.65])
        with decision_left:
            selected_status = st.selectbox(
                "Status",
                options=status_options,
                key=decision_status_key,
            )
            if st.button("Update Status", type="primary", key=f"update_status_{record_id}", width="stretch"):
                changed = False
                updated = {
                    "review_status": selected_status,
                    "reviewed_by": (
                        reviewed_by or "analyst"
                        if selected_status in ("Approved", "Disapproved")
                        else (reviewed_by or str(rec.get("reviewed_by") or ""))
                    ),
                    "notes": (
                        notes or "Marked disapproved during review."
                        if selected_status == "Disapproved"
                        else (notes if selected_status == "Approved" else (notes or str(rec.get("notes") or "")))
                    ),
                    "is_duplicate": bool(exclude_value),
                }
                for key, value in updated.items():
                    if rec.get(key) != value:
                        rec[key] = value
                        changed = True
                if changed:
                    overwrite_records(records)
                    clear_records_cache()
                    st.success(f"Status updated to {selected_status}.")
                    st.rerun()
                else:
                    st.info("No changes to save.")

        context_col1, context_col2 = st.columns(2)
        with context_col1:
            st.markdown(
                f"**Source:** {str(rec.get('source_type') or '-')}  \n"
                f"**Publish date:** {str(rec.get('publish_date') or '-')}  \n"
                f"**Added date:** {_created_date_pt_label(rec.get('created_at'))}"
            )
        with context_col2:
            st.markdown(
                f"**Actor type:** {str(rec.get('actor_type') or '-')}  \n"
                f"**Regions relevant:** {join_list(rec.get('regions_relevant_to_apex_mobility')) or '-'}"
            )

        rec_obj = None
        ok = False
        errs: List[str] = []
        parse_requested = bool(edit_mode or raw_json_tools_enabled)
        if parse_requested:
            raw = st.session_state.get(json_key, raw_default)
            try:
                parsed_obj = json.loads(raw)
                if not isinstance(parsed_obj, dict):
                    raise ValueError("Top-level JSON must be an object.")
                rec_obj = dict(rec)
                rec_obj.update(parsed_obj)
                rec_obj["record_id"] = record_id
                rec_obj["review_status"] = status_value
                rec_obj["reviewed_by"] = reviewed_by
                rec_obj["notes"] = notes
                rec_obj["is_duplicate"] = bool(exclude_value)
                ok, errs = validate_record(rec_obj)
            except Exception as exc:
                rec_obj = None
                ok = False
                errs = [f"Invalid JSON: {exc}"]

        if "reingest_success_msg" in st.session_state:
            st.success(st.session_state.pop("reingest_success_msg"))
        if "reingest_info_msg" in st.session_state:
            st.info(st.session_state.pop("reingest_info_msg"))
        if "review_save_success_msg" in st.session_state:
            st.success(st.session_state.pop("review_save_success_msg"))

        tab_brief, tab_evidence, tab_fields, tab_advanced = st.tabs(["Brief", "Evidence", "Fields", "Advanced"])

        with tab_brief:
            render_source = rec_obj if rec_obj is not None else rec
            st.markdown(render_intelligence_brief(render_source))

        with tab_evidence:
            st.markdown("**Evidence bullets**")
            bullets = safe_list(rec.get("evidence_bullets"))
            if bullets:
                for item in bullets:
                    st.markdown(f"- {item}")
            else:
                st.caption("No evidence bullets.")
            st.divider()
            st.markdown("**Key insights**")
            insights = safe_list(rec.get("key_insights"))
            if insights:
                for item in insights:
                    st.markdown(f"- {item}")
            else:
                st.caption("No insights.")

        with tab_fields:
            fleft, fright = st.columns(2)
            with fleft:
                st.markdown(
                    f"**Actor type:** {str(rec.get('actor_type') or '-')}  \n"
                    f"**Source type:** {str(rec.get('source_type') or '-')}  \n"
                    f"**Publish date:** {str(rec.get('publish_date') or '-')}  \n"
                    f"**Priority / Confidence:** {str(rec.get('priority') or '-')} / {str(rec.get('confidence') or '-')}"
                )
                st.markdown(
                    f"**Companies:** {join_list(rec.get('companies_mentioned')) or '-'}  \n"
                    f"**Government entities:** {join_list(rec.get('government_entities')) or '-'}"
                )
            with fright:
                st.markdown(
                    f"**Footprint regions:** {join_list(rec.get('regions_relevant_to_apex_mobility')) or '-'}  \n"
                    f"**Display regions:** {join_list(rec.get('regions_mentioned')) or '-'}  \n"
                    f"**Countries:** {join_list(rec.get('country_mentions')) or '-'}  \n"
                    f"**Topics:** {join_list(rec.get('topics')) or '-'}"
                )
                link_label, link_value = best_record_link(rec)
                if link_value and link_value.startswith("http"):
                    st.markdown(f"[{link_label}]({link_value})")
                elif link_value:
                    st.caption(f"{link_label}: `{link_value}`")
                else:
                    st.caption("No source link available.")

        with tab_advanced:
            with st.expander("JSON Editor", expanded=False):
                st.toggle("Edit mode", value=edit_mode, key=edit_mode_key)
                st.toggle(
                    "Enable advanced tools",
                    value=raw_json_tools_enabled,
                    key=raw_json_tools_key,
                    help="Parses JSON live for preview/diagnostics without saving to records.jsonl.",
                )
                rc1, rc2 = st.columns(2)
                with rc1:
                    st.selectbox(
                        "Review Status",
                        options=status_options,
                        key=status_key,
                    )
                    st.checkbox(
                        "Mark as duplicate (exclude from briefs)",
                        value=exclude_value,
                        key=exclude_key,
                    )
                with rc2:
                    st.text_input("Reviewed By", value=reviewed_by, key=reviewed_by_key)
                    st.text_area("Notes", value=notes, height=100, key=notes_key)
                st.text_area(
                    "Record JSON",
                    value=raw_default,
                    height=300,
                    key=json_key,
                )
                if edit_mode and parse_requested and not ok:
                    st.warning("Validation errors")
                    for err in errs[:5]:
                        st.caption(f"- {err}")
                    hints = _json_editor_hints(errs)
                    if hints:
                        st.caption("How to fix")
                        for hint in hints:
                            st.caption(f"- {hint}")
                if edit_mode:
                    if st.button("Save edits", type="secondary", disabled=not ok or rec_obj is None, key=f"save_adv_{record_id}", width="stretch"):
                        changed = False
                        for idx, row in enumerate(records):
                            if str(row.get("record_id") or "") == record_id:
                                if row != rec_obj:
                                    records[idx] = rec_obj
                                    changed = True
                                break
                        if changed:
                            overwrite_records(records)
                            clear_records_cache()
                            st.session_state["review_save_success_msg"] = "Changes saved."
                            st.rerun()
                        else:
                            st.info("No changes.")

            with st.expander("Diagnostics", expanded=False):
                st.markdown(f"**Priority:** {_priority_reason_sentence(rec)}")
                st.markdown("**Confidence drivers**")
                conf_lines = _confidence_driver_lines(rec)
                if conf_lines:
                    for row in conf_lines:
                        st.markdown(f"- {row}")
                else:
                    st.caption("No detail available.")
                st.markdown("**Macro themes**")
                macro_rows = _macro_theme_diag(rec)
                if macro_rows:
                    st.dataframe(pd.DataFrame(macro_rows), width="stretch", hide_index=True)
                else:
                    st.caption("No themes detected.")

            with st.expander("Re-ingest", expanded=False):
                st.caption(f"PDF: `{str(pdf_path) if pdf_exists and pdf_path is not None else (source_pdf_path or 'None')}`")
                if source_pdf_path and not pdf_exists:
                    st.warning("PDF file missing")
                elif pdf_exists and pdf_path_source == "record_id_fallback":
                    st.caption("PDF resolved from `data/pdfs` by record ID.")
                st.caption("This overwrites extracted fields only and resets status to Pending.")

                reingest_provider = st.selectbox(
                    "Model",
                    options=["auto", "gemini", "claude", "chatgpt"],
                    index=0,
                    key=f"reingest_provider_{record_id}",
                )
                reingest_confirm = st.checkbox(
                    "Replace extracted fields and reset status to Pending",
                    value=False,
                    key=f"confirm_reingest_{record_id}",
                )
                if st.button(
                    "Re-ingest",
                    type="primary",
                    disabled=(not pdf_exists or not reingest_confirm),
                    key=f"reingest_{record_id}",
                    width="stretch",
                ):
                    try:
                        pdf_bytes = pdf_path.read_bytes() if pdf_path else b""
                    except Exception as exc:
                        st.error(f"Could not read PDF: {exc}")
                        st.stop()

                    set_navigation_lock(True, owner_page="review", reason="PDF re-ingest")
                    try:
                        with st.spinner("Re-ingesting..."):
                            new_rec, new_router_log, status_msg = _process_one_pdf_reingest(
                                pdf_bytes=pdf_bytes,
                                filename=(pdf_path.name if pdf_path else "source.pdf"),
                                provider_choice=reingest_provider,
                                override_title=str(rec.get("title") or ""),
                                override_url=str(rec.get("original_url") or ""),
                            )
                    finally:
                        set_navigation_lock(False, owner_page="review")

                    if new_rec is None:
                        st.error(status_msg)
                        if new_router_log:
                            with st.expander("Re-ingest failure details", expanded=False):
                                st.json(new_router_log)
                    else:
                        old_notes = str(rec.get("notes") or "").strip()
                        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                        reingest_note = f"Re-ingested {stamp}"
                        merged_notes = old_notes
                        if reingest_note not in old_notes:
                            merged_notes = f"{old_notes}\n{reingest_note}".strip() if old_notes else reingest_note

                        replaced = dict(rec)
                        replaced.update(new_rec)
                        replaced["record_id"] = record_id
                        replaced["created_at"] = rec.get("created_at") or replaced.get("created_at")
                        replaced["reviewed_by"] = str(rec.get("reviewed_by") or "")
                        replaced["notes"] = merged_notes
                        replaced["review_status"] = "Pending"
                        replaced["is_duplicate"] = bool(rec.get("is_duplicate", False))
                        replaced["source_pdf_path"] = source_pdf_path or replaced.get("source_pdf_path")
                        replaced["_router_log"] = new_router_log
                        if not replaced.get("original_url") and rec.get("original_url"):
                            replaced["original_url"] = rec.get("original_url")

                        ok_new, errs_new = validate_record(replaced)
                        if not ok_new:
                            st.error("Re-ingest validation failed.")
                            for err in errs_new[:3]:
                                st.caption(f"- {err}")
                        else:
                            changed = False
                            for idx, row in enumerate(records):
                                if str(row.get("record_id") or "") == record_id:
                                    if row != replaced:
                                        records[idx] = replaced
                                        changed = True
                                    break
                            if changed:
                                overwrite_records(records)
                                clear_records_cache()
                                st.success("Re-ingested and replaced. Status=Pending")
                                _reset_record_editor_state(record_id)
                                st.rerun()
                            else:
                                st.info("No field changes detected.")
                                _reset_record_editor_state(record_id)
                                st.rerun()

            with st.expander("Delete", expanded=False):
                del_col1, del_col2 = st.columns(2)
                with del_col1:
                    delete_record_confirm = st.checkbox(
                        "Delete record permanently",
                        value=False,
                        key=f"confirm_delete_record_{record_id}",
                    )
                    if st.button(
                        "Delete record permanently",
                        type="secondary",
                        key=f"delete_record_{record_id}",
                        disabled=(not delete_record_confirm),
                        width="stretch",
                    ):
                        delete_record_pdf_too = True
                        filtered_records = [r for r in records if str(r.get("record_id") or "") != record_id]
                        overwrite_records(filtered_records)
                        clear_records_cache()

                        if delete_record_pdf_too and pdf_path and pdf_path.exists():
                            try:
                                pdf_path.unlink()
                            except Exception as exc:
                                st.warning(f"Record deleted, PDF delete failed: {exc}")

                        remaining_ids = [rid for rid in queue_ids if rid != record_id]
                        if remaining_ids:
                            new_idx = min(current_idx, len(remaining_ids) - 1)
                            st.session_state["selected_record_id"] = remaining_ids[new_idx]
                        else:
                            st.session_state.pop("selected_record_id", None)
                        st.success("Record deleted.")
                        st.rerun()

                with del_col2:
                    delete_pdf_confirm = st.checkbox(
                        "Delete attached PDF only",
                        value=False,
                        key=f"confirm_delete_pdf_{record_id}",
                    )
                    if st.button(
                        "Delete attached PDF only",
                        type="secondary",
                        key=f"delete_pdf_only_{record_id}",
                        disabled=(not pdf_exists or not delete_pdf_confirm),
                        width="stretch",
                    ):
                        deleted_file = False
                        if pdf_path and pdf_path.exists():
                            try:
                                pdf_path.unlink()
                                deleted_file = True
                            except Exception as exc:
                                st.error(f"Delete failed: {exc}")
                        changed = False
                        if rec.get("source_pdf_path") is not None:
                            rec["source_pdf_path"] = None
                            changed = True
                        if changed:
                            overwrite_records(records)
                            clear_records_cache()
                            st.success("PDF deleted.")
                            st.rerun()
                        elif deleted_file:
                            st.success("PDF deleted.")
                            st.rerun()
                        else:
                            st.info("No PDF found.")

with pdf_col:
    with ui.card("Source PDF"):
        if not rec:
            st.info("Select a record from the queue.")
        else:
            source_url = str(rec.get("original_url") or "").strip()
            if source_url:
                st.link_button(
                    "Open source URL",
                    source_url,
                    type="tertiary",
                    width="stretch",
                )

            if pdf_exists and pdf_path is not None:
                _render_pdf_embed(pdf_path, height=980)
                try:
                    with pdf_path.open("rb") as handle:
                        st.download_button(
                            "Download",
                            data=handle.read(),
                            file_name=pdf_path.name,
                            mime="application/pdf",
                            key=f"download_original_pdf_panel_{record_id}",
                            help="Download PDF",
                        )
                except Exception:
                    st.caption("PDF exists but could not be read.")
            elif source_pdf_path:
                st.caption(f"Source PDF path: `{source_pdf_path}`")
                st.warning("Source PDF file is missing.")
            else:
                st.caption("No source PDF attached.")
