import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from src.storage import load_records
from src.dedupe import dedupe_records

st.set_page_config(page_title="Dashboard", layout="wide")
st.title("Dashboard")

# Sidebar toggle for canonical vs all records
with st.sidebar:
    st.subheader("Data Mode")
    show_canonical_only = st.checkbox("Show canonical stories only", value=False)
    st.caption("Canonical: deduplicated (one story per source group). All: includes duplicates.")

# Load records
records = load_records()
if not records:
    st.info("No records yet.")
    st.stop()

# Apply deduplication filter if requested
if show_canonical_only:
    canonical, _ = dedupe_records(records)
    records = canonical
    st.info(f"Showing {len(records)} canonical records (deduplicated)")

df = pd.json_normalize(records)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total items", len(df))
c2.metric("High priority", int((df.get("priority")=="High").sum()) if "priority" in df else 0)
c3.metric("Approved", int((df.get("review_status")=="Approved").sum()) if "review_status" in df else 0)
c4.metric("Needs review", int((df.get("review_status")=="Not Reviewed").sum()) if "review_status" in df else 0)

st.divider()

if "priority" in df:
    st.subheader("Items by priority")
    counts = df["priority"].value_counts()
    fig = plt.figure()
    counts.plot(kind="bar")
    st.pyplot(fig)

if "topics" in df:
    st.subheader("Top topics")
    tdf = df[["topics"]].explode("topics").dropna()
    tc = tdf["topics"].value_counts().head(12)
    fig2 = plt.figure()
    tc.plot(kind="bar")
    st.pyplot(fig2)

if "regions_relevant_to_kiekert" in df:
    st.subheader("Footprint regions relevance")
    rdf = df[["regions_relevant_to_kiekert"]].explode("regions_relevant_to_kiekert").dropna()
    rc = rdf["regions_relevant_to_kiekert"].value_counts()
    fig3 = plt.figure()
    rc.plot(kind="bar")
    st.pyplot(fig3)

if "companies_mentioned" in df:
    st.subheader("Top companies mentioned")
    cdf = df[["companies_mentioned"]].explode("companies_mentioned").dropna()
    cc = cdf["companies_mentioned"].value_counts().head(15)
    fig4 = plt.figure()
    cc.plot(kind="bar")
    st.pyplot(fig4)
