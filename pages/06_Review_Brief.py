from __future__ import annotations

import json
import re
from difflib import unified_diff
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from src.briefing import render_weekly_brief_md, select_weekly_candidates
from src.storage import load_records, overwrite_records


st.set_page_config(page_title="Review Brief", layout="wide")
st.title("Review Brief")
st.caption("Single workspace for latest brief review and source-record inspection.")

BRIEFS_DIR = Path("data") / "briefs"
BRIEF_INDEX = BRIEFS_DIR / "index.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _log_action(action: str, record_id: str) -> None:
    logs = st.session_state.setdefault("review_brief_action_log", [])
    logs.append({"ts": _now_iso(), "action": action, "record_id": record_id})
    st.session_state["review_brief_action_log"] = logs[-30:]


def _update_record_fields(record_id: str, updates: Dict[str, Any]) -> bool:
    rows = load_records()
    changed = False
    for i, row in enumerate(rows):
        if str(row.get("record_id") or "") != str(record_id):
            continue
        for k, v in updates.items():
            if row.get(k) != v:
                row[k] = v
                changed = True
        rows[i] = row
        break
    if changed:
        overwrite_records(rows)
    return changed


def _save_brief(brief_text: str, week_range: str, selected_ids: List[str], usage: Dict[str, Any]) -> Path:
    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"brief_{ts}.md"
    path = BRIEFS_DIR / filename
    path.write_text(brief_text, encoding="utf-8")

    sidecar = path.with_suffix(".meta.json")
    sidecar_meta = {
        "created_at": _now_iso(),
        "week_range": week_range,
        "file": str(path),
        "selected_record_ids": list(selected_ids),
        "usage": usage or {},
    }
    sidecar.write_text(json.dumps(sidecar_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    with BRIEF_INDEX.open("a", encoding="utf-8") as f:
        f.write(json.dumps(sidecar_meta, ensure_ascii=False) + "\n")
    return path


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _latest_brief_file() -> Optional[Path]:
    if not BRIEFS_DIR.exists():
        return None
    files = [p for p in BRIEFS_DIR.glob("brief_*.md") if p.is_file()]
    if not files:
        return None
    files.sort(key=lambda p: (p.stat().st_mtime, p.name))
    return files[-1]


def load_previous_brief(current_path: Optional[Path]) -> Optional[tuple[Path, str]]:
    if not current_path or not BRIEFS_DIR.exists():
        return None
    files = [p for p in BRIEFS_DIR.glob("brief_*.md") if p.is_file()]
    if len(files) < 2:
        return None
    files.sort(key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
    previous = next((p for p in files if p != current_path), None)
    if not previous:
        return None
    return previous, previous.read_text(encoding="utf-8")


def make_brief_diff(prev_text: str, curr_text: str) -> tuple[str, Dict[str, int], bool]:
    prev_lines = prev_text.splitlines()
    curr_lines = curr_text.splitlines()
    diff_lines = list(
        unified_diff(
            prev_lines,
            curr_lines,
            fromfile="previous_brief",
            tofile="current_brief",
            lineterm="",
        )
    )
    added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))

    num_pat = re.compile(r"[$€£]?\d[\d,]*(?:\.\d+)?%?")
    prev_nums = set(num_pat.findall(prev_text))
    curr_nums = set(num_pat.findall(curr_text))
    numeric_changed = prev_nums != curr_nums

    return "\n".join(diff_lines), {"added": added, "removed": removed}, numeric_changed


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


def _parse_days(week_range: str) -> int:
    m = re.search(r"Last\s+(\d+)\s+days", str(week_range or ""), flags=re.IGNORECASE)
    if not m:
        return 30
    try:
        return max(1, int(m.group(1)))
    except Exception:
        return 30


def _join_list(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(x) for x in value if str(x).strip())
    if value is None:
        return ""
    return str(value)


def _usage_from_router_log(router_log: Dict[str, Any]) -> Dict[str, Any]:
    top_usage = router_log.get("usage")
    if isinstance(top_usage, dict) and top_usage:
        return top_usage

    totals = {"prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    found_any = False
    for item in (router_log.get("chunk_logs") or []):
        if not isinstance(item, dict):
            continue
        usage = item.get("usage")
        if not isinstance(usage, dict):
            continue
        found_any = True
        for k in totals:
            v = usage.get(k)
            if isinstance(v, int):
                totals[k] += v
    return totals if found_any else {}


def _router_log_summary(router_log: Any) -> Dict[str, Any]:
    if not isinstance(router_log, dict):
        return {}
    usage = _usage_from_router_log(router_log)
    chunks_repaired = int(router_log.get("chunks_repaired") or 0)
    fallback_used = bool(router_log.get("fallback_used")) or chunks_repaired > 0
    return {
        "provider": router_log.get("provider_choice"),
        "model": router_log.get("model") or router_log.get("initial_model"),
        "chunked_mode": router_log.get("chunked_mode"),
        "fallback_used": fallback_used,
        "chunks_total": router_log.get("chunks_total"),
        "chunks_succeeded_initial": router_log.get("chunks_succeeded_initial"),
        "chunks_repaired": chunks_repaired,
        "chunks_failed_final": router_log.get("chunks_failed_final"),
        "usage": usage or None,
    }


brief_path = _latest_brief_file()
brief_meta = _brief_sidecar_meta(brief_path)
if not brief_meta:
    brief_meta = _latest_brief_meta_for_file(brief_path)
brief_text = ""
if brief_path and brief_path.exists():
    brief_text = brief_path.read_text(encoding="utf-8")

records = load_records()
if not records:
    st.info("No records yet.")
    st.stop()

days = _parse_days(str(brief_meta.get("week_range") or ""))
candidates = select_weekly_candidates(records, days=days, include_excluded=False)
selected_ids = set(brief_meta.get("selected_record_ids") or [])
approved_non_excluded_records = [
    r for r in candidates
    if str(r.get("review_status") or "") == "Approved" and not bool(r.get("exclude_from_brief"))
]
eligible_ids = {str(r.get("record_id") or "") for r in approved_non_excluded_records if r.get("record_id")}
missing_ids = eligible_ids - selected_ids

if not candidates:
    st.warning(f"No candidate records found for the latest brief period (Last {days} days).")
    st.stop()

records_by_id = {str(r.get("record_id") or ""): r for r in candidates}
if selected_ids:
    for r in records:
        rid = str(r.get("record_id") or "")
        if rid and rid in selected_ids and rid not in records_by_id:
            records_by_id[rid] = r

table_rows = []
for rec in records_by_id.values():
    used_in_brief = str(rec.get("record_id") or "") in selected_ids
    row = {
        "title": rec.get("title"),
        "source_type": rec.get("source_type"),
        "publish_date": rec.get("publish_date"),
        "priority": rec.get("priority"),
        "review_status": rec.get("review_status"),
        "topics": _join_list(rec.get("topics")),
        "regions_relevant_to_kiekert": _join_list(rec.get("regions_relevant_to_kiekert")),
        "record_id": rec.get("record_id"),
        "used_in_brief": used_in_brief,
    }
    table_rows.append(row)

df_all = pd.DataFrame(table_rows)
if "publish_date" not in df_all.columns:
    df_all["publish_date"] = ""
df_all["publish_date_dt"] = pd.to_datetime(df_all["publish_date"], errors="coerce", utc=False)
df_all["publish_date_display"] = df_all["publish_date_dt"].dt.strftime("%Y-%m-%d").fillna("")
df_all = df_all.sort_values(by="publish_date_dt", ascending=False, na_position="last")
df_all = df_all.reset_index(drop=True)

left, right = st.columns([1.6, 1], gap="large")

with left:
    st.subheader("Latest Generated Brief")
    previous_brief = load_previous_brief(brief_path)
    if brief_text:
        st.markdown(brief_text)
        st.caption(f"File: `{brief_path}`")
        if previous_brief:
            compare_prev = st.checkbox("Compare to previous brief", value=False)
        else:
            compare_prev = st.checkbox("Compare to previous brief", value=False, disabled=True)
            st.caption("No previous brief available yet.")

        if compare_prev and previous_brief:
            prev_path, prev_text = previous_brief
            diff_text, counts, numeric_changed = make_brief_diff(prev_text, brief_text)
            st.subheader("Changes")
            st.caption(f"Compared with: `{prev_path}`")
            st.caption(f"+{counts['added']} added, -{counts['removed']} removed")
            if numeric_changed:
                st.warning("Numeric content changed — review numbers.")
            st.code(diff_text or "No line-level changes detected.", language="diff")
    else:
        st.info("No saved brief markdown found in `data/briefs`.")

    st.subheader("Candidate/Approved Records For Brief Period")
    st.caption(f"Period: Last {days} days")
    if eligible_ids and missing_ids:
        st.warning(
            f"{len(missing_ids)} approved, non-excluded records are missing from the current brief selection. "
            "Use filter: Missing in brief (Approved, not used)."
        )

    if st.button("Regenerate brief", type="primary"):
        week_range = f"Last {days} days"
        selected_regen_ids = [str(r.get("record_id") or "") for r in approved_non_excluded_records if r.get("record_id")]
        regen_md = render_weekly_brief_md(approved_non_excluded_records, week_range)
        out_path = _save_brief(
            regen_md,
            week_range,
            selected_regen_ids,
            {"generated_by": "review_brief", "record_count": len(approved_non_excluded_records)},
        )
        _log_action("regenerate_brief", "brief")
        st.success(f"Regenerated brief with {len(approved_non_excluded_records)} items. Saved: {out_path}")

    f1, f2 = st.columns(2)
    with f1:
        used_only = st.checkbox("Used in brief only", value=False)
    with f2:
        missing_only = st.checkbox("Missing in brief (Approved, not used)", value=False)

    df = df_all.copy()
    if used_only:
        df = df[df["used_in_brief"] == True]
    if missing_only:
        df = df[
            (df["review_status"].astype(str) == "Approved")
            & (df["used_in_brief"] == False)
        ]
    df = df.reset_index(drop=True)

    if df.empty:
        st.info("No records match current filters.")

    selected_idx: Optional[int] = None
    if not df.empty:
        try:
            event = st.dataframe(
                df[
                    [
                        "title",
                        "source_type",
                        "publish_date_display",
                        "priority",
                        "review_status",
                        "topics",
                        "regions_relevant_to_kiekert",
                        "record_id",
                        "used_in_brief",
                    ]
                ],
                column_config={"publish_date_display": "publish_date"},
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key="review_brief_table",
            )
            rows = list(event.selection.rows) if event and hasattr(event, "selection") else []
            if rows:
                selected_idx = int(rows[0])
        except TypeError:
            st.dataframe(
                df[
                    [
                        "title",
                        "source_type",
                        "publish_date_display",
                        "priority",
                        "review_status",
                        "topics",
                        "regions_relevant_to_kiekert",
                        "record_id",
                        "used_in_brief",
                    ]
                ],
                column_config={"publish_date_display": "publish_date"},
                use_container_width=True,
                hide_index=True,
            )

with right:
    st.subheader("Selected Record Detail")

    if df.empty:
        st.info("No records available for detail view with current filters.")
        st.stop()

    fallback_id = None
    if selected_ids:
        for rid in selected_ids:
            if rid in set(df["record_id"].astype(str).tolist()):
                fallback_id = rid
                break
    if fallback_id is None and not df.empty:
        fallback_id = str(df.iloc[0]["record_id"])

    selected_record_id = fallback_id
    if selected_idx is not None and 0 <= selected_idx < len(df):
        selected_record_id = str(df.iloc[selected_idx]["record_id"])

    if selected_idx is None:
        options = df["record_id"].astype(str).tolist()
        selected_record_id = st.selectbox(
            "Select record",
            options=options,
            index=(options.index(fallback_id) if fallback_id in options else 0),
        )

    rec = records_by_id.get(str(selected_record_id or ""))
    if not rec:
        st.info("Select a record to view details.")
        st.stop()

    st.markdown(f"**Title:** {rec.get('title', 'Untitled')}")
    st.markdown(f"**Record ID:** `{rec.get('record_id', '-')}`")

    action_c1, action_c2 = st.columns(2)
    with action_c1:
        if st.button("Approve", disabled=str(rec.get("review_status") or "") == "Approved"):
            rid = str(rec.get("record_id") or "")
            if rid and _update_record_fields(rid, {"review_status": "Approved"}):
                _log_action("approve", rid)
                st.success(f"Approved record `{rid}`.")
                st.rerun()
    with action_c2:
        exclude_value = st.checkbox(
            "Exclude from brief",
            value=bool(rec.get("exclude_from_brief")),
            key=f"exclude_{rec.get('record_id')}",
        )
        current_exclude = bool(rec.get("exclude_from_brief"))
        if exclude_value != current_exclude:
            rid = str(rec.get("record_id") or "")
            if rid and _update_record_fields(rid, {"exclude_from_brief": bool(exclude_value)}):
                _log_action("toggle_exclude", rid)
                st.success(f"Updated exclude flag for `{rid}` to `{exclude_value}`.")
                st.rerun()

    evidence = rec.get("evidence_bullets") or []
    with st.expander("Evidence Bullets", expanded=True):
        if evidence:
            for b in evidence:
                st.markdown(f"- {b}")
        else:
            st.caption("No evidence bullets.")

    with st.expander("Insights & Implications", expanded=True):
        insights = rec.get("key_insights") or []
        implications = rec.get("strategic_implications") or []
        if insights:
            st.markdown("**Key Insights**")
            for item in insights:
                st.markdown(f"- {item}")
        if implications:
            st.markdown("**Strategic Implications** _(legacy)_")
            for item in implications:
                st.markdown(f"- {item}")
        if not insights and not implications:
            st.caption("No key insights available.")

    with st.expander("Mutations & Provenance", expanded=False):
        st.markdown("**_mutations**")
        st.json(rec.get("_mutations") or {})
        st.markdown("**_provenance**")
        st.json(rec.get("_provenance") or {})

    with st.expander("Router Log", expanded=False):
        summary = _router_log_summary(rec.get("_router_log"))
        st.markdown("**Summary**")
        st.json(summary or {})
        st.markdown("**Raw _router_log**")
        st.json(rec.get("_router_log") or {})

    st.markdown("**Source**")
    source_url = rec.get("source_sharepoint_url") or rec.get("original_url")
    if source_url:
        st.markdown(f"[Open source link]({source_url})")
    elif rec.get("source_pdf_path"):
        st.code(str(rec.get("source_pdf_path")))
    else:
        st.caption("No source link or source PDF path available.")

    action_logs = st.session_state.get("review_brief_action_log", [])
    if action_logs:
        st.markdown("**Recent Actions**")
        for item in action_logs[-5:][::-1]:
            st.caption(f"{item.get('ts')} | {item.get('action')} | {item.get('record_id')}")
