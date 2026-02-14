import streamlit as st
import json
from src.storage import load_records, overwrite_records
from src.render_brief import render_intelligence_brief
from src.schema_validate import validate_record
from src.constants import _LEGACY_REVIEW_MAP

st.set_page_config(page_title="Record", layout="wide")
st.title("Record Detail")

records = load_records()
if not records:
    st.info("No records yet.")
    st.stop()


def _norm_status(s):
    return _LEGACY_REVIEW_MAP.get(s, s)


# ── Record selector (title-first) ────────────────────────────────────────
ids = [r.get("record_id") for r in records if r.get("record_id")]
labels = {
    r.get("record_id"): f"{r.get('title', 'Untitled')}  [{_norm_status(r.get('review_status', '?'))}]"
    for r in records
}

default_id = st.session_state.get("selected_record_id", ids[0])
current_idx = ids.index(default_id) if default_id in ids else 0

record_id = st.selectbox(
    "Select record",
    ids,
    index=current_idx,
    format_func=lambda rid: labels.get(rid, rid),
)

# ── Next / Previous navigation ────────────────────────────────────────────
idx = ids.index(record_id)
nav1, nav2, nav3 = st.columns([1, 1, 4])
with nav1:
    if st.button("Previous", disabled=idx == 0):
        st.session_state["selected_record_id"] = ids[idx - 1]
        st.rerun()
with nav2:
    if st.button("Next", disabled=idx >= len(ids) - 1):
        st.session_state["selected_record_id"] = ids[idx + 1]
        st.rerun()
with nav3:
    st.caption(f"Record {idx + 1} of {len(ids)}")

rec = next(r for r in records if r.get("record_id") == record_id)
current_status = _norm_status(rec.get("review_status", "Pending"))

# ── Title and metadata header ─────────────────────────────────────────────
st.subheader(rec.get("title", "Untitled"))
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Priority", rec.get("priority", "-"))
m2.metric("Confidence", rec.get("confidence", "-"))
m3.metric("Source", rec.get("source_type", "-"))
m4.metric("Publish Date", rec.get("publish_date") or "-")
m5.metric("Status", current_status)

st.divider()

# ── Two-column view ───────────────────────────────────────────────────────
col1, col2 = st.columns([1, 1])
with col1:
    st.subheader("JSON (editable)")
    raw = st.text_area("Edit JSON", value=json.dumps(rec, ensure_ascii=False, indent=2), height=520)
with col2:
    st.subheader("Rendered Intelligence Brief")
    try:
        rec_obj = json.loads(raw)
        ok, errs = validate_record(rec_obj)
        if not ok:
            st.warning("Schema validation failed. Fix before saving.")
            st.write(errs)
        st.code(render_intelligence_brief(rec_obj), language="markdown")
    except Exception as e:
        st.error(f"Invalid JSON: {e}")
        rec_obj = None
        ok = False

st.divider()

# ── Review controls ───────────────────────────────────────────────────────
c1, c2, c3 = st.columns([1, 1, 2])
with c1:
    status_options = ["Pending", "Approved", "Disapproved"]
    status = st.selectbox(
        "Review Status",
        status_options,
        index=status_options.index(current_status) if current_status in status_options else 0,
    )
with c2:
    reviewer = st.text_input("Reviewed By", value=rec.get("reviewed_by", ""))
with c3:
    notes = st.text_input("Notes", value=rec.get("notes", "") or "")

save_col, approve_col, disapprove_col, _ = st.columns([1, 1, 1, 2])
with save_col:
    if st.button("Save changes", type="primary", disabled=(not ok or rec_obj is None)):
        rec_obj["review_status"] = status
        rec_obj["reviewed_by"] = reviewer
        rec_obj["notes"] = notes

        for i, r in enumerate(records):
            if r.get("record_id") == record_id:
                records[i] = rec_obj
                break
        overwrite_records(records)
        st.success("Saved.")
with approve_col:
    if current_status != "Approved":
        if st.button("Quick Approve", disabled=(not ok or rec_obj is None)):
            rec_obj["review_status"] = "Approved"
            rec_obj["reviewed_by"] = reviewer or "analyst"
            rec_obj["notes"] = notes

            for i, r in enumerate(records):
                if r.get("record_id") == record_id:
                    records[i] = rec_obj
                    break
            overwrite_records(records)
            st.success("Approved.")
            # Auto-advance to next pending record
            for next_id in ids[idx + 1 :]:
                next_rec = next((r for r in records if r.get("record_id") == next_id), None)
                if next_rec and _norm_status(next_rec.get("review_status", "")) != "Approved":
                    st.session_state["selected_record_id"] = next_id
                    st.rerun()
with disapprove_col:
    if current_status != "Disapproved":
        if st.button("Quick Disapprove", disabled=(not ok or rec_obj is None)):
            rec_obj["review_status"] = "Disapproved"
            rec_obj["reviewed_by"] = reviewer or "analyst"
            rec_obj["notes"] = notes or "Marked disapproved for model-improvement review."

            for i, r in enumerate(records):
                if r.get("record_id") == record_id:
                    records[i] = rec_obj
                    break
            overwrite_records(records)
            st.success("Disapproved.")
