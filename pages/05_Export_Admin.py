import streamlit as st
import pandas as pd
from src.storage import load_records, overwrite_records, RECORDS_PATH

st.set_page_config(page_title="Export/Admin", layout="wide")
st.title("Export / Admin")

records = load_records()
if not records:
    st.info("No records yet.")
else:
    df = pd.json_normalize(records)
    st.subheader("Export CSV")
    export_approved = st.checkbox("Approved only", value=True)
    edf = df[df["review_status"]=="Approved"] if export_approved and "review_status" in df else df
    csv = edf.to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV", data=csv, file_name="intelligence_records.csv", mime="text/csv")

st.divider()
st.subheader("Admin")
if st.button("Clear all records (demo reset)", type="secondary"):
    overwrite_records([])
    st.success("Cleared.")
    st.caption(f"Data file: {RECORDS_PATH}")
