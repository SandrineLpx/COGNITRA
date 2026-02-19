from __future__ import annotations

import ast
import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import streamlit as st

from src.constants import _LEGACY_REVIEW_MAP

WORKFLOW_STEPS = ["Ingest", "Review", "Brief", "Insights", "Admin"]
_NAV_LOCK_ACTIVE_KEY = "_nav_lock_active"
_NAV_LOCK_OWNER_KEY = "_nav_lock_owner"
_NAV_LOCK_REASON_KEY = "_nav_lock_reason"
_NAV_LOCK_SET_AT_KEY = "_nav_lock_set_at"
_NAV_LOCK_TTL_SECONDS = 60 * 60
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
BRIEFS_DIR = DATA_DIR / "briefs"
BRIEF_INDEX = BRIEFS_DIR / "index.jsonl"

_PAGE_SWITCH_PATHS = {
    "home": "Home.py",
    "ingest": "pages/01_Ingest.py",
    "review": "pages/02_Review.py",
    "weekly": "pages/03_Brief.py",
    "insights": "pages/04_Insights.py",
    "admin": "pages/Admin.py",
}


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
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


def load_brief_history() -> Dict[str, List[Dict[str, str]]]:
    """Record->brief membership map built from saved brief index + sidecars."""
    by_record_id: Dict[str, List[Dict[str, str]]] = {}
    seen_rows: set[Tuple[str, str]] = set()

    def _ingest_row(row: Dict[str, Any], default_file: str = "") -> None:
        ids = row.get("selected_record_ids") or []
        if not isinstance(ids, list):
            return
        file_name = Path(str(row.get("file") or default_file)).name
        week_range = str(row.get("week_range") or "")
        created_at = str(row.get("created_at") or "")
        row_key = (file_name, created_at)
        if row_key in seen_rows:
            return
        seen_rows.add(row_key)
        for rid in ids:
            rid_s = str(rid or "").strip()
            if not rid_s:
                continue
            by_record_id.setdefault(rid_s, []).append(
                {
                    "file": file_name,
                    "week_range": week_range,
                    "created_at": created_at,
                }
            )

    for row in read_jsonl(BRIEF_INDEX):
        _ingest_row(row)

    if BRIEFS_DIR.exists():
        for sidecar in sorted(BRIEFS_DIR.glob("brief_*.meta.json")):
            try:
                row = json.loads(sidecar.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(row, dict):
                continue
            _ingest_row(row, default_file=sidecar.name.replace(".meta.json", ".md"))

    return by_record_id


def latest_brief_entry_for_record(brief_history: Dict[str, List[Dict[str, str]]], record_id: Any) -> Dict[str, str]:
    rid = str(record_id or "").strip()
    if not rid:
        return {}
    rows = brief_history.get(rid) or []
    if not rows:
        return {}
    return rows[-1]


def normalize_review_status(value: Any) -> str:
    s = str(value or "").strip()
    if not s:
        return "Pending"
    return _LEGACY_REVIEW_MAP.get(s, s)


def safe_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        if s.startswith("["):
            try:
                parsed = ast.literal_eval(s)
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []
        return [s]
    return []


def join_list(value: Any) -> str:
    return ", ".join(str(x) for x in safe_list(value) if str(x).strip())


def best_record_link(record: dict) -> Tuple[str, str]:
    original_url = str(record.get("original_url") or "").strip()
    sharepoint_url = str(record.get("source_sharepoint_url") or "").strip()
    source_pdf_path = str(record.get("source_pdf_path") or "").strip()
    if original_url:
        return "Original URL", original_url
    if sharepoint_url:
        return "Source SharePoint URL", sharepoint_url
    if source_pdf_path:
        return "Source PDF path", source_pdf_path
    return "No link", ""


def workflow_ribbon(current_step: int) -> None:
    chips: List[str] = []
    for idx, name in enumerate(WORKFLOW_STEPS, start=1):
        if idx == current_step:
            chips.append(f"**{idx:02d} {name}**")
        else:
            chips.append(f"{idx:02d} {name}")
    st.caption(" -> ".join(chips))


def set_navigation_lock(active: bool, owner_page: str, reason: str = "Processing") -> None:
    if active:
        st.session_state[_NAV_LOCK_ACTIVE_KEY] = True
        st.session_state[_NAV_LOCK_OWNER_KEY] = str(owner_page or "ingest")
        st.session_state[_NAV_LOCK_REASON_KEY] = str(reason or "Processing")
        st.session_state[_NAV_LOCK_SET_AT_KEY] = int(time.time())
        return
    st.session_state.pop(_NAV_LOCK_ACTIVE_KEY, None)
    st.session_state.pop(_NAV_LOCK_OWNER_KEY, None)
    st.session_state.pop(_NAV_LOCK_REASON_KEY, None)
    st.session_state.pop(_NAV_LOCK_SET_AT_KEY, None)


def _lock_state() -> Tuple[bool, str, str]:
    active = bool(st.session_state.get(_NAV_LOCK_ACTIVE_KEY, False))
    owner = str(st.session_state.get(_NAV_LOCK_OWNER_KEY, "") or "")
    reason = str(st.session_state.get(_NAV_LOCK_REASON_KEY, "Processing") or "Processing")
    set_at = int(st.session_state.get(_NAV_LOCK_SET_AT_KEY, 0) or 0)
    if active and set_at > 0 and (int(time.time()) - set_at) > _NAV_LOCK_TTL_SECONDS:
        set_navigation_lock(False, owner_page=owner, reason=reason)
        return False, "", ""
    return active, owner, reason


def enforce_navigation_lock(current_page: str) -> None:
    active, owner, reason = _lock_state()
    current = str(current_page or "").strip().lower()
    if not active:
        return
    if owner == current:
        return
    target = _PAGE_SWITCH_PATHS.get(owner, _PAGE_SWITCH_PATHS["ingest"])
    st.warning(f"{reason} is running. Stay on the active page until it completes.")
    try:
        st.switch_page(target)
    except Exception:
        pass
    st.stop()


def render_navigation_lock_notice(current_page: str) -> None:
    active, owner, reason = _lock_state()
    current = str(current_page or "").strip().lower()
    if not active or owner != current:
        return
    st.warning(f"{reason} is running. Navigation is temporarily locked to avoid interrupted extraction and token waste.")
    st.markdown(
        """
<style>
[data-testid="stSidebarNav"] a {
  pointer-events: none !important;
  opacity: 0.45 !important;
}
</style>
        """,
        unsafe_allow_html=True,
    )
