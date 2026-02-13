import streamlit as st
from collections import Counter
from datetime import datetime
from src.storage import load_records, new_record_id, overwrite_records, save_pdf_bytes, utc_now_iso
from src.pdf_extract import extract_text_robust
from src.context_pack import select_context_chunks
from src.render_brief import render_intelligence_brief
from src.model_router import route_and_extract
from src.postprocess import postprocess_record
from src.schema_validate import validate_record
from src.text_clean_chunk import clean_and_chunk
from src.dedupe import find_exact_title_duplicate, find_similar_title_records, score_source_quality

st.set_page_config(page_title="Ingest", layout="wide")
st.title("Ingest")

with st.sidebar:
    provider = st.selectbox("Model", ["auto","gemini","claude","chatgpt"], index=0)
    st.caption("Strict routing: fallback only on schema failure.")

uploaded = st.file_uploader("Upload a PDF", type=["pdf"])
title = st.text_input("Title (optional)", value="")
original_url_input = st.text_input("Original URL (optional)", value="")

manual_override = st.checkbox("Paste text manually (override extraction)", value=False)
pasted = st.text_area("Paste text here", height=200, disabled=not manual_override)
show_selected_chunks = st.checkbox("Show selected chunks", value=False)
chunked_mode = st.checkbox("Chunked extraction (better for long/noisy docs)", value=True)


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
        "regions_relevant_to_kiekert": _dedupe_keep_order(x for r in chunk_records for x in (r.get("regions_relevant_to_kiekert") or [])),
        "region_signal_type": next((str(r.get("region_signal_type")).strip() for r in chunk_records if str(r.get("region_signal_type") or "").strip()), "mixed"),
        "supply_flow_hint": next((str(r.get("supply_flow_hint")).strip() for r in chunk_records if str(r.get("supply_flow_hint") or "").strip()), ""),
        "priority": next((str(r.get("priority")).strip() for r in chunk_records if str(r.get("priority") or "").strip()), "Medium"),
        "confidence": next((str(r.get("confidence")).strip() for r in chunk_records if str(r.get("confidence") or "").strip()), "Medium"),
        "key_insights": _dedupe_keep_order(x for r in chunk_records for x in (r.get("key_insights") or []))[:4],
        "strategic_implications": _dedupe_keep_order(x for r in chunk_records for x in (r.get("strategic_implications") or []))[:4],
        "recommended_actions": _dedupe_keep_order(x for r in chunk_records for x in (r.get("recommended_actions") or []))[:6] or None,
        "review_status": "Not Reviewed",
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

