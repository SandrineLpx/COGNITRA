import streamlit as st
import pandas as pd
import json
from pathlib import Path
from src.storage import load_records, overwrite_records, RECORDS_PATH
from src.dedupe import dedupe_records

st.set_page_config(page_title="Admin", layout="wide")
st.title("Admin")

records = load_records()
if not records:
    st.info("No records yet.")
else:
    # Toggle: canonical vs all records
    st.subheader("Deduplication")
    col1, col2 = st.columns(2)
    with col1:
        show_canonical = st.checkbox("Show canonical records only", value=True)
    with col2:
        if show_canonical:
            canonical, dups = dedupe_records(records)
            st.metric("Canonical", len(canonical))
            st.metric("Duplicates", len(dups))
        else:
            st.metric("Total records", len(records))
    
    export_records = canonical if show_canonical else records
    
    df = pd.json_normalize(export_records)
    
    st.subheader("Export CSV")
    st.caption("(Flat table for Excel/Power BI; nested fields are flattened.)")
    c1, c2 = st.columns(2)
    with c1:
        export_approved = st.checkbox("Approved only", value=True)
    with c2:
        st.caption(f"{'Canonical' if show_canonical else 'All'} records")
    
    edf = df[df["review_status"]=="Approved"] if export_approved and "review_status" in df else df
    csv = edf.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download CSV",
        data=csv,
        file_name=f"intelligence_records{'_canonical' if show_canonical else ''}.csv",
        mime="text/csv"
    )
    
    st.divider()
    st.subheader("Bulk Deduplication Export")
    st.caption("(JSONL for full-fidelity pipeline/audit outputs; preserves full JSON structure and metadata.)")
    st.caption("Export canonical and duplicate records to separate JSONL files.")
    
    if st.button("Run deduplication and export", type="primary"):
        canonical_recs, dup_recs = dedupe_records(records)
        
        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)
        
        canonical_path = data_dir / "canonical.jsonl"
        dups_path = data_dir / "duplicates.jsonl"
        
        with canonical_path.open("w", encoding="utf-8") as f:
            for rec in canonical_recs:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        
        with dups_path.open("w", encoding="utf-8") as f:
            for rec in dup_recs:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        
        st.success(f"Exported {len(canonical_recs)} canonical + {len(dup_recs)} duplicates")
        st.caption(f"• Canonical: {canonical_path}\n• Duplicates: {dups_path}")

st.divider()
st.subheader("Admin")
if st.button("Clear all records (demo reset)", type="secondary"):
    overwrite_records([])
    st.success("Cleared.")
    st.caption(f"Data file: {RECORDS_PATH}")
