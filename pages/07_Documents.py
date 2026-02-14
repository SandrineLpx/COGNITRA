from __future__ import annotations

import ast
import pandas as pd
import streamlit as st

from src.storage import load_records
from src.constants import ALLOWED_SOURCE_TYPES, _LEGACY_REVIEW_MAP


# ── Helpers ────────────────────────────────────────────────────────────────

def _safe_list(val):
    """Ensure val is a list. Parses stringified lists; returns [] on failure."""
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        s = val.strip()
        if s.startswith("["):
            try:
                parsed = ast.literal_eval(s)
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []
        return [s] if s else []
    return []


def _norm_status(s):
    return _LEGACY_REVIEW_MAP.get(s, s)


def _best_link(rec: dict) -> tuple[str, str]:
    """Return (url, label) using fallback chain: original_url > source_pdf_path > none."""
    url = (rec.get("original_url") or "").strip()
    if url:
        return url, url
    pdf = (rec.get("source_pdf_path") or "").strip()
    if pdf:
        return "", f"Local: {pdf}"
    return "", "No link"


# ── Page setup ─────────────────────────────────────────────────────────────

st.set_page_config(page_title="Documents", layout="wide")
st.title("Original Documents")
st.caption("Library view of source files referenced by intelligence records.")

records = load_records()
if not records:
    st.info("No records yet. Go to Ingest to process a PDF.")
    st.stop()

df = pd.json_normalize(records)
if df.empty:
    st.info("No records available.")
    st.stop()

# Normalize legacy review statuses
if "review_status" in df.columns:
    df["review_status"] = df["review_status"].map(_norm_status)

# Parse dates
publish_dt = pd.to_datetime(df.get("publish_date"), errors="coerce", utc=True).dt.tz_convert(None)
created_dt = pd.to_datetime(df.get("created_at"), errors="coerce", utc=True).dt.tz_convert(None)
df["_event_day"] = publish_dt.combine_first(created_dt).dt.normalize()

# ── Filters ────────────────────────────────────────────────────────────────

today = pd.Timestamp.today().normalize()
default_from = (today - pd.Timedelta(days=30)).date()
default_to = today.date()

st.subheader("Filters")
f1, f2, f3 = st.columns(3)
with f1:
    date_from = st.date_input("From", value=default_from)
with f2:
    date_to = st.date_input("To", value=default_to)
with f3:
    q = st.text_input("Search (title/company)")

f4, f5, f6, f7 = st.columns(4)
with f4:
    all_topics = sorted(
        pd.Series(df.get("topics", pd.Series(dtype=object)))
        .apply(_safe_list).explode().dropna().astype(str).unique().tolist()
    )
    all_topics = [t for t in all_topics if t and t not in ("", "None", "nan")]
    sel_topics = st.multiselect("Topics", all_topics, default=[])
with f5:
    all_companies = sorted(
        pd.Series(df.get("companies_mentioned", pd.Series(dtype=object)))
        .apply(_safe_list).explode().dropna().astype(str).unique().tolist()
    )
    all_companies = [c for c in all_companies if c and c not in ("", "None", "nan")]
    sel_companies = st.multiselect("Companies", all_companies, default=[])
with f6:
    statuses = sorted(df["review_status"].dropna().astype(str).unique().tolist()) if "review_status" in df else []
    sel_status = st.multiselect("Review Status", statuses, default=statuses)
with f7:
    priorities = sorted(df["priority"].dropna().astype(str).unique().tolist()) if "priority" in df else []
    sel_priority = st.multiselect("Priority", priorities, default=priorities)

# Apply filters
mask = pd.Series(True, index=df.index)
mask = mask & (df["_event_day"] >= pd.Timestamp(date_from)) & (df["_event_day"] <= pd.Timestamp(date_to))

if sel_status and "review_status" in df:
    mask = mask & df["review_status"].astype(str).isin(sel_status)
if sel_priority and "priority" in df:
    mask = mask & df["priority"].astype(str).isin(sel_priority)
if sel_topics:
    topic_set = set(sel_topics)
    topic_hit = pd.Series(
        [bool(set(_safe_list(x)) & topic_set) for x in df.get("topics", [])],
        index=df.index,
    )
    mask = mask & topic_hit
if sel_companies:
    company_set = set(sel_companies)
    company_hit = pd.Series(
        [bool(set(_safe_list(x)) & company_set) for x in df.get("companies_mentioned", [])],
        index=df.index,
    )
    mask = mask & company_hit
if q.strip():
    qq = q.lower()
    text_hit = pd.Series(
        [
            qq in str(row.get("title", "")).lower()
            or qq in " ".join(_safe_list(row.get("companies_mentioned", []))).lower()
            for _, row in df.iterrows()
        ],
        index=df.index,
    )
    mask = mask & text_hit

fdf = df[mask].copy()

if fdf.empty:
    st.warning("No records match current filters.")
    st.stop()

# Sort newest first
fdf = fdf.sort_values("_event_day", ascending=False, na_position="last")

st.caption(f"{len(fdf)} documents shown / {len(df)} total")

# ── Document cards ─────────────────────────────────────────────────────────

st.subheader("Documents")

for _, row in fdf.iterrows():
    rec = row.to_dict()
    rid = rec.get("record_id", "?")
    title = rec.get("title") or "Untitled"
    source = rec.get("source_type", "-")
    pub_date = rec.get("publish_date") or "-"
    priority = rec.get("priority", "-")
    confidence = rec.get("confidence", "-")
    status = rec.get("review_status", "-")

    topics = ", ".join(_safe_list(rec.get("topics", [])))
    companies = ", ".join(_safe_list(rec.get("companies_mentioned", [])))
    regions = ", ".join(_safe_list(rec.get("regions_relevant_to_kiekert", [])))

    url, link_label = _best_link(rec)

    # Header line
    pri_tag = f"**{priority}**" if priority == "High" else priority
    header = f"{title}  —  {source} | {pub_date} | {pri_tag}"

    with st.expander(header, expanded=False):
        # Top row: link + metadata
        lc, mc = st.columns([2, 2])
        with lc:
            if url:
                st.markdown(f"[Open original source]({url})")
            else:
                st.caption(link_label)
            st.caption(f"Record ID: {rid}")

        with mc:
            st.markdown(
                f"**Status:** {status} &nbsp; | &nbsp; **Priority:** {priority} &nbsp; | &nbsp; **Confidence:** {confidence}"
            )
            if topics:
                st.caption(f"Topics: {topics}")
            if companies:
                st.caption(f"Companies: {companies}")
            if regions:
                st.caption(f"Regions: {regions}")

        # Evidence bullets
        bullets = _safe_list(rec.get("evidence_bullets", []))
        if bullets:
            st.markdown("**Evidence**")
            for b in bullets[:6]:
                st.markdown(f"- {b}")
            if len(bullets) > 6:
                st.caption(f"... and {len(bullets) - 6} more")

        # Notes
        notes = (rec.get("notes") or "").strip()
        if notes:
            st.markdown(f"**Notes:** {notes}")

        # Router usage summary
        router_log = rec.get("_router_log")
        if router_log and isinstance(router_log, dict):
            model = router_log.get("model") or router_log.get("provider", "?")
            prompt_tok = router_log.get("prompt_tokens", "?")
            output_tok = router_log.get("output_tokens", "?")
            st.caption(f"Extraction: model={model}, prompt_tokens={prompt_tok}, output_tokens={output_tok}")

        # Open full record button
        if st.button("Open full record", key=f"doc_open_{rid}"):
            st.session_state["selected_record_id"] = rid
            st.switch_page("pages/03_Record.py")
