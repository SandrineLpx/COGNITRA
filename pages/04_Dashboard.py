import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from src.storage import load_records
from src.dedupe import dedupe_records

st.set_page_config(page_title="Dashboard", layout="wide")
st.title("Dashboard")

with st.sidebar:
    st.subheader("Data Mode")
    show_canonical_only = st.checkbox("Show canonical stories only", value=False)
    st.caption("Canonical: deduplicated (one story per source group).")

records = load_records()
if not records:
    st.info("No records yet.")
    st.stop()

if show_canonical_only:
    canonical, dups = dedupe_records(records)
    records = canonical
    st.info(f"Showing {len(records)} canonical records (suppressed {len(dups)} duplicates).")

df = pd.json_normalize(records)
if df.empty:
    st.info("No records after filters.")
    st.stop()

df["publish_date_dt"] = pd.to_datetime(df.get("publish_date"), errors="coerce")
df["created_at_dt"] = pd.to_datetime(df.get("created_at"), errors="coerce")
df["event_date"] = df["publish_date_dt"].fillna(df["created_at_dt"]).dt.date
df["event_day"] = pd.to_datetime(df["event_date"], errors="coerce")

today = pd.Timestamp.today().normalize()
default_from = (today - pd.Timedelta(days=30)).date()
default_to = today.date()

st.subheader("Filters")
f1, f2, f3, f4 = st.columns(4)
with f1:
    date_from = st.date_input("From", value=default_from)
with f2:
    date_to = st.date_input("To", value=default_to)
with f3:
    statuses = sorted(df["review_status"].dropna().astype(str).unique().tolist()) if "review_status" in df else []
    sel_status = st.multiselect("Review Status", statuses, default=statuses)
with f4:
    sources = sorted(df["source_type"].dropna().astype(str).unique().tolist()) if "source_type" in df else []
    sel_sources = st.multiselect("Source Type", sources, default=sources)

t1, t2 = st.columns(2)
with t1:
    all_topics = sorted(
        pd.Series(df.get("topics", pd.Series(dtype=object))).explode().dropna().astype(str).unique().tolist()
    )
    sel_topics = st.multiselect("Topics", all_topics, default=all_topics)
with t2:
    only_brief_included = st.checkbox("Exclude suppressed/duplicate records", value=True)

mask = pd.Series(True, index=df.index)
mask = mask & (df["event_day"] >= pd.Timestamp(date_from)) & (df["event_day"] <= pd.Timestamp(date_to))
if sel_status and "review_status" in df:
    mask = mask & df["review_status"].astype(str).isin(sel_status)
if sel_sources and "source_type" in df:
    mask = mask & df["source_type"].astype(str).isin(sel_sources)
if only_brief_included:
    mask = mask & (~df.get("exclude_from_brief", False).fillna(False))
if sel_topics:
    topic_set = set(sel_topics)
    topic_hit = pd.Series(
        [bool(set(x or []) & topic_set) if isinstance(x, list) else False for x in df.get("topics", [])],
        index=df.index,
    )
    mask = mask & topic_hit

fdf = df[mask].copy()
if fdf.empty:
    st.warning("No records match current filters.")
    st.stop()

st.subheader("KPI")
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Records", len(fdf))
k2.metric("Approved", int((fdf.get("review_status") == "Approved").sum()) if "review_status" in fdf else 0)
k3.metric("Pending", int((fdf.get("review_status") == "Pending").sum()) if "review_status" in fdf else 0)
k4.metric("Disapproved", int((fdf.get("review_status") == "Disapproved").sum()) if "review_status" in fdf else 0)
k5.metric("Excluded", int(fdf.get("exclude_from_brief", pd.Series(False)).fillna(False).sum()))
k6.metric("High Priority", int((fdf.get("priority") == "High").sum()) if "priority" in fdf else 0)

st.subheader("30-Day Trend")
trend = (
    fdf.dropna(subset=["event_day"])
    .groupby(["event_day", "source_type"], dropna=False)
    .size()
    .reset_index(name="count")
)
if not trend.empty:
    pivot_trend = trend.pivot(index="event_day", columns="source_type", values="count").fillna(0)
    st.line_chart(pivot_trend)
else:
    st.caption("No dated records for trend chart.")

st.subheader("Region x Topic Heatmap")
if "regions_relevant_to_kiekert" in fdf and "topics" in fdf:
    hm = fdf[["regions_relevant_to_kiekert", "topics"]].copy()
    hm = hm.explode("regions_relevant_to_kiekert").explode("topics").dropna()
    if not hm.empty:
        ct = pd.crosstab(hm["regions_relevant_to_kiekert"], hm["topics"])
        fig, ax = plt.subplots(figsize=(8, 2.8))
        im = ax.imshow(ct.values, aspect="auto")
        ax.set_xticks(range(len(ct.columns)))
        ax.set_xticklabels(ct.columns, rotation=35, ha="right", fontsize=8)
        ax.set_yticks(range(len(ct.index)))
        ax.set_yticklabels(ct.index, fontsize=8)
        ax.set_title("Signals by Footprint Region and Topic")
        fig.colorbar(im, ax=ax)
        fig.tight_layout()
        st.pyplot(fig)
    else:
        st.caption("No region-topic pairs for heatmap.")

st.subheader("Drilldown")
show_cols = [
    "record_id",
    "title",
    "source_type",
    "priority",
    "confidence",
    "review_status",
    "publish_date",
    "exclude_from_brief",
]
show_cols = [c for c in show_cols if c in fdf.columns]
st.dataframe(fdf[show_cols].sort_values(by=["publish_date"], ascending=False), use_container_width=True, hide_index=True)

csv = fdf.to_csv(index=False).encode("utf-8")
st.download_button(
    "Download filtered CSV",
    data=csv,
    file_name="dashboard_filtered_records.csv",
    mime="text/csv",
)
