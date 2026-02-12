import streamlit as st
from src.storage import load_records, new_record_id, overwrite_records, save_pdf_bytes, utc_now_iso
from src.pdf_extract import extract_text_robust
from src.context_pack import build_context_pack
from src.render_brief import render_intelligence_brief
from src.model_router import route_and_extract
from src.postprocess import postprocess_record
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

if uploaded is not None:
    pdf_bytes = uploaded.read()

    extracted_text = ""
    method = ""
    if not manual_override:
        extracted_text, method = extract_text_robust(pdf_bytes)
        st.caption(f"Extraction method: {method} • chars: {len(extracted_text)}")

    preview_text = pasted if manual_override else extracted_text
    st.subheader("Text preview")
    st.text_area("Preview", preview_text[:6000], height=220)

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
        country_terms = []    # optional: seed with common countries later

        context_pack = build_context_pack(title or uploaded.name, preview_text, watch_terms, country_terms)

        rec, router_log = route_and_extract(context_pack, provider_choice=provider)

        if rec is None:
            st.error("All models failed strict validation. Use manual paste and try again.")
            st.json(router_log)
            st.stop()

        if original_url_input.strip():
            rec["original_url"] = original_url_input.strip()

        try:
            rec = postprocess_record(rec)
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
        st.subheader("JSON record")
        st.json(rec)

        st.subheader("Rendered Intelligence Brief")
        st.code(render_intelligence_brief(rec), language="markdown")
