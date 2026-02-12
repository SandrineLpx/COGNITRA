from __future__ import annotations

from datetime import date, timedelta
import streamlit as st
import pandas as pd

from src.storage import load_records
from src.briefing import select_weekly_candidates, render_weekly_brief_md, render_exec_email

st.set_page_config(page_title="Weekly Brief", layout="wide")
st.title("Weekly Brief")

records = load_records()
if not records:
    st.info("No records yet.")
    st.stop()

c1, c2, c3 = st.columns(3)
with c1:
    days = st.number_input("Days back", min_value=3, max_value=30, value=7, step=1)
with c2:
    include_excluded = st.checkbox("Include duplicates", value=False)
with c3:
    show_share_ready_only = st.checkbox("Share-ready only", value=False)

candidates = select_weekly_candidates(records, days=days, include_excluded=include_excluded)
if show_share_ready_only:
    candidates = [r for r in candidates if r.get("priority") == "High" and r.get("confidence") == "High"]

if not candidates:
    st.warning("No candidates found for this range.")
    st.stop()

week_range = f"Last {int(days)} days"

st.subheader("Suggested selections")
df = pd.json_normalize(candidates)
show_cols = ["record_id", "title", "priority", "confidence", "source_type", "publish_date"]
show_cols = [c for c in show_cols if c in df.columns]
st.dataframe(df[show_cols], use_container_width=True, hide_index=True)

ids = [r.get("record_id") for r in candidates if r.get("record_id")]
labels = {r.get("record_id"): f"{r.get('title','Untitled')} ({r.get('priority','-')})" for r in candidates}

selected_ids = st.multiselect(
    "Select items for the brief",
    options=ids,
    default=ids,
    format_func=lambda rid: labels.get(rid, rid),
)
selected_records = [r for r in candidates if r.get("record_id") in set(selected_ids)]

st.subheader("Weekly Brief (Markdown)")
brief_md = render_weekly_brief_md(selected_records, week_range)
st.code(brief_md, language="markdown")

st.subheader("Executive Email Draft")
subject, body = render_exec_email(selected_records, week_range)
st.text_input("Email subject", value=subject)
st.text_area("Email body", value=body, height=260)
