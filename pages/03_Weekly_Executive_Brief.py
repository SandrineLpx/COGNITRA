from __future__ import annotations

import json
from datetime import datetime, timezone
from difflib import unified_diff
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import pandas as pd
import streamlit as st

from src.briefing import (
    render_exec_email,
    render_weekly_brief_md,
    select_weekly_candidates,
    synthesize_weekly_brief_llm,
)
from src.storage import load_records
from src.ui_helpers import normalize_review_status, workflow_ribbon

st.set_page_config(page_title="Weekly Executive Brief", layout="wide")
st.title("Weekly Executive Brief")
workflow_ribbon(3)
st.caption("This page uses Approved + included records. Edit/approve records in Review & Approve.")

BRIEFS_DIR = Path("data") / "briefs"
BRIEF_INDEX = BRIEFS_DIR / "index.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _latest_brief_file() -> Optional[Path]:
    if not BRIEFS_DIR.exists():
        return None
    files = sorted([p for p in BRIEFS_DIR.glob("brief_*.md") if p.is_file()], key=lambda p: (p.stat().st_mtime, p.name))
    return files[-1] if files else None


def _previous_brief_file(current_path: Optional[Path]) -> Optional[Path]:
    if not current_path or not BRIEFS_DIR.exists():
        return None
    files = sorted([p for p in BRIEFS_DIR.glob("brief_*.md") if p.is_file()], key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
    for path in files:
        if path != current_path:
            return path
    return None


def _latest_brief_meta_for_file(brief_path: Optional[Path]) -> Dict[str, Any]:
    rows = _read_jsonl(BRIEF_INDEX)
    if not rows:
        return {}
    if brief_path is None:
        return rows[-1]
    matches = [r for r in rows if Path(str(r.get("file") or "")).name == brief_path.name]
    return matches[-1] if matches else rows[-1]


def _brief_sidecar_meta(brief_path: Optional[Path]) -> Dict[str, Any]:
    if not brief_path:
        return {}
    sidecar = brief_path.with_suffix(".meta.json")
    if not sidecar.exists():
        return {}
    try:
        obj = json.loads(sidecar.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _save_brief(brief_text: str, week_range: str, selected_ids: List[str], usage: Dict[str, Any]) -> Path:
    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = BRIEFS_DIR / f"brief_{ts}.md"
    path.write_text(brief_text, encoding="utf-8")

    meta = {
        "created_at": _now_iso(),
        "week_range": week_range,
        "file": str(path),
        "selected_record_ids": list(selected_ids),
        "usage": usage or {},
    }
    path.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    with BRIEF_INDEX.open("a", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
    return path


def _diff_text(previous: str, current: str) -> Tuple[str, int, int]:
    diff_lines = list(unified_diff(previous.splitlines(), current.splitlines(), fromfile="previous", tofile="current", lineterm=""))
    added = sum(1 for ln in diff_lines if ln.startswith("+") and not ln.startswith("+++"))
    removed = sum(1 for ln in diff_lines if ln.startswith("-") and not ln.startswith("---"))
    return ("\n".join(diff_lines), added, removed)


records = load_records()
if not records:
    st.info("No records yet.")
    st.stop()

meta_seed = _brief_sidecar_meta(_latest_brief_file()) or _latest_brief_meta_for_file(_latest_brief_file())
default_days = 30
if isinstance(meta_seed.get("week_range"), str):
    parts = str(meta_seed.get("week_range")).split()
    if len(parts) >= 2 and parts[0].lower() == "last" and parts[1].isdigit():
        default_days = max(3, min(90, int(parts[1])))

c1, c2 = st.columns(2)
with c1:
    days = st.number_input("Days back", min_value=3, max_value=90, value=default_days, step=1)
with c2:
    st.caption("Approved records are preselected by default.")

with st.expander("Candidate Filters (Advanced)", expanded=False):
    f1, f2, f3 = st.columns(3)
    with f1:
        only_approved = st.checkbox("Only Approved", value=True)
    with f2:
        include_excluded = st.checkbox("Include already excluded records", value=False)
    with f3:
        share_ready_only = st.checkbox("Share-ready only (High/High)", value=False)

week_range = f"Last {int(days)} days"
candidates = select_weekly_candidates(records, days=int(days), include_excluded=include_excluded)
if only_approved:
    candidates = [r for r in candidates if normalize_review_status(r.get("review_status")) == "Approved"]
if share_ready_only:
    candidates = [r for r in candidates if r.get("priority") == "High" and r.get("confidence") == "High"]

if not candidates:
    st.warning("No candidates found for this period.")
    st.stop()

approved_non_excluded = [
    r for r in candidates if normalize_review_status(r.get("review_status")) == "Approved" and not bool(r.get("exclude_from_brief", False))
]
default_ids = [str(r.get("record_id")) for r in approved_non_excluded if r.get("record_id")]

with st.expander("Candidate Records", expanded=False):
    df_candidates = pd.json_normalize(candidates)
    show_cols = ["record_id", "title", "source_type", "publish_date", "priority", "confidence", "review_status", "exclude_from_brief"]
    show_cols = [c for c in show_cols if c in df_candidates.columns]
    st.dataframe(df_candidates[show_cols], use_container_width=True, hide_index=True)

ids = [str(r.get("record_id")) for r in candidates if r.get("record_id")]
labels = {str(r.get("record_id")): f"{r.get('title', 'Untitled')} ({r.get('priority', '-')}/{r.get('confidence', '-')})" for r in candidates}
selected_ids = st.multiselect(
    "Select records for this brief",
    options=ids,
    default=default_ids,
    format_func=lambda rid: labels.get(rid, rid),
)
selected_set = set(selected_ids)
selected_records = [r for r in candidates if str(r.get("record_id")) in selected_set]

eligible_ids = set(default_ids)
missing_approved = eligible_ids - selected_set
if missing_approved:
    st.warning(f"{len(missing_approved)} approved, non-excluded records are not selected for this brief.")

st.divider()
st.markdown("## Executive-Ready Output")
st.subheader("AI-Generated Executive Brief")
provider = "gemini"
web_check_enabled = False
model_override = ""
with st.expander("Advanced AI Settings", expanded=False):
    ai1, ai2, ai3 = st.columns(3)
    with ai1:
        provider = st.selectbox("AI provider", ["gemini", "claude", "chatgpt"], index=0)
    with ai2:
        web_check_enabled = st.checkbox("Web coherence check (Gemini)", value=False)
    with ai3:
        model_override = st.text_input("Model override", value="")

k1, k2, k3 = st.columns(3)
k1.metric("Candidates", len(candidates))
k2.metric("Approved + Included", len(default_ids))
k3.metric("Selected", len(selected_records))

if st.button("Generate AI Brief", type="primary", disabled=not selected_records):
    with st.spinner("Synthesizing executive brief..."):
        try:
            brief_text, usage = synthesize_weekly_brief_llm(
                selected_records,
                week_range,
                provider=provider,
                web_check=bool(web_check_enabled and provider == "gemini"),
                model_override=(model_override.strip() or None),
            )
        except Exception as exc:
            st.error(f"Synthesis failed: {exc}")
            st.stop()

    st.session_state["weekly_ai_brief_text"] = brief_text
    st.session_state["weekly_ai_brief_usage"] = usage or {}
    st.session_state["weekly_ai_brief_week_range"] = week_range
    st.session_state["weekly_ai_brief_selected_ids"] = selected_ids

if st.session_state.get("weekly_ai_brief_text"):
    saved_text = st.session_state["weekly_ai_brief_text"]
    saved_usage = st.session_state.get("weekly_ai_brief_usage", {})
    saved_week_range = st.session_state.get("weekly_ai_brief_week_range", week_range)
    saved_ids = st.session_state.get("weekly_ai_brief_selected_ids", selected_ids)

    with st.expander("Rendered brief (readable)", expanded=True):
        st.markdown(saved_text)
    with st.expander("Copy / Export (raw text)", expanded=False):
        st.text_area("Copy-friendly version", value=saved_text, height=280)
    st.caption(
        f"Model: {saved_usage.get('model', 'unknown')} | "
        f"prompt={saved_usage.get('prompt_tokens', '?')} "
        f"output={saved_usage.get('output_tokens', '?')} "
        f"total={saved_usage.get('total_tokens', '?')}"
    )

    a1, a2, a3 = st.columns(3)
    with a1:
        if st.button("Save brief"):
            path = _save_brief(saved_text, saved_week_range, list(saved_ids), saved_usage)
            st.success(f"Saved: {path}")
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

with st.expander("Weekly Brief (Deterministic Preview)", expanded=False):
    brief_md = render_weekly_brief_md(selected_records, week_range)
    st.code(brief_md, language="markdown")

with st.expander("Executive Email Draft", expanded=False):
    subject, body = render_exec_email(selected_records, week_range)
    st.text_input("Email subject", value=subject)
    st.text_area("Email body", value=body, height=220)

st.divider()
latest_path = _latest_brief_file()
latest_meta = _brief_sidecar_meta(latest_path) or _latest_brief_meta_for_file(latest_path)
with st.expander("Saved Brief Review", expanded=False):
    if latest_path and latest_path.exists():
        latest_text = latest_path.read_text(encoding="utf-8")
        st.caption(f"Latest brief: `{latest_path.name}`")
        with st.expander("Latest brief metadata", expanded=False):
            st.json(latest_meta)
        with st.expander("Latest brief markdown", expanded=False):
            st.markdown(latest_text)

        prev_path = _previous_brief_file(latest_path)
        if prev_path:
            with st.expander("Compare with previous brief", expanded=False):
                prev_text = prev_path.read_text(encoding="utf-8")
                diff, added, removed = _diff_text(prev_text, latest_text)
                st.caption(f"Previous: `{prev_path.name}` | +{added} / -{removed}")
                st.code(diff or "No line-level changes.", language="diff")
    else:
        st.info("No saved brief found yet.")
