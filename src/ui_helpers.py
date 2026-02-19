from __future__ import annotations

import ast
import time
from typing import Any, Iterable, List, Tuple

import streamlit as st

from src.constants import _LEGACY_REVIEW_MAP

WORKFLOW_STEPS = ["Ingest", "Review", "Weekly Brief", "Insights"]
_NAV_LOCK_ACTIVE_KEY = "_nav_lock_active"
_NAV_LOCK_OWNER_KEY = "_nav_lock_owner"
_NAV_LOCK_REASON_KEY = "_nav_lock_reason"
_NAV_LOCK_SET_AT_KEY = "_nav_lock_set_at"
_NAV_LOCK_TTL_SECONDS = 60 * 60

_PAGE_SWITCH_PATHS = {
    "home": "Home.py",
    "ingest": "pages/01_Ingest.py",
    "review": "pages/02_Review_Approve.py",
    "weekly": "pages/03_Weekly_Executive_Brief.py",
    "insights": "pages/04_Insights.py",
    "admin": "pages/08_Admin.py",
}


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
            chips.append(f"**{idx} {name}**")
        else:
            chips.append(f"{idx} {name}")
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
