from __future__ import annotations

from datetime import date, timedelta
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import quote
import streamlit as st
import pandas as pd

from src.storage import load_records
from src.briefing import select_weekly_candidates, render_weekly_brief_md, render_exec_email, synthesize_weekly_brief_llm

st.set_page_config(page_title="Weekly Brief", layout="wide")
st.title("Weekly Brief")

BRIEFS_DIR = Path("data") / "briefs"
BRIEF_INDEX = BRIEFS_DIR / "index.jsonl"


def _save_brief(brief_text: str, week_range: str, selected_ids, usage):
    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"brief_{ts}.md"
    path = BRIEFS_DIR / filename
    path.write_text(brief_text, encoding="utf-8")

    meta = {
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "week_range": week_range,
        "file": str(path),
        "selected_record_ids": list(selected_ids),
        "usage": usage or {},
    }
    with BRIEF_INDEX.open("a", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
    return path

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

# ---------------------------------------------------------------------------
# LLM-synthesized executive brief
# ---------------------------------------------------------------------------
st.divider()
st.subheader("AI-Generated Executive Brief")
st.caption(
    "Uses Gemini to synthesize a structured executive brief from the selected records. "
    "Follows the Weekly Executive Report template."
)

if st.button("Generate AI Brief", type="primary", disabled=not selected_records):
    with st.spinner("Synthesizing executive brief..."):
        try:
            brief_text, usage = synthesize_weekly_brief_llm(selected_records, week_range)
        except Exception as e:
            st.error(f"Synthesis failed: {e}")
            st.stop()

    if usage:
        st.caption(
            f"Model: {usage.get('model', 'unknown')} | "
            f"prompt={usage.get('prompt_tokens', '?')} "
            f"output={usage.get('output_tokens', '?')} "
            f"total={usage.get('total_tokens', '?')}"
        )

    st.code(brief_text, language="markdown")
    st.text_area("Copy-friendly version", value=brief_text, height=400)

    st.session_state["last_ai_brief"] = brief_text
    st.session_state["last_ai_brief_usage"] = usage or {}
    st.session_state["last_ai_brief_week_range"] = week_range
    st.session_state["last_ai_brief_selected_ids"] = selected_ids

if st.session_state.get("last_ai_brief"):
    st.divider()
    st.subheader("Brief Actions")
    saved_week_range = st.session_state.get("last_ai_brief_week_range", week_range)
    saved_text = st.session_state["last_ai_brief"]
    saved_usage = st.session_state.get("last_ai_brief_usage", {})
    saved_ids = st.session_state.get("last_ai_brief_selected_ids", selected_ids)

    a1, a2, a3 = st.columns(3)
    with a1:
        if st.button("Save brief"):
            out_path = _save_brief(saved_text, saved_week_range, saved_ids, saved_usage)
            st.success(f"Saved: {out_path}")
    with a2:
        st.download_button(
            "Download .md",
            data=saved_text.encode("utf-8"),
            file_name=f"weekly_brief_{saved_week_range.replace(' ', '_')}.md",
            mime="text/markdown",
        )
    with a3:
        mailto = (
            "mailto:"
            + "?subject="
            + quote(f"Weekly Intelligence Brief ({saved_week_range})")
            + "&body="
            + quote(saved_text)
        )
        st.link_button("Open in Email Client", mailto)