if uploaded is not None:
    pdf_bytes = uploaded.read()

    extracted_text = ""
    method = ""
    if not manual_override:
        extracted_text, method = extract_text_robust(pdf_bytes)
        st.caption(f"Extraction method: {method} • chars: {len(extracted_text)}")

    preview_text = pasted if manual_override else extracted_text
    cleaned = clean_and_chunk(preview_text)
    cleaned_text = cleaned["clean_text"]
    cleaned_meta = cleaned["meta"]
    cleaned_chunks = cleaned["chunks"]

    raw_len = len(preview_text)
    cleaned_len = len(cleaned_text)
    removed_pct = (100.0 * (raw_len - cleaned_len) / raw_len) if raw_len > 0 else 0.0

    st.subheader("Text preview")
    col_raw, col_clean = st.columns(2)
    with col_raw:
        st.caption(f"Raw chars: {raw_len}")
        st.text_area("Raw preview", preview_text[:2000], height=220)
    with col_clean:
        st.caption(f"Cleaned chars: {cleaned_len} | Removed: {removed_pct:.1f}%")
        st.text_area("Cleaned preview", cleaned_text[:6000], height=220)
    st.caption(
        "Chunks: "
        f"{cleaned_meta.get('chunks_count', 0)} | Removed lines: {cleaned_meta.get('removed_line_count', 0)} | "
        f"Top removed patterns: {cleaned_meta.get('top_removed_patterns', [])[:3]}"
    )

    run = st.button("Run pipeline", type="primary")
    if run:
        if not preview_text.strip():
            st.error("No text available. Paste text manually and try again.")
            st.stop()

        records = load_records()
        proposed_title = (title or uploaded.name).strip()
        dupe = find_exact_title_duplicate(records, proposed_title)
        if dupe:
            st.error("Duplicate detected: an article with the same title already exists. Skipping ingestion.")
            st.caption(
                f"Existing record: {dupe.get('record_id')} • {dupe.get('created_at','') or 'Unknown date'}"
            )
            st.stop()

        record_id = new_record_id()
        pdf_path = save_pdf_bytes(record_id, pdf_bytes, uploaded.name)

        watch_terms = []      # optional: load from spec/company-watchlist_final.md later
        topic_terms = [
            "tariff", "plant", "capacity", "joint venture", "platform", "EV", "battery",
            "latch", "door handle", "supplier", "production", "recall", "regulation",
        ]

        if chunked_mode and cleaned_chunks:
            chunk_records = []
            chunk_logs = []
            for idx, chunk in enumerate(cleaned_chunks, 1):
                rec_i, log_i = route_and_extract(chunk, provider_choice=provider)
                chunk_logs.append({"chunk_id": f"{idx}/{len(cleaned_chunks)}", "router_log": log_i})
                if rec_i is not None:
                    chunk_records.append(rec_i)

            if not chunk_records:
                st.error("All chunk extractions failed strict validation.")
                st.json({"chunked_mode": True, "chunks_total": len(cleaned_chunks), "chunk_logs": chunk_logs})
                st.stop()

            rec = _merge_chunk_records(chunk_records)
            router_log = {
                "provider_choice": provider,
                "chunked_mode": True,
                "chunks_total": len(cleaned_chunks),
                "chunks_succeeded": len(chunk_records),
                "chunk_logs": chunk_logs,
            }
            if original_url_input.strip() and not rec.get("original_url"):
                rec["original_url"] = original_url_input.strip()
            rec = postprocess_record(rec, source_text=cleaned_text)
            ok, errs = validate_record(rec)
            if not ok:
                router_log["final_validation_errors"] = errs
                st.error("Merged chunk output failed validation after postprocess.")
                st.json(router_log)
                st.stop()
        else:
            selected = select_context_chunks(
                title or uploaded.name,
                cleaned_text,
                watch_terms,
                topic_terms,
                user_provided_url=original_url_input.strip(),
            )
            context_pack = selected["context_pack"]

            if show_selected_chunks:
                st.subheader("Selected Header Chunks")
                if selected["header_chunks"]:
                    for i, h in enumerate(selected["header_chunks"], 1):
                        st.markdown(f"**H{i}** score={h['score']} flags={', '.join(h['flags']) or '[none]'}")
                        st.code(h["chunk"])
                else:
                    st.caption("No header chunks selected.")

                st.subheader("Selected Body Chunks")
                if selected["body_chunks"]:
                    for i, b in enumerate(selected["body_chunks"], 1):
                        st.markdown(f"**B{i}** score={b['score']} flags={', '.join(b['flags']) or '[none]'}")
                        st.code(b["chunk"])
                else:
                    st.caption("No body chunks selected.")

            rec, router_log = route_and_extract(context_pack, provider_choice=provider)

            if rec is None:
                st.error("All models failed strict validation. Use manual paste and try again.")
                st.json(router_log)
                st.stop()

            if original_url_input.strip() and not rec.get("original_url"):
                rec["original_url"] = original_url_input.strip()

            try:
                rec = postprocess_record(rec, source_text=context_pack)
            except Exception as e:
                st.warning(f"Postprocess skipped due to error: {e}")

        rec["record_id"] = record_id
        rec["created_at"] = utc_now_iso()
        rec["source_pdf_path"] = pdf_path
        rec.setdefault("review_status", "Not Reviewed")
        rec["_router_log"] = router_log
        rec.setdefault("exclude_from_brief", False)

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
                    existing["exclude_from_brief"] = True
                    existing["duplicate_story_of"] = record_id
                    existing["story_primary"] = False
                st.warning("Similar story detected. This source looks stronger, so duplicates will be suppressed.")
                overwrite_records(records + [rec])
            else:
                rec["exclude_from_brief"] = True
                rec["duplicate_story_of"] = best.get("record_id")
                rec["story_primary"] = False
                st.warning(
                    "Similar story detected. A stronger source already exists, so this one will be excluded from briefs."
                )
                overwrite_records(records + [rec])
        else:
            overwrite_records(records + [rec])

        st.success("Record saved.")
        usage_summary = _extract_usage_summary(router_log)
        if usage_summary:
            st.caption(
                "Model used: "
                f"{usage_summary.get('model')} | "
                f"prompt={usage_summary.get('prompt_tokens')} "
                f"output={usage_summary.get('output_tokens')} "
                f"total={usage_summary.get('total_tokens')}"
            )
        st.subheader("JSON record")
        st.json(rec)

        st.subheader("Rendered Intelligence Brief")
        st.code(render_intelligence_brief(rec), language="markdown")
