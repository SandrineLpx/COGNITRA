from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from src.context_pack import select_context_chunks
from src.model_router import choose_extraction_strategy, extract_single_pass, route_and_extract
from src.pdf_extract import extract_pdf_publish_date_hint, extract_text_robust
from src.postprocess import postprocess_record
from src.render_brief import render_intelligence_brief
from src.schema_validate import ALLOWED_SOURCE_TYPES, validate_record
from src.text_clean_chunk import clean_and_chunk
from src.storage import load_records, overwrite_records
from src.ui_helpers import (
    best_record_link,
    join_list,
    normalize_review_status,
    safe_list,
    workflow_ribbon,
)

st.set_page_config(page_title="Review & Approve", layout="wide")
st.title("Review & Approve")
workflow_ribbon(2)
st.caption("Review extracted records, edit JSON, and approve for weekly briefing.")


def _is_valid_iso_date(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except Exception:
        return False


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
        "regions_relevant_to_kiekert": _dedupe_keep_order(x for r in chunk_records for x in (r.get("regions_relevant_to_kiekert") or [])),
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

records = load_records()
if not records:
    st.info("No records yet. Go to Ingest to process a PDF.")
    st.stop()

rows = []
for rec in records:
    created_dt = pd.to_datetime(rec.get("created_at"), errors="coerce")
    publish_dt = pd.to_datetime(rec.get("publish_date"), errors="coerce")
    rows.append(
        {
            "record_id": str(rec.get("record_id") or ""),
            "title": str(rec.get("title") or "Untitled"),
            "source_type": str(rec.get("source_type") or "Other"),
            "publish_date": str(rec.get("publish_date") or ""),
            "priority": str(rec.get("priority") or "Medium"),
            "confidence": str(rec.get("confidence") or "Medium"),
            "review_status": normalize_review_status(rec.get("review_status")),
            "exclude_from_brief": bool(rec.get("exclude_from_brief", False)),
            "_sort_dt": created_dt if pd.notna(created_dt) else publish_dt,
            "_companies_joined": " ".join(str(x) for x in safe_list(rec.get("companies_mentioned"))).lower(),
        }
    )

df = pd.DataFrame(rows)

f1, f2, f3, f4 = st.columns(4)
with f1:
    pri_vals = ["High", "Medium", "Low"]
    sel_pri = st.multiselect("Priority", pri_vals, default=pri_vals)
with f2:
    status_vals = ["Pending", "Approved", "Disapproved"]
    sel_status = st.multiselect("Review Status", status_vals, default=status_vals)
with f3:
    source_vals = sorted(set(df.get("source_type", pd.Series(dtype=str)).dropna().tolist()) | set(ALLOWED_SOURCE_TYPES))
    sel_sources = st.multiselect("Source Type", source_vals, default=source_vals)
with f4:
    query = st.text_input("Search (title/company)")

mask = pd.Series(True, index=df.index)
mask = mask & df["priority"].isin(sel_pri) & df["review_status"].isin(sel_status)
if sel_sources:
    mask = mask & df["source_type"].isin(sel_sources)
if query.strip():
    qq = query.lower().strip()
    mask = mask & (
        df["title"].str.lower().str.contains(qq, na=False)
        | df["_companies_joined"].str.contains(qq, na=False)
    )

fdf = df[mask].copy()
fdf = fdf.sort_values(by="_sort_dt", ascending=False, na_position="last")

pending_count = int((fdf["review_status"] == "Pending").sum()) if not fdf.empty else 0
approved_count = int((fdf["review_status"] == "Approved").sum()) if not fdf.empty else 0
disapproved_count = int((fdf["review_status"] == "Disapproved").sum()) if not fdf.empty else 0
excluded_count = int(fdf["exclude_from_brief"].fillna(False).sum()) if not fdf.empty else 0
eligible_count = int(
    ((fdf["review_status"] == "Approved") & (~fdf["exclude_from_brief"].fillna(False))).sum()
) if not fdf.empty else 0

st.caption(
    f"Queue summary: {eligible_count} approved + included (brief-eligible)  |  "
    f"{pending_count} pending  |  {excluded_count} excluded"
)
st.caption(
    f"{len(fdf)} shown / {len(df)} total  |  "
    f"{approved_count} approved  |  {disapproved_count} disapproved"
)

b1, _ = st.columns([1, 4])
with b1:
    if st.button(f"Approve all pending ({pending_count})", disabled=pending_count == 0, type="primary"):
        pending_ids = set(fdf.loc[fdf["review_status"] == "Pending", "record_id"].tolist())
        changed = False
        for rec in records:
            if str(rec.get("record_id") or "") in pending_ids:
                if normalize_review_status(rec.get("review_status")) != "Approved":
                    rec["review_status"] = "Approved"
                    changed = True
        if changed:
            overwrite_records(records)
            st.rerun()

if fdf.empty:
    st.warning("No records match current filters.")
    st.stop()

st.subheader("Record Queue")
with st.expander("Record Queue", expanded=True):
    queue = fdf.copy()
    queue["priority_conf"] = queue["priority"] + "/" + queue["confidence"]
    queue_display = queue[["title", "source_type", "publish_date", "priority_conf", "review_status"]]
    queue_ids = queue["record_id"].astype(str).tolist()
    queue_title_map = {
        str(rid): str(ttl)
        for rid, ttl in zip(queue["record_id"].astype(str).tolist(), queue["title"].astype(str).tolist())
    }

    selected_id: str = str(st.session_state.get("selected_record_id") or "")
    if selected_id not in queue_ids:
        selected_id = queue_ids[0]

    used_table_selection = True
    try:
        event = st.dataframe(
            queue_display,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="review_queue_table",
        )
        rows_sel = list(event.selection.rows) if event and hasattr(event, "selection") else []
        if rows_sel:
            selected_idx = int(rows_sel[0])
            if 0 <= selected_idx < len(queue_ids):
                selected_id = queue_ids[selected_idx]
    except Exception:
        used_table_selection = False

    if not used_table_selection:
        selected_id = st.selectbox(
            "Select record",
            options=queue_ids,
            index=(queue_ids.index(selected_id) if selected_id in queue_ids else 0),
            format_func=lambda rid: queue_title_map.get(rid, rid),
            key="review_queue_selectbox",
        )

    if selected_id not in queue_ids:
        selected_id = queue_ids[0]

    st.session_state["selected_record_id"] = selected_id

    current_idx = queue_ids.index(selected_id)
    next_pending_id = None
    for rid in queue_ids[current_idx + 1 :]:
        status = str(queue.loc[queue["record_id"].astype(str) == rid, "review_status"].iloc[0])
        if status == "Pending":
            next_pending_id = rid
            break

    nav1, nav2 = st.columns(2)
    with nav1:
        if st.button("Previous", disabled=current_idx == 0, key="review_prev"):
            prev_id = queue_ids[current_idx - 1]
            if prev_id != selected_id:
                st.session_state["selected_record_id"] = prev_id
                st.rerun()
    with nav2:
        if st.button("Next Pending", disabled=next_pending_id is None, key="review_next_pending"):
            if next_pending_id and next_pending_id != selected_id:
                st.session_state["selected_record_id"] = next_pending_id
                st.rerun()

records_by_id: Dict[str, Dict[str, Any]] = {str(r.get("record_id") or ""): r for r in records}
record_id = str(st.session_state.get("selected_record_id") or "")
rec = records_by_id.get(record_id)

st.divider()
st.subheader("Record Detail")
with st.container():
    if not rec:
        st.info("Select a record from the queue.")
        st.stop()

    st.markdown(f"**{rec.get('title', 'Untitled')}**")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Source", str(rec.get("source_type") or "-"))
    m2.metric("Date", str(rec.get("publish_date") or "-"))
    m3.metric("Priority", str(rec.get("priority") or "-"))
    m4.metric("Status", normalize_review_status(rec.get("review_status")))

    link_label, link_value = best_record_link(rec)
    if link_value and link_value.startswith("http"):
        st.markdown(f"[{link_label}]({link_value})")
    elif link_value:
        st.caption(f"{link_label}: `{link_value}`")
    else:
        st.caption("No source link available.")

    with st.expander("Evidence", expanded=True):
        bullets = safe_list(rec.get("evidence_bullets"))
        if bullets:
            for item in bullets:
                st.markdown(f"- {item}")
        else:
            st.caption("No evidence bullets.")

    with st.expander("Insights", expanded=True):
        insights = safe_list(rec.get("key_insights"))
        if insights:
            for item in insights:
                st.markdown(f"- {item}")
        else:
            st.caption("No insights.")

    st.markdown(
        f"**Companies:** {join_list(rec.get('companies_mentioned')) or '-'}  \n"
        f"**Footprint:** {join_list(rec.get('regions_relevant_to_kiekert')) or '-'}  \n"
        f"**Topics:** {join_list(rec.get('topics')) or '-'}"
    )

    st.divider()
    rc1, rc2 = st.columns(2)
    with rc1:
        status_options = ["Pending", "Approved", "Disapproved"]
        current_status = normalize_review_status(rec.get("review_status"))
        status_value = st.selectbox(
            "Review Status",
            options=status_options,
            index=(status_options.index(current_status) if current_status in status_options else 0),
            key=f"status_{record_id}",
        )
        exclude_value = st.checkbox(
            "Exclude from brief",
            value=bool(rec.get("exclude_from_brief", False)),
            key=f"exclude_{record_id}",
        )
    with rc2:
        reviewed_by = st.text_input("Reviewed By", value=str(rec.get("reviewed_by") or ""), key=f"reviewed_by_{record_id}")
        notes = st.text_area("Notes", value=str(rec.get("notes") or ""), height=120, key=f"notes_{record_id}")

    raw = st.text_area(
        "Record JSON (editable)",
        value=json.dumps(rec, ensure_ascii=False, indent=2),
        height=320,
        key=f"json_editor_{record_id}",
    )
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
        rec_obj["exclude_from_brief"] = bool(exclude_value)
        ok, errs = validate_record(rec_obj)
    except Exception as exc:
        rec_obj = None
        ok = False
        errs = [f"Invalid JSON: {exc}"]

    if not ok:
        st.warning("Validation issues")
        for err in errs:
            st.caption(f"- {err}")

    with st.expander("Rendered Intelligence Brief", expanded=True):
        if rec_obj is not None:
            st.code(render_intelligence_brief(rec_obj), language="markdown")
        else:
            st.caption("Valid JSON required to render.")

    s1, s2, s3 = st.columns(3)
    with s1:
        if st.button("Save changes", type="primary", disabled=not ok or rec_obj is None, key=f"save_{record_id}"):
            changed = False
            for idx, row in enumerate(records):
                if str(row.get("record_id") or "") == record_id:
                    if row != rec_obj:
                        records[idx] = rec_obj
                        changed = True
                    break
            if changed:
                overwrite_records(records)
                st.success("Record saved.")
                st.rerun()
            else:
                st.info("No changes to save.")
    with s2:
        if st.button("Quick Approve", disabled=rec_obj is None, key=f"quick_approve_{record_id}"):
            changed = False
            updated = {
                "review_status": "Approved",
                "reviewed_by": reviewed_by or "analyst",
                "notes": notes,
                "exclude_from_brief": bool(exclude_value),
            }
            for key, value in updated.items():
                if rec.get(key) != value:
                    rec[key] = value
                    changed = True
            if changed:
                overwrite_records(records)
                st.success("Record approved.")
                st.rerun()
            else:
                st.info("Record already in this state.")
    with s3:
        if st.button("Quick Disapprove", disabled=rec_obj is None, key=f"quick_disapprove_{record_id}"):
            changed = False
            updated = {
                "review_status": "Disapproved",
                "reviewed_by": reviewed_by or "analyst",
                "notes": notes or "Marked disapproved during review.",
                "exclude_from_brief": bool(exclude_value),
            }
            for key, value in updated.items():
                if rec.get(key) != value:
                    rec[key] = value
                    changed = True
            if changed:
                overwrite_records(records)
                st.success("Record disapproved.")
                st.rerun()
            else:
                st.info("Record already in this state.")

    st.divider()
    with st.expander("Iteration / Quality Fix", expanded=False):
        st.caption("Use these controls to remove bad inputs or re-run extraction from the original PDF.")

        source_pdf_path = str(rec.get("source_pdf_path") or "").strip()
        pdf_path = Path(source_pdf_path) if source_pdf_path else None
        pdf_exists = bool(pdf_path and pdf_path.exists())
        st.caption(f"Stored PDF path: `{source_pdf_path or 'None'}`")
        if source_pdf_path and not pdf_exists:
            st.warning("Stored PDF path is set, but the file is missing.")

        delete_record_confirm = st.checkbox(
            "I understand this permanently deletes this record",
            value=False,
            key=f"confirm_delete_record_{record_id}",
        )
        delete_record_pdf_too = st.checkbox(
            "Also delete stored PDF file (if present)",
            value=True,
            key=f"delete_record_pdf_too_{record_id}",
        )
        if st.button(
            "Delete record",
            type="secondary",
            disabled=not delete_record_confirm,
            key=f"delete_record_{record_id}",
        ):
            filtered_records = [r for r in records if str(r.get("record_id") or "") != record_id]
            overwrite_records(filtered_records)

            if delete_record_pdf_too and pdf_path and pdf_path.exists():
                try:
                    pdf_path.unlink()
                except Exception as exc:
                    st.warning(f"Record deleted, but PDF delete failed: {exc}")

            remaining_ids = [rid for rid in queue_ids if rid != record_id]
            if remaining_ids:
                new_idx = min(current_idx, len(remaining_ids) - 1)
                st.session_state["selected_record_id"] = remaining_ids[new_idx]
            else:
                st.session_state.pop("selected_record_id", None)
            st.success("Record deleted.")
            st.rerun()

        st.divider()
        delete_pdf_confirm = st.checkbox(
            "I understand this permanently deletes the stored PDF file",
            value=False,
            key=f"confirm_delete_pdf_{record_id}",
        )
        if st.button(
            "Delete stored PDF (keep record)",
            type="secondary",
            disabled=(not source_pdf_path or not delete_pdf_confirm),
            key=f"delete_pdf_only_{record_id}",
        ):
            deleted_file = False
            if pdf_path and pdf_path.exists():
                try:
                    pdf_path.unlink()
                    deleted_file = True
                except Exception as exc:
                    st.error(f"Could not delete PDF file: {exc}")
            changed = False
            if rec.get("source_pdf_path") is not None:
                rec["source_pdf_path"] = None
                changed = True
            if changed:
                overwrite_records(records)
                st.success("PDF reference removed from record.")
                st.rerun()
            elif deleted_file:
                st.success("PDF deleted.")
                st.rerun()
            else:
                st.info("No stored PDF found for this record.")

        st.divider()
        reingest_provider = st.selectbox(
            "Re-ingest model provider",
            options=["auto", "gemini", "claude", "chatgpt"],
            index=0,
            key=f"reingest_provider_{record_id}",
        )
        reingest_confirm = st.checkbox(
            "I understand this replaces extracted fields and sets review status to Pending",
            value=False,
            key=f"confirm_reingest_{record_id}",
        )
        if st.button(
            "Re-ingest from stored PDF",
            type="primary",
            disabled=(not pdf_exists or not reingest_confirm),
            key=f"reingest_{record_id}",
        ):
            try:
                pdf_bytes = pdf_path.read_bytes() if pdf_path else b""
            except Exception as exc:
                st.error(f"Could not read PDF for re-ingest: {exc}")
                st.stop()

            with st.spinner("Re-ingesting from stored PDF..."):
                new_rec, new_router_log, status_msg = _process_one_pdf_reingest(
                    pdf_bytes=pdf_bytes,
                    filename=(pdf_path.name if pdf_path else "source.pdf"),
                    provider_choice=reingest_provider,
                    override_title=str(rec.get("title") or ""),
                    override_url=str(rec.get("original_url") or ""),
                )

            if new_rec is None:
                st.error(status_msg)
                if new_router_log:
                    st.json(new_router_log)
            else:
                old_notes = str(rec.get("notes") or "").strip()
                stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                reingest_note = f"Re-ingested on {stamp}."
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
                replaced["exclude_from_brief"] = bool(rec.get("exclude_from_brief", False))
                replaced["source_pdf_path"] = source_pdf_path or replaced.get("source_pdf_path")
                replaced["_router_log"] = new_router_log
                if not replaced.get("original_url") and rec.get("original_url"):
                    replaced["original_url"] = rec.get("original_url")

                ok_new, errs_new = validate_record(replaced)
                if not ok_new:
                    st.error("Re-ingest produced an invalid record.")
                    for err in errs_new:
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
                        st.success("Record re-ingested and replaced. Review status reset to Pending.")
                        st.rerun()
                    else:
                        st.info("Re-ingest completed but no field changes were detected.")
