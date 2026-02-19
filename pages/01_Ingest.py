import streamlit as st
import pandas as pd
import re
from collections import Counter
from datetime import datetime
from src import ui
from src.storage import new_record_id, overwrite_records, save_pdf_bytes, utc_now_iso
from src.pdf_extract import extract_text_robust, extract_pdf_publish_date_hint
from src.context_pack import select_context_chunks
from src.render_brief import render_intelligence_brief
from src.model_router import route_and_extract, extract_single_pass, choose_extraction_strategy
from src.postprocess import postprocess_record
from src.schema_validate import validate_record
from src.text_clean_chunk import clean_and_chunk
from src.dedupe import find_exact_title_duplicate, find_similar_title_records, score_source_quality
from src.ui_helpers import (
    clear_records_cache,
    enforce_navigation_lock,
    load_records_cached,
    render_navigation_lock_notice,
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


def _title_guess_from_filename(filename: str) -> str:
    name = str(filename or "").strip()
    if not name:
        return ""
    if "\\" in name:
        name = name.rsplit("\\", 1)[-1]
    if "/" in name:
        name = name.rsplit("/", 1)[-1]
    if name.lower().endswith(".pdf"):
        name = name[:-4]
    if "__" in name:
        # Stored PDFs are often "{record_id}__{original_name}".
        name = name.split("__", 1)[1]
    name = re.sub(r"[_\-]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


_SYSTEM_STATUS_STEPS = [
    ("extract_text", "Extracting Text"),
    ("clean", "Cleaning Data"),
    ("chunk", "Preparing Context"),
    ("extract", "Extracting Structured Data"),
    ("normalize", "Normalizing OEM Entities"),
    ("confidence", "Computing Confidence"),
    ("validate", "Validating Schema"),
    ("dedupe", "Checking Duplicates"),
    ("save", "Saving Record"),
]


def _default_system_status() -> dict:
    return {
        "state": "ready",
        "step": "",
        "message": "System ready. Awaiting input.",
        "error": "",
        "summary": {},
    }


def _clear_ingest_form_state() -> None:
    for key in [
        "ing_upload_files",
        "ing_single_title_override",
        "ing_single_original_url",
        "ing_show_chunks_upload",
        "ing_paste_title",
        "ing_paste_url",
        "ing_paste_text",
        "ing_show_chunks_paste",
        "ing_allow_duplicate_save",
        "ingest_active_mode",
    ]:
        st.session_state.pop(key, None)
    st.session_state.pop("ingest_last_debug", None)
    st.session_state.pop("ingest_last_brief_md", None)


def _set_system_status(
    state: str,
    step: str = "",
    message: str = "",
    error: str = "",
    summary: dict | None = None,
) -> None:
    status = _default_system_status()
    status.update(
        {
            "state": state,
            "step": step,
            "message": message or status["message"],
            "error": error,
            "summary": summary or {},
        }
    )
    st.session_state["ingest_system_status"] = status


def _render_system_status(slot=None) -> None:
    if "ingest_system_status" not in st.session_state:
        st.session_state["ingest_system_status"] = _default_system_status()

    status = st.session_state.get("ingest_system_status") or _default_system_status()
    holder = slot.container() if slot is not None else st.container()

    with holder:
        with ui.card("System Status"):
            state = str(status.get("state") or "ready")
            message = str(status.get("message") or "")
            step_key = str(status.get("step") or "")
            summary = status.get("summary") or {}

            if state == "ready":
                st.caption("System ready. Awaiting input.")
                return

            if state == "running":
                st.status("Ingest Pipeline", state="running", expanded=True)
                st.caption(message or "Pipeline is running.")
                active_idx = -1
                for idx, (key, _label) in enumerate(_SYSTEM_STATUS_STEPS):
                    if key == step_key:
                        active_idx = idx
                        break
                for idx, (_key, label) in enumerate(_SYSTEM_STATUS_STEPS):
                    row_num = idx + 1
                    if idx < active_idx:
                        st.caption(f"{row_num:02d}. Complete - {label}")
                    elif idx == active_idx:
                        st.caption(f"{row_num:02d}. In Progress - {label}")
                    else:
                        st.caption(f"{row_num:02d}. Pending - {label}")
                return

            if state == "error":
                st.status("Ingest Pipeline", state="error", expanded=False)
                st.error(status.get("error") or "Run failed.")
                st.caption("Check the input/source and retry. Open Advanced debug for technical details.")
                return

            st.status("Ingest Pipeline", state="complete", expanded=False)
            st.success("Processing Complete")
            if message:
                st.caption(message)
            if summary:
                c1, c2 = st.columns(2)
                c1.metric("Priority", str(summary.get("priority") or "-"))
                c2.metric("Confidence", str(summary.get("confidence") or "-"))
                st.caption("Regions: " + (", ".join(summary.get("regions") or []) or "-"))
                st.caption("Topics: " + (", ".join(summary.get("topics") or []) or "-"))

            b1, b2 = st.columns(2)
            if b1.button("View in Review", key="ing_status_view_review", width='stretch'):
                try:
                    st.switch_page("pages/02_Review.py")
                except Exception:
                    st.info("Open page 02 Review from the sidebar.")
            if b2.button("Ingest Another", key="ing_status_ingest_another", width='stretch'):
                _clear_ingest_form_state()
                _set_system_status("ready")
                st.rerun()


st.set_page_config(page_title="Cognitra", page_icon="assets/logo/cognitra-icon.png", layout="wide")
enforce_navigation_lock("ingest")
ui.init_page(active_step="Ingest")
ui.render_page_header(
    title="Ingest",
    subtitle="Extract structured intelligence from a PDF or pasted text.",
    active_step="Ingest",
)
render_navigation_lock_notice("ingest")

with st.sidebar:
    with st.expander("Model selector", expanded=False):
        provider = st.selectbox("Model", ["auto", "gemini", "claude", "chatgpt"], index=0, key="ing_model")
        st.caption("Strict routing: fallback only on schema failure.")

ui.render_sidebar_utilities(
    model_label=provider,
    overrides=st.session_state.get("rule_impact_run", {}),
)

uploaded_files = []
title = ""
original_url_input = ""
paste_title = ""
paste_url_input = ""
pasted = ""
show_selected_chunks = False
show_selected_chunks_paste = False
allow_duplicate_save = False
run_clicked = False
is_bulk = False
has_upload = False
has_paste = False
active_mode = st.session_state.get("ingest_active_mode", "upload_pdf")
status_slot = None

left_col, right_col = st.columns([1.8, 1.0], gap="large")

with left_col:
    with ui.card("Upload Source"):
        tab_pdf, tab_text = st.tabs(["Upload PDF", "Paste text"])

        with tab_pdf:
            uploaded_files = st.file_uploader(
                "Upload PDFs",
                type=["pdf"],
                accept_multiple_files=True,
                key="ing_upload_files",
            )
            has_upload = len(uploaded_files) > 0
            is_bulk = len(uploaded_files) > 1

            if has_upload and (not is_bulk):
                with st.expander("Optional metadata", expanded=False):
                    title = st.text_input("Title override (optional)", value="", key="ing_single_title_override")
                    original_url_input = st.text_input("Original URL (optional)", value="", key="ing_single_original_url")
                show_selected_chunks = st.checkbox("Show selected chunks", value=False, key="ing_show_chunks_upload")

        with tab_text:
            paste_title = st.text_input("Title", value="", key="ing_paste_title")
            paste_url_input = st.text_input("URL (optional)", value="", key="ing_paste_url")
            pasted = st.text_area("Text", height=220, key="ing_paste_text")
            show_selected_chunks_paste = st.checkbox("Show selected chunks", value=False, key="ing_show_chunks_paste")
            has_paste = bool(paste_title.strip()) and bool(pasted.strip())

        paste_has_any = bool(paste_title.strip() or paste_url_input.strip() or pasted.strip())
        if has_upload:
            active_mode = "upload_pdf"
        elif paste_has_any:
            active_mode = "paste_text"
        st.session_state["ingest_active_mode"] = active_mode

        cta_label = "Generate Intelligence Record"
        if active_mode == "upload_pdf" and is_bulk:
            cta_label = "Generate Intelligence Records"
        run_clicked = st.button(cta_label, type="primary", width='stretch', key="ing_primary_cta")

with right_col:
    status_slot = st.empty()
    _render_system_status(status_slot)


def _is_valid_iso_date(value):
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except Exception:
        return False


def _postprocess_with_checks(rec, source_text, publish_date_hint=None, publish_date_hint_source=None):
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
    run_impact = st.session_state.setdefault("rule_impact_run", {})
    for rule, count in rec.get("_rule_impact", {}).items():
        run_impact[rule] = int(run_impact.get(rule, 0)) + int(count or 0)
    return rec


def _dedupe_keep_order(values):
    out = []
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


def _pick_publish_date(recs):
    conf_rank = {"High": 3, "Medium": 2, "Low": 1}
    best = ("", "Low")
    best_key = (-1, datetime.min)
    for r in recs:
        pd = r.get("publish_date")
        if not pd:
            continue
        try:
            dt = datetime.strptime(pd, "%Y-%m-%d")
        except Exception:
            continue
        conf = str(r.get("publish_date_confidence") or "Low")
        key = (conf_rank.get(conf, 0), dt)
        if key > best_key:
            best_key = key
            best = (pd, conf)
    return best


def _merge_chunk_records(chunk_records):
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


def _usage_from_provider_log(prov_log):
    usage = prov_log.get("usage") if isinstance(prov_log, dict) else None
    if not isinstance(usage, dict):
        return None
    return usage


def _extract_usage_summary(router_log):
    if not isinstance(router_log, dict):
        return None

    if router_log.get("chunked_mode") and isinstance(router_log.get("chunk_logs"), list):
        prompt_total = 0
        output_total = 0
        total_total = 0
        model_counts = Counter()
        has_any = False
        for ch in router_log.get("chunk_logs", []):
            inner = ch.get("router_log", {})
            for prov in inner.get("providers_tried", []):
                u = _usage_from_provider_log(prov)
                if not u:
                    continue
                has_any = True
                model = u.get("model")
                if model:
                    model_counts[model] += 1
                prompt_total += int(u.get("prompt_tokens") or 0)
                output_total += int(u.get("output_tokens") or 0)
                total_total += int(u.get("total_tokens") or 0)
        if not has_any:
            return None
        return {
            "model": model_counts.most_common(1)[0][0] if model_counts else "unknown",
            "prompt_tokens": prompt_total,
            "output_tokens": output_total,
            "total_tokens": total_total,
            "chunked": True,
        }

    provs = router_log.get("providers_tried", [])
    for prov in reversed(provs):
        u = _usage_from_provider_log(prov)
        if u:
            return {
                "model": u.get("model"),
                "prompt_tokens": u.get("prompt_tokens"),
                "output_tokens": u.get("output_tokens"),
                "total_tokens": u.get("total_tokens"),
                "chunked": False,
            }
    return None


def _humanize_router_failure(router_log):
    """Turn router/provider logs into a concise, user-facing error."""
    if not isinstance(router_log, dict):
        return "Failed: model extraction failed. See details below."

    providers = router_log.get("providers_tried", [])
    if not providers:
        return "Failed: model extraction failed. No provider logs found."

    lines = []
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
        return "Failed: model extraction failed. Check provider logs below."

    prefix = "Failed: model extraction failed."
    if saw_gemini_503:
        prefix = "Failed: Gemini is temporarily overloaded (503)."
    return prefix + " " + " ".join(lines)


def _process_one_pdf(pdf_bytes, filename, records, provider_choice,
                     override_title="", override_url=""):
    """Extract, validate, and return (rec, router_log, status_msg) for one PDF.
    Returns (None, None, error_msg) on failure."""

    extracted_text, method = extract_text_robust(pdf_bytes)
    if not extracted_text.strip():
        return None, None, "Failed: no text extracted"
    publish_date_hint, publish_date_hint_source = extract_pdf_publish_date_hint(pdf_bytes, extracted_text)

    cleaned = clean_and_chunk(extracted_text)
    cleaned_text = cleaned["clean_text"]
    cleaned_chunks = cleaned["chunks"]
    cleaned_meta = cleaned.get("meta", {})
    strategy = choose_extraction_strategy(cleaned_meta)
    effective_chunked = bool(strategy.get("chunked_mode"))

    watch_terms = []
    topic_terms = [
        "tariff", "plant", "capacity", "joint venture", "platform", "EV", "battery",
        "latch", "door handle", "supplier", "production", "recall", "regulation",
    ]

    if effective_chunked and cleaned_chunks:
        initial_model = strategy["primary_model"]
        strong_model = strategy["fallback_model"]
        used_lite = initial_model != strong_model

        # Phase 1: all chunks with initial model
        chunk_records = {}   # idx -> rec
        chunk_logs = []
        failed_idxs = []
        for idx, chunk in enumerate(cleaned_chunks):
            rec_i, log_i = extract_single_pass(chunk, model=initial_model)
            log_i["chunk_id"] = f"{idx + 1}/{len(cleaned_chunks)}"
            log_i["phase"] = "initial"
            chunk_logs.append(log_i)
            if rec_i is not None:
                chunk_records[idx] = rec_i
            else:
                failed_idxs.append(idx)

        # Phase 2: retry ONLY failed chunks with strong model (if lite was used)
        if failed_idxs and used_lite:
            for idx in failed_idxs:
                rec_i, log_i = extract_single_pass(cleaned_chunks[idx], model=strong_model)
                log_i["chunk_id"] = f"{idx + 1}/{len(cleaned_chunks)}"
                log_i["phase"] = "repair"
                chunk_logs.append(log_i)
                if rec_i is not None:
                    chunk_records[idx] = rec_i

        if not chunk_records:
            return None, None, "Failed: all chunk extractions failed validation"

        rec = _merge_chunk_records(list(chunk_records.values()))
        router_log = {
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

    # Override title if provided
    if override_title:
        rec["title"] = override_title

    return rec, router_log, "OK"


def _finalize_record(rec, router_log, record_id, pdf_path, records):
    """Add metadata, auto-approve, handle dedupe. Returns (rec, status_label)."""
    rec["record_id"] = record_id
    rec["created_at"] = utc_now_iso()
    rec["source_pdf_path"] = pdf_path
    rec["_router_log"] = router_log
    rec.setdefault("is_duplicate", False)

    _auto = (
        rec.get("confidence") in ("High", "Medium")
        and bool(rec.get("publish_date"))
        and rec.get("source_type", "Other") != "Other"
        and len(rec.get("evidence_bullets") or []) >= 2
    )
    rec["review_status"] = "Approved" if _auto else "Pending"

    similar = find_similar_title_records(records, rec.get("title", ""), threshold=0.88)
    if similar:
        best = rec
        best_score = score_source_quality(rec)
        for existing, _ratio in similar:
            s = score_source_quality(existing)
            if s > best_score:
                best = existing
                best_score = s

        if best is rec:
            rec["story_primary"] = True
            for existing, _ratio in similar:
                existing["is_duplicate"] = True
                existing["duplicate_story_of"] = record_id
                existing["story_primary"] = False
            return rec, "Saved (similar story suppressed)"
        else:
            rec["is_duplicate"] = True
            rec["duplicate_story_of"] = best.get("record_id")
            rec["story_primary"] = False
            return rec, "Saved (duplicate story excluded from briefs)"

    return rec, "Saved"


# Single-file mode
if run_clicked:
    st.session_state.pop("ingest_last_brief_md", None)
    st.session_state.pop("ingest_last_debug", None)
    st.session_state.pop("ingest_bulk_results", None)

    if active_mode == "upload_pdf":
        if not has_upload:
            _set_system_status("error", error="Upload at least one PDF to continue.")
            _render_system_status(status_slot)
        elif is_bulk:
            _set_system_status("running", step="extract_text", message="Extracting Text for bulk upload.")
            _render_system_status(status_slot)

            set_navigation_lock(True, owner_page="ingest", reason="Bulk ingest pipeline")
            records = load_records_cached()
            results = []
            progress = st.progress(0, text="Starting bulk extraction...")

            try:
                for file_idx, uploaded in enumerate(uploaded_files):
                    file_num = file_idx + 1
                    progress.progress(
                        file_num / len(uploaded_files),
                        text=f"Processing {file_num}/{len(uploaded_files)}: {uploaded.name}",
                    )

                    pdf_bytes = uploaded.read()
                    proposed_title = uploaded.name.strip()
                    all_records_so_far = records
                    dupe = find_exact_title_duplicate(all_records_so_far, proposed_title)
                    if dupe:
                        results.append({
                            "File": uploaded.name,
                            "Title": proposed_title,
                            "Status": "Skipped (duplicate title)",
                            "Review": "-",
                        })
                        continue

                    try:
                        rec, router_log, status_msg = _process_one_pdf(
                            pdf_bytes, uploaded.name, all_records_so_far, provider,
                        )
                    except Exception as exc:
                        results.append({
                            "File": uploaded.name,
                            "Title": "-",
                            "Status": f"Error: {exc}",
                            "Review": "-",
                        })
                        continue

                    if rec is None:
                        results.append({
                            "File": uploaded.name,
                            "Title": "-",
                            "Status": status_msg,
                            "Review": "-",
                        })
                        continue

                    extracted_title = rec.get("title", "")
                    if extracted_title and extracted_title != proposed_title:
                        dupe2 = find_exact_title_duplicate(all_records_so_far, extracted_title)
                        if dupe2:
                            results.append({
                                "File": uploaded.name,
                                "Title": extracted_title,
                                "Status": "Skipped (duplicate - same article already exists)",
                                "Review": "-",
                            })
                            continue

                    record_id = new_record_id()
                    pdf_path = save_pdf_bytes(record_id, pdf_bytes, uploaded.name)
                    rec, save_status = _finalize_record(rec, router_log, record_id, pdf_path, all_records_so_far)

                    try:
                        records.append(rec)
                        overwrite_records(records)
                        clear_records_cache()
                    except Exception as exc:
                        if records and records[-1] is rec:
                            records.pop()
                        results.append({
                            "File": uploaded.name,
                            "Title": rec.get("title", "Untitled"),
                            "Status": f"Error saving checkpoint: {exc}",
                            "Review": "-",
                        })
                        continue

                    results.append({
                        "File": uploaded.name,
                        "Title": rec.get("title", "Untitled"),
                        "Status": save_status,
                        "Review": rec.get("review_status", "?"),
                    })
            finally:
                set_navigation_lock(False, owner_page="ingest")

            progress.progress(1.0, text="Done")
            saved_count = sum(1 for row in results if str(row.get("Status") or "").startswith("Saved"))
            skipped_count = sum(
                1 for row in results if "Skipped" in str(row.get("Status") or "")
                or "duplicate" in str(row.get("Status") or "").lower()
            )
            failed_count = sum(
                1 for row in results
                if str(row.get("Status") or "").startswith("Failed")
                or str(row.get("Status") or "").startswith("Error")
            )
            st.session_state["ingest_bulk_results"] = results
            st.session_state["ingest_last_debug"] = {"bulk_results": results}

            _set_system_status(
                "success",
                step="save",
                message=(
                    f"{saved_count} saved, {skipped_count} skipped, {failed_count} failed "
                    f"out of {len(uploaded_files)} files."
                ),
                summary={},
            )
            _render_system_status(status_slot)
        else:
            uploaded = uploaded_files[0]
            pdf_bytes = uploaded.read()
            error_msg = ""
            rec = None
            router_log = {}

            _set_system_status("running", step="extract_text", message="Extracting Text")
            _render_system_status(status_slot)
            extracted_text, method = extract_text_robust(pdf_bytes)
            if not extracted_text.strip():
                error_msg = "No text was extracted from this PDF."

            cleaned_text = ""
            cleaned_meta = {}
            cleaned_chunks = []
            selected_dbg = {}
            if not error_msg:
                _set_system_status("running", step="clean", message="Cleaning Data")
                _render_system_status(status_slot)
                _set_system_status("running", step="chunk", message="Preparing Context")
                _render_system_status(status_slot)
                cleaned = clean_and_chunk(extracted_text)
                cleaned_text = cleaned["clean_text"]
                cleaned_meta = cleaned.get("meta", {})
                cleaned_chunks = cleaned.get("chunks", [])

                if show_selected_chunks:
                    selected_dbg = select_context_chunks(
                        title.strip() or uploaded.name,
                        cleaned_text,
                        [],
                        [
                            "tariff", "plant", "capacity", "joint venture", "platform", "EV", "battery",
                            "latch", "door handle", "supplier", "production", "recall", "regulation",
                        ],
                        user_provided_url=original_url_input.strip(),
                    )

            records = load_records_cached()
            proposed_title = (title or uploaded.name).strip()
            if not error_msg:
                _set_system_status("running", step="dedupe", message="Checking Duplicates")
                _render_system_status(status_slot)

                precheck_titles = [proposed_title]
                guessed_from_file = _title_guess_from_filename(uploaded.name)
                if guessed_from_file and guessed_from_file.lower() != proposed_title.lower():
                    precheck_titles.append(guessed_from_file)

                for candidate_title in precheck_titles:
                    dupe = find_exact_title_duplicate(records, candidate_title)
                    if dupe and not allow_duplicate_save:
                        error_msg = (
                            f"Likely duplicate detected before extraction: REC:{dupe.get('record_id')}"
                        )
                        break

                    if len(candidate_title.split()) >= 5:
                        similar_pre = find_similar_title_records(records, candidate_title, threshold=0.88)
                        if similar_pre and not allow_duplicate_save:
                            best, ratio = similar_pre[0]
                            error_msg = (
                                f"Likely duplicate detected from title/filename: REC:{best.get('record_id')} "
                                f"(similarity={ratio:.2f})"
                            )
                            break

            if not error_msg:
                _set_system_status("running", step="extract", message="Extracting structured data")
                _render_system_status(status_slot)
                set_navigation_lock(True, owner_page="ingest", reason="Ingest pipeline")
                try:
                    rec, router_log, status_msg = _process_one_pdf(
                        pdf_bytes,
                        uploaded.name,
                        records,
                        provider,
                        override_title=title.strip(),
                        override_url=original_url_input.strip(),
                    )
                finally:
                    set_navigation_lock(False, owner_page="ingest")

                if rec is None:
                    error_msg = status_msg

            if not error_msg:
                _set_system_status("running", step="normalize", message="Normalizing OEM Entities")
                _render_system_status(status_slot)
                _set_system_status("running", step="confidence", message="Computing Confidence")
                _render_system_status(status_slot)
                _set_system_status("running", step="validate", message="Validating schema")
                _render_system_status(status_slot)
                extracted_title = str(rec.get("title") or "").strip()
                if extracted_title and extracted_title != proposed_title:
                    dupe2 = find_exact_title_duplicate(records, extracted_title)
                    if dupe2 and not allow_duplicate_save:
                        error_msg = (
                            f"Duplicate detected after extraction: REC:{dupe2.get('record_id')}"
                        )

            if not error_msg:
                _set_system_status("running", step="dedupe", message="Checking Duplicates")
                _render_system_status(status_slot)
                similar_title = str(rec.get("title") or proposed_title)
                similar = find_similar_title_records(records, similar_title, threshold=0.88)
                if similar and not allow_duplicate_save:
                    best, ratio = similar[0]
                    error_msg = (
                        f"Similar story already exists: REC:{best.get('record_id')} (similarity={ratio:.2f})"
                    )

            if not error_msg:
                _set_system_status("running", step="save", message="Saving record")
                _render_system_status(status_slot)
                record_id = new_record_id()
                pdf_path = save_pdf_bytes(record_id, pdf_bytes, uploaded.name)
                rec, save_status = _finalize_record(rec, router_log, record_id, pdf_path, records)
                overwrite_records(records + [rec])
                clear_records_cache()

                st.session_state["ingest_last_brief_md"] = render_intelligence_brief(rec)
                st.session_state["ingest_last_debug"] = {
                    "method": method,
                    "raw_preview": extracted_text[:2000],
                    "cleaned_text": cleaned_text,
                    "cleaned_meta": cleaned_meta,
                    "chunk_count": len(cleaned_chunks),
                    "selected_chunks": selected_dbg.get("selected_chunks") if selected_dbg else [],
                    "context_pack": selected_dbg.get("context_pack") if selected_dbg else "",
                    "record": rec,
                    "router_log": router_log,
                    "validation_errors": validate_record(rec)[1],
                }
                _set_system_status(
                    "success",
                    step="save",
                    message=save_status,
                    summary={
                        "priority": str(rec.get("priority") or "-"),
                        "confidence": str(rec.get("confidence") or "-"),
                        "regions": [str(x) for x in (rec.get("regions_relevant_to_apex_mobility") or [])],
                        "topics": [str(x) for x in (rec.get("topics") or [])],
                    },
                )
                _render_system_status(status_slot)
            else:
                st.session_state["ingest_last_debug"] = {
                    "method": method,
                    "raw_preview": extracted_text[:2000],
                    "cleaned_text": cleaned_text,
                    "cleaned_meta": cleaned_meta,
                    "chunk_count": len(cleaned_chunks),
                    "selected_chunks": selected_dbg.get("selected_chunks") if selected_dbg else [],
                    "context_pack": selected_dbg.get("context_pack") if selected_dbg else "",
                    "router_log": router_log,
                }
                _set_system_status("error", error=error_msg)
                _render_system_status(status_slot)

    elif active_mode == "paste_text":
        if not has_paste:
            _set_system_status("error", error="Title and text are required for Paste text mode.")
            _render_system_status(status_slot)
        else:
            title = paste_title
            original_url_input = paste_url_input
            _set_system_status("running", step="clean", message="Cleaning Data")
            _render_system_status(status_slot)
            cleaned = clean_and_chunk(pasted)
            cleaned_text = cleaned["clean_text"]
            cleaned_meta = cleaned["meta"]
            cleaned_chunks = cleaned["chunks"]
            _set_system_status("running", step="chunk", message="Preparing Context")
            _render_system_status(status_slot)
            selected = select_context_chunks(
                title.strip(),
                cleaned_text,
                [],
                [
                    "tariff", "plant", "capacity", "joint venture", "platform", "EV", "battery",
                    "latch", "door handle", "supplier", "production", "recall", "regulation",
                ],
                user_provided_url=original_url_input.strip(),
            )

            records = load_records_cached()
            rec = None
            router_log = {}
            error_msg = ""

            _set_system_status("running", step="dedupe", message="Checking Duplicates")
            _render_system_status(status_slot)
            dupe = find_exact_title_duplicate(records, title.strip())
            if dupe and not allow_duplicate_save:
                error_msg = f"Likely duplicate detected before extraction: REC:{dupe.get('record_id')}"

            if not error_msg:
                _set_system_status("running", step="extract", message="Extracting structured data")
                _render_system_status(status_slot)
                set_navigation_lock(True, owner_page="ingest", reason="Ingest pipeline")
                try:
                    rec, router_log, status_msg = _process_one_pdf(
                        b"",
                        "Manual Paste",
                        records,
                        provider,
                        override_title=title.strip(),
                        override_url=original_url_input.strip(),
                    )
                finally:
                    set_navigation_lock(False, owner_page="ingest")

                if rec is None:
                    set_navigation_lock(True, owner_page="ingest", reason="Ingest pipeline")
                    try:
                        rec, router_log = route_and_extract(selected["context_pack"], provider_choice=provider)
                    finally:
                        set_navigation_lock(False, owner_page="ingest")
                    if rec is None:
                        error_msg = _humanize_router_failure(router_log)

            if not error_msg:
                if original_url_input.strip() and not rec.get("original_url"):
                    rec["original_url"] = original_url_input.strip()
                _set_system_status("running", step="normalize", message="Normalizing OEM Entities")
                _render_system_status(status_slot)
                rec = _postprocess_with_checks(rec, source_text=selected["context_pack"])
                _set_system_status("running", step="confidence", message="Computing Confidence")
                _render_system_status(status_slot)
                rec["title"] = title.strip()

                _set_system_status("running", step="dedupe", message="Checking Duplicates")
                _render_system_status(status_slot)
                similar = find_similar_title_records(records, rec.get("title", ""), threshold=0.88)
                if similar and not allow_duplicate_save:
                    best, ratio = similar[0]
                    error_msg = (
                        f"Similar story already exists: REC:{best.get('record_id')} (similarity={ratio:.2f})"
                    )

            if not error_msg:
                _set_system_status("running", step="save", message="Saving record")
                _render_system_status(status_slot)
                record_id = new_record_id()
                rec, save_status = _finalize_record(rec, router_log, record_id, None, records)
                overwrite_records(records + [rec])
                clear_records_cache()

                st.session_state["ingest_last_brief_md"] = render_intelligence_brief(rec)
                st.session_state["ingest_last_debug"] = {
                    "raw_preview": pasted[:2000],
                    "cleaned_text": cleaned_text,
                    "cleaned_meta": cleaned_meta,
                    "chunk_count": len(cleaned_chunks),
                    "selected_chunks": selected.get("selected_chunks") if show_selected_chunks_paste else [],
                    "context_pack": selected.get("context_pack") if show_selected_chunks_paste else "",
                    "record": rec,
                    "router_log": router_log,
                    "validation_errors": validate_record(rec)[1],
                }
                _set_system_status(
                    "success",
                    step="save",
                    message=save_status,
                    summary={
                        "priority": str(rec.get("priority") or "-"),
                        "confidence": str(rec.get("confidence") or "-"),
                        "regions": [str(x) for x in (rec.get("regions_relevant_to_apex_mobility") or [])],
                        "topics": [str(x) for x in (rec.get("topics") or [])],
                    },
                )
                _render_system_status(status_slot)
            else:
                st.session_state["ingest_last_debug"] = {
                    "raw_preview": pasted[:2000],
                    "cleaned_text": cleaned_text,
                    "cleaned_meta": cleaned_meta,
                    "chunk_count": len(cleaned_chunks),
                    "selected_chunks": selected.get("selected_chunks") if show_selected_chunks_paste else [],
                    "context_pack": selected.get("context_pack") if show_selected_chunks_paste else "",
                    "router_log": router_log,
                }
                _set_system_status("error", error=error_msg)
                _render_system_status(status_slot)

bulk_results = st.session_state.get("ingest_bulk_results") or []
if bulk_results:
    with ui.card("Bulk Ingest Results"):
        saved_count = sum(1 for row in bulk_results if str(row.get("Status") or "").startswith("Saved"))
        skipped_count = sum(
            1 for row in bulk_results if "Skipped" in str(row.get("Status") or "")
            or "duplicate" in str(row.get("Status") or "").lower()
        )
        failed_count = sum(
            1 for row in bulk_results
            if str(row.get("Status") or "").startswith("Failed")
            or str(row.get("Status") or "").startswith("Error")
        )
        st.caption(f"{saved_count} saved | {skipped_count} skipped | {failed_count} failed | {len(bulk_results)} total")
        st.dataframe(pd.DataFrame(bulk_results), width='stretch', hide_index=True)

brief_md = st.session_state.get("ingest_last_brief_md")
if brief_md:
    with ui.card("Rendered Intelligence Brief"):
        st.code(brief_md, language="markdown")

debug_payload = st.session_state.get("ingest_last_debug")
if debug_payload:
    with st.expander("Advanced debug", expanded=False):
        if debug_payload.get("chunk_count") is not None:
            st.caption(
                f"Chunks: {debug_payload.get('chunk_count', 0)} | "
                f"Removed lines: {(debug_payload.get('cleaned_meta') or {}).get('removed_line_count', 0)}"
            )
        raw_preview = str(debug_payload.get("raw_preview") or "")
        if raw_preview:
            st.text_area("Raw preview", raw_preview, height=160)
        cleaned_text = str(debug_payload.get("cleaned_text") or "")
        if cleaned_text:
            st.text_area("Context pack preview", cleaned_text[:6000], height=220)

        selected_chunks = debug_payload.get("selected_chunks") or []
        if selected_chunks:
            st.caption("Selected chunks")
            st.json(selected_chunks)

        context_pack = str(debug_payload.get("context_pack") or "")
        if context_pack:
            st.text_area("Selected context pack", context_pack[:6000], height=220)

        validation_errors = debug_payload.get("validation_errors") or []
        if validation_errors:
            st.caption("Validation errors")
            for err in validation_errors:
                st.caption(f"- {err}")

        rec = debug_payload.get("record")
        if rec:
            st.caption("Raw JSON output")
            st.json(rec)

        router_log = debug_payload.get("router_log")
        if router_log:
            st.caption("Routing/validation logs")
            st.json(router_log)
