from __future__ import annotations

import ast
from typing import Any, Iterable, List, Tuple

import streamlit as st

from src.constants import _LEGACY_REVIEW_MAP

WORKFLOW_STEPS = ["Ingest", "Review", "Weekly Brief", "Insights"]


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

