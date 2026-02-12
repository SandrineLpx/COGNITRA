import streamlit as st
import json
from src.storage import load_records, overwrite_records
from src.render_brief import render_intelligence_brief
from src.schema_validate import validate_record

st.set_page_config(page_title="Record", layout="wide")
st.title("Record Detail")

records = load_records()
if not records:
    st.info("No records yet.")
    st.stop()

ids = [r.get("record_id") for r in records if r.get("record_id")]
default_id = st.session_state.get("selected_record_id", ids[0])

record_id = st.selectbox("Record ID", ids, index=ids.index(default_id) if default_id in ids else 0)
rec = next(r for r in records if r.get("record_id") == record_id)

col1, col2 = st.columns([1,1])
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
c1, c2, c3 = st.columns([1,1,2])
with c1:
    status = st.selectbox("Review Status", ["Not Reviewed","Reviewed","Approved"],
                          index=["Not Reviewed","Reviewed","Approved"].index(rec.get("review_status","Not Reviewed")))
with c2:
    reviewer = st.text_input("Reviewed By", value=rec.get("reviewed_by",""))
with c3:
    notes = st.text_input("Notes", value=rec.get("notes","") or "")

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
