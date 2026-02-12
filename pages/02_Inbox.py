import streamlit as st
import pandas as pd
from src.storage import load_records
from src.schema_validate import ALLOWED_SOURCE_TYPES

st.set_page_config(page_title="Inbox", layout="wide")
st.title("Inbox")

records = load_records()
if not records:
    st.info("No records yet. Go to Ingest to process a PDF.")
    st.stop()

df = pd.json_normalize(records)

col1, col2, col3, col4 = st.columns(4)
with col1:
    pri = st.multiselect("Priority", ["High","Medium","Low"], default=["High","Medium","Low"])
with col2:
    rs = st.multiselect("Review Status", ["Not Reviewed","Reviewed","Approved"], default=["Not Reviewed","Reviewed","Approved"])
with col3:
    src_vals = sorted(set(df.get("source_type", pd.Series()).dropna().unique().tolist()) | set(ALLOWED_SOURCE_TYPES))
    src = st.multiselect("Source Type", src_vals, default=src_vals)
with col4:
    q = st.text_input("Search (title/company)")

mask = df["priority"].isin(pri) & df["review_status"].isin(rs)
if src:
    mask = mask & df["source_type"].isin(src)
fdf = df[mask].copy()

if q.strip():
    qq = q.lower()
    def hit(row):
        t = str(row.get("title","")).lower()
        comps = " ".join(row.get("companies_mentioned", []) if isinstance(row.get("companies_mentioned"), list) else [])
        return (qq in t) or (qq in comps.lower())
    fdf = fdf[fdf.apply(hit, axis=1)]

st.caption(f"{len(fdf)} records shown / {len(df)} total")

show_cols = ["record_id","created_at","source_type","publish_date","priority","review_status","title"]
show_cols = [c for c in show_cols if c in fdf.columns]
st.dataframe(fdf[show_cols], use_container_width=True, hide_index=True)

st.divider()
st.subheader("Open a record")
ids = fdf["record_id"].tolist()
selected = st.selectbox("Record ID", ids)
if st.button("Open in Record page"):
    st.session_state["selected_record_id"] = selected
    st.switch_page("pages/03_Record.py")
