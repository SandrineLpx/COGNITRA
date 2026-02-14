import streamlit as st
import pandas as pd
from datetime import datetime
from src.storage import load_records, overwrite_records
from src.schema_validate import ALLOWED_SOURCE_TYPES
from src.constants import _LEGACY_REVIEW_MAP

st.set_page_config(page_title="Inbox", layout="wide")
st.title("Inbox")

records = load_records()
if not records:
    st.info("No records yet. Go to Ingest to process a PDF.")
    st.stop()


def _norm_status(s):
    return _LEGACY_REVIEW_MAP.get(s, s)


df = pd.json_normalize(records)
# Normalize legacy review statuses for display/filtering.
if "review_status" in df.columns:
    df["review_status"] = df["review_status"].map(_norm_status)

# ── Filters ──────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
with col1:
    pri = st.multiselect("Priority", ["High", "Medium", "Low"], default=["High", "Medium", "Low"])
with col2:
    rs = st.multiselect("Review Status", ["Pending", "Approved", "Disapproved"], default=["Pending", "Approved", "Disapproved"])
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
        t = str(row.get("title", "")).lower()
        comps = " ".join(row.get("companies_mentioned", []) if isinstance(row.get("companies_mentioned"), list) else [])
        return (qq in t) or (qq in comps.lower())

    fdf = fdf[fdf.apply(hit, axis=1)]

# Default sort: latest first (created_at preferred, else publish_date)
if "created_at" in fdf.columns:
    fdf["_sort_dt"] = pd.to_datetime(fdf["created_at"], errors="coerce")
elif "publish_date" in fdf.columns:
    fdf["_sort_dt"] = pd.to_datetime(fdf["publish_date"], errors="coerce")
else:
    fdf["_sort_dt"] = pd.NaT

fdf = fdf.sort_values(by="_sort_dt", ascending=False, na_position="last").drop(columns=["_sort_dt"])

filtered_ids = fdf["record_id"].tolist()
filtered_records = [r for r in records if r.get("record_id") in set(filtered_ids)]

pending = [r for r in filtered_records if _norm_status(r.get("review_status", "")) == "Pending"]
approved = [r for r in filtered_records if _norm_status(r.get("review_status", "")) == "Approved"]
disapproved = [r for r in filtered_records if _norm_status(r.get("review_status", "")) == "Disapproved"]

st.caption(
    f"{len(filtered_records)} records shown / {len(records)} total  |  "
    f"{len(pending)} pending  |  {len(approved)} approved  |  {len(disapproved)} disapproved"
)

# ── Batch approve bar ────────────────────────────────────────────────────
if st.button(f"Approve all Pending ({len(pending)})", disabled=not pending, type="primary"):
    pending_ids = {r.get("record_id") for r in pending}
    for r in records:
        if r.get("record_id") in pending_ids:
            r["review_status"] = "Approved"
    overwrite_records(records)
    st.rerun()

st.divider()

# ── Record cards ─────────────────────────────────────────────────────────
for rec in filtered_records:
    rid = rec.get("record_id", "?")
    title = rec.get("title", "Untitled")
    status = _norm_status(rec.get("review_status", "Pending"))
    priority = rec.get("priority", "-")
    confidence = rec.get("confidence", "-")
    source = rec.get("source_type", "-")
    pub_date = rec.get("publish_date") or "-"

    status_icon = "[v]" if status == "Approved" else "[ ]"
    pri_tag = f"**{priority}**" if priority == "High" else priority

    with st.expander(f"{status_icon} {title}  —  {source} | {pub_date} | {pri_tag}/{confidence}", expanded=False):
        c_left, c_right = st.columns([3, 1])
        with c_left:
            insights = rec.get("key_insights") or []
            if insights:
                st.markdown("**Key Insights**")
                for ins in insights:
                    st.markdown(f"- {ins}")

            bullets = rec.get("evidence_bullets") or []
            if bullets:
                st.markdown("**Evidence**")
                for b in bullets:
                    st.markdown(f"- {b}")

            companies = rec.get("companies_mentioned") or []
            regions = rec.get("regions_relevant_to_kiekert") or []
            topics = rec.get("topics") or []
            meta_parts = []
            if companies:
                meta_parts.append(f"Companies: {', '.join(companies[:6])}")
            if regions:
                meta_parts.append(f"Regions: {', '.join(regions)}")
            if topics:
                meta_parts.append(f"Topics: {', '.join(topics)}")
            if meta_parts:
                st.caption(" | ".join(meta_parts))

        with c_right:
            st.markdown(f"**Status:** {status}")
            st.caption(f"ID: {rid}")
            reason_note = st.text_input("Review note (optional)", value="", key=f"note_{rid}")

            if status == "Pending":
                if st.button("Approve", key=f"app_{rid}", type="primary"):
                    for r in records:
                        if r.get("record_id") == rid:
                            r["review_status"] = "Approved"
                            if reason_note.strip():
                                prev = str(r.get("notes") or "").strip()
                                r["notes"] = (prev + " | " if prev else "") + f"Review note: {reason_note.strip()}"
                            break
                    overwrite_records(records)
                    st.rerun()

            if status != "Disapproved":
                if st.button("Disapprove", key=f"dis_{rid}"):
                    for r in records:
                        if r.get("record_id") == rid:
                            r["review_status"] = "Disapproved"
                            prev = str(r.get("notes") or "").strip()
                            note = reason_note.strip() or "Marked disapproved for analyst review."
                            r["notes"] = (prev + " | " if prev else "") + f"Disapproval note: {note}"
                            break
                    overwrite_records(records)
                    st.rerun()

            if st.button("Open full record", key=f"open_{rid}"):
                st.session_state["selected_record_id"] = rid
                st.switch_page("pages/03_Record.py")
