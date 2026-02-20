from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from difflib import unified_diff
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import re

import pandas as pd
import streamlit as st

from src import ui
from src.briefing import (
    select_weekly_candidates,
    synthesize_weekly_brief_llm,
)
from src.ui_helpers import (
    clear_brief_history_cache,
    enforce_navigation_lock,
    load_brief_history,
    load_records_cached,
    normalize_review_status,
)

def _normalize_brief_markdown(text: str) -> str:
    """Apply markdown safety/display normalization for generated brief text."""
    if not text:
        return ""

    # Escape bare dollar signs outside inline code spans.
    parts = re.split(r"(`[^`]*`)", text)
    escaped_parts: List[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            escaped_parts.append(part)
        else:
            escaped_parts.append(re.sub(r"(?<!\\)\$", r"\\$", part))
    text = "".join(escaped_parts)

    # Render indented Supplier Implications lines as blockquote lines.
    text = re.sub(
        r"^[ \t]+(Supplier Implications:)\s*(.*)$",
        r"> **\1** \2",
        text,
        flags=re.MULTILINE,
    )
    return text


def _render_brief(text: str) -> None:
    normalized = _normalize_brief_markdown(text)
    if normalized:
        st.markdown(normalized)


_BRIEF_SECTION_HEADERS = [
    "AUTOMOTIVE COMPETITIVE INTELLIGENCE BRIEF",
    "EXECUTIVE SUMMARY",
    "HIGH PRIORITY DEVELOPMENTS",
    "FOOTPRINT REGION SIGNALS",
    "KEY DEVELOPMENTS BY TOPIC",
    "EMERGING TRENDS",
    "CONFLICTS & UNCERTAINTY",
    "RECOMMENDED ACTIONS",
    "APPENDIX",
]


def _split_brief_sections(text: str) -> List[Tuple[str, str]]:
    lines = (text or "").splitlines()
    if not lines:
        return []

    header_set = {h.upper() for h in _BRIEF_SECTION_HEADERS}
    marks: List[Tuple[int, str]] = []
    for idx, raw in enumerate(lines):
        line = str(raw).strip()
        if line and line.upper() in header_set:
            marks.append((idx, line.upper()))

    if not marks:
        return []

    sections: List[Tuple[str, str]] = []
    for i, (start_idx, header) in enumerate(marks):
        end_idx = marks[i + 1][0] if i + 1 < len(marks) else len(lines)
        body = "\n".join(lines[start_idx + 1:end_idx]).strip()
        sections.append((header, body))
    return sections


def _render_brief_collapsible(text: str) -> None:
    normalized = _normalize_brief_markdown(text)
    sections = _split_brief_sections(normalized)
    if not sections:
        _render_brief(normalized)
        return

    for idx, (header, body) in enumerate(sections):
        with st.expander(header, expanded=(idx == 0)):
            if body:
                st.markdown(body)
            else:
                st.caption("No content in this section.")


def _first_text(values: Any) -> str:
    if isinstance(values, list):
        for item in values:
            text = str(item or "").strip()
            if text:
                return text
    text = str(values or "").strip()
    return text


def _preview_source_date(rec: Dict[str, Any]) -> str:
    source = str(rec.get("source_type") or "-").strip() or "-"
    publish = str(rec.get("publish_date") or "").strip()
    if publish:
        return f"{source} - {publish}"
    created = str(rec.get("created_at") or "").strip()
    created_date = created[:10] if len(created) >= 10 else "-"
    return f"{source} - {created_date}"


def _build_quick_preview_text(records: List[Dict[str, Any]]) -> str:
    if not records:
        return "No items selected for this week."

    lines: List[str] = []
    for rec in records:
        snippet = _first_text(rec.get("key_insights")) or _first_text(rec.get("evidence_bullets")) or "No key insight/evidence line."
        lines.append(f"- {snippet} ({_preview_source_date(rec)})")
    return "\n".join(lines)

st.set_page_config(page_title="Cognitra", page_icon="assets/logo/cognitra-icon.png", layout="wide")
enforce_navigation_lock("weekly")
ui.init_page(active_step="Brief")
ui.render_page_header(
    "Brief",
    subtitle="Executive intelligence briefs generated from approved, structured records. No raw document content — only validated JSON inputs.",
    active_step="Brief",
)
ui.render_sidebar_utilities(model_label="gemini")

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


def _brief_family_and_version_from_name(file_name: str) -> Tuple[str, int]:
    stem = Path(str(file_name or "")).stem or "brief"
    m = re.match(r"^(?P<root>.+?)(?:-v(?P<ver>\d+))?$", stem)
    root = (m.group("root") if m else stem) or "brief"
    version = int(m.group("ver")) if m and m.group("ver") else 1
    return root, max(version, 1)


def _infer_brief_status(file_name: str) -> str:
    return "draft" if "draft" in str(file_name or "").lower() else "final"


def _rewrite_brief_index(rows: List[Dict[str, Any]]) -> None:
    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    BRIEF_INDEX.write_text((payload + "\n") if payload else "", encoding="utf-8")


def _synchronize_sidecar_status(file_name: str, status: str) -> None:
    if not file_name:
        return
    sidecar = (BRIEFS_DIR / file_name).with_suffix(".meta.json")
    if not sidecar.exists():
        return
    try:
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
    except Exception:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    meta["status"] = status
    fam, ver = _brief_family_and_version_from_name(file_name)
    meta.setdefault("brief_family_id", fam)
    meta.setdefault("version", ver)
    sidecar.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _supersede_previous_finals(brief_family_id: str, new_file_name: str) -> None:
    rows = _read_jsonl(BRIEF_INDEX)
    if not rows:
        return
    changed = False
    superseded_files: List[str] = []
    for row in rows:
        file_name = Path(str(row.get("file") or "")).name
        if not file_name or file_name == new_file_name:
            continue
        fam, ver = _brief_family_and_version_from_name(file_name)
        row_family = str(row.get("brief_family_id") or fam)
        row_version = int(row.get("version") or ver)
        row_status = str(row.get("status") or _infer_brief_status(file_name)).strip().lower()
        row["brief_family_id"] = row_family
        row["version"] = row_version
        if row_family == brief_family_id and row_status == "final":
            row["status"] = "superseded"
            superseded_files.append(file_name)
            changed = True
    if changed:
        _rewrite_brief_index(rows)
        for file_name in superseded_files:
            _synchronize_sidecar_status(file_name, "superseded")
        clear_brief_history_cache()


def _save_brief_to_path(
    path: Path,
    brief_text: str,
    week_range: str,
    selected_ids: List[str],
    usage: Dict[str, Any],
    *,
    status: str = "final",
    brief_family_id: Optional[str] = None,
    version: Optional[int] = None,
    supersedes_file: Optional[str] = None,
) -> Path:
    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(brief_text, encoding="utf-8")
    file_name = path.name
    inferred_family, inferred_version = _brief_family_and_version_from_name(file_name)
    status_norm = str(status or "final").strip().lower()
    if status_norm not in {"final", "superseded", "draft"}:
        status_norm = "final"
    family = str(brief_family_id or inferred_family)
    ver = int(version or inferred_version)

    meta = {
        "created_at": _now_iso(),
        "week_range": week_range,
        "file": str(path),
        "selected_record_ids": list(selected_ids),
        "usage": usage or {},
        "status": status_norm,
        "brief_family_id": family,
        "version": ver,
    }
    if supersedes_file:
        meta["supersedes_file"] = str(supersedes_file)
    path.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    with BRIEF_INDEX.open("a", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
    clear_brief_history_cache()
    return path


def _save_brief(brief_text: str, week_range: str, selected_ids: List[str], usage: Dict[str, Any]) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = BRIEFS_DIR / f"brief_{ts}.md"
    family, ver = _brief_family_and_version_from_name(path.name)
    return _save_brief_to_path(
        path,
        brief_text,
        week_range,
        selected_ids,
        usage,
        status="final",
        brief_family_id=family,
        version=ver,
    )


def _next_regenerated_brief_path(base_file_name: str) -> Path:
    root, current_ver = _brief_family_and_version_from_name(str(base_file_name or "brief"))
    candidate_ver = max(2, current_ver + 1)
    while True:
        candidate = BRIEFS_DIR / f"{root}-v{candidate_ver}.md"
        if not candidate.exists():
            return candidate
        candidate_ver += 1


def _save_regenerated_brief(
    base_file_name: str,
    brief_text: str,
    week_range: str,
    selected_ids: List[str],
    usage: Dict[str, Any],
) -> Path:
    path = _next_regenerated_brief_path(base_file_name)
    family, ver = _brief_family_and_version_from_name(path.name)
    _supersede_previous_finals(family, path.name)
    return _save_brief_to_path(
        path,
        brief_text,
        week_range,
        selected_ids,
        usage,
        status="final",
        brief_family_id=family,
        version=ver,
        supersedes_file=str(base_file_name or ""),
    )


def _synthesize_and_store(
    *,
    state_prefix: str,
    selected_records: List[Dict[str, Any]],
    selected_ids: List[str],
    week_range: str,
    provider: str,
    web_check_enabled: bool,
    model_override: str,
) -> bool:
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
            return False

    st.session_state[f"{state_prefix}_text"] = brief_text
    st.session_state[f"{state_prefix}_usage"] = usage or {}
    st.session_state[f"{state_prefix}_week_range"] = week_range
    st.session_state[f"{state_prefix}_selected_ids"] = list(selected_ids)
    return True


def _parse_publish_date(value: Any) -> Optional[date]:
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _parse_created_at(value: Any) -> Optional[date]:
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        return None


def _record_date_by_basis(rec: Dict[str, Any], basis_field: str) -> Optional[date]:
    if basis_field == "created_at":
        return _parse_created_at(rec.get("created_at"))
    return _parse_publish_date(rec.get("publish_date"))


def _record_filter_blob(rec: Dict[str, Any]) -> str:
    parts: List[str] = []
    scalar_fields = [
        "record_id",
        "title",
        "source_type",
        "actor_type",
        "priority",
        "confidence",
        "review_status",
        "already_shared",
        "shared_brief_week_range",
        "publish_date",
        "created_at",
    ]
    list_fields = [
        "regions_relevant_to_apex_mobility",
        "macro_themes_detected",
        "topics",
        "country_mentions",
        "companies_mentioned",
        "government_entities",
        "keywords",
    ]

    for key in scalar_fields:
        value = str(rec.get(key) or "").strip()
        if value:
            parts.append(value)
    for key in list_fields:
        values = rec.get(key) or []
        if isinstance(values, list):
            parts.extend(str(v).strip() for v in values if str(v).strip())

    return " ".join(parts).lower()


def _matches_filter_search(rec: Dict[str, Any], query: str) -> bool:
    normalized = " ".join(str(query or "").lower().replace(",", " ").split())
    if not normalized:
        return True
    blob = _record_filter_blob(rec)
    tokens = [tok for tok in normalized.split(" ") if tok]
    return all(token in blob for token in tokens)


def _diff_text(previous: str, current: str) -> Tuple[str, int, int]:
    diff_lines = list(unified_diff(previous.splitlines(), current.splitlines(), fromfile="previous", tofile="current", lineterm=""))
    added = sum(1 for ln in diff_lines if ln.startswith("+") and not ln.startswith("+++"))
    removed = sum(1 for ln in diff_lines if ln.startswith("-") and not ln.startswith("---"))
    return ("\n".join(diff_lines), added, removed)


def _safe_iso(value: Any) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s).isoformat()
    except Exception:
        return s


def _friendly_datetime(value: Any) -> str:
    s = _safe_iso(value)
    if not s:
        return "-"
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return s
    try:
        if dt.tzinfo is not None:
            dt = dt.astimezone()
    except Exception:
        pass
    return dt.strftime("%b %d, %Y %I:%M %p")


def _saved_brief_rows(records_by_id: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str]] = set()

    def _add_row(row: Dict[str, Any], default_file: str = "") -> None:
        if not isinstance(row, dict):
            return
        file_name = Path(str(row.get("file") or default_file)).name
        if not file_name:
            return
        inferred_family, inferred_version = _brief_family_and_version_from_name(file_name)
        row_status = str(row.get("status") or _infer_brief_status(file_name)).strip().lower()
        if row_status not in {"final", "superseded", "draft"}:
            row_status = _infer_brief_status(file_name)
        created_at = _safe_iso(row.get("created_at"))
        key = (file_name, created_at)
        if key in seen:
            return
        seen.add(key)
        selected_ids = [str(x) for x in (row.get("selected_record_ids") or []) if str(x)]
        themes: List[str] = []
        for rid in selected_ids:
            rec = records_by_id.get(rid, {})
            themes.extend([str(x) for x in (rec.get("macro_themes_detected") or []) if str(x).strip()])
        top_themes = []
        for name in themes:
            if name not in top_themes:
                top_themes.append(name)
        rows.append(
            {
                "file_name": file_name,
                "file_path": str(row.get("file") or (BRIEFS_DIR / file_name)),
                "created_at": created_at,
                "created_at_display": _friendly_datetime(created_at),
                "week_range": str(row.get("week_range") or ""),
                "record_count": len(selected_ids),
                "selected_record_ids": selected_ids,
                "key_themes": top_themes[:3],
                "status": row_status,
                "brief_family_id": str(row.get("brief_family_id") or inferred_family),
                "version": int(row.get("version") or inferred_version),
            }
        )

    for row in _read_jsonl(BRIEF_INDEX):
        _add_row(row)
    if BRIEFS_DIR.exists():
        for sidecar in sorted(BRIEFS_DIR.glob("brief_*.meta.json")):
            try:
                row = json.loads(sidecar.read_text(encoding="utf-8"))
            except Exception:
                continue
            _add_row(row, default_file=sidecar.name.replace(".meta.json", ".md"))

    rows.sort(key=lambda x: (x.get("created_at") or "", x.get("file_name") or ""), reverse=True)
    return rows


def _render_saved_brief_browser(records_by_id: Dict[str, Dict[str, Any]]) -> None:
    st.subheader("Saved Brief Browser")
    saved_rows = _saved_brief_rows(records_by_id)
    if not saved_rows:
        st.info("No saved brief found yet.")
        return

    for i, row in enumerate(saved_rows):
        row["brief_code"] = f"BRIEF-{len(saved_rows) - i:03d}"
        status_raw = str(row.get("status") or _infer_brief_status(str(row.get("file_name") or ""))).strip().lower()
        if status_raw not in {"final", "superseded", "draft"}:
            status_raw = _infer_brief_status(str(row.get("file_name") or ""))
        row["status"] = status_raw

    sf1, sf2 = st.columns([2.2, 1.4])
    with sf1:
        search_query = st.text_input(
            "Search briefs",
            placeholder="Search briefs...",
            key="wb_saved_search",
            label_visibility="collapsed",
        )
    with sf2:
        status_filter = st.selectbox(
            "Status",
            options=["All Statuses", "Final", "Superseded", "Draft"],
            index=0,
            key="wb_saved_status_filter",
            label_visibility="collapsed",
        )

    query_tokens = [tok for tok in str(search_query or "").lower().split() if tok]
    filtered_rows: List[Dict[str, Any]] = []
    for row in saved_rows:
        row_status = str(row.get("status") or "final").lower()
        if status_filter != "All Statuses" and row_status != str(status_filter).lower():
            continue
        if query_tokens:
            blob = " ".join(
                [
                    str(row.get("brief_code") or ""),
                    str(row.get("file_name") or ""),
                    str(row.get("week_range") or ""),
                    str(row.get("created_at_display") or ""),
                    " ".join(str(x) for x in (row.get("key_themes") or [])),
                ]
            ).lower()
            if not all(tok in blob for tok in query_tokens):
                continue
        filtered_rows.append(row)

    if not filtered_rows:
        st.warning("No saved briefs match current selection.")
        return

    selected_file = str(st.session_state.get("wb_saved_selected_file") or "")
    selectable_files = {str(r.get("file_name") or "") for r in filtered_rows}
    if selected_file not in selectable_files:
        selected_file = str(filtered_rows[0].get("file_name") or "")
        st.session_state["wb_saved_selected_file"] = selected_file

    lc, rc = st.columns([1.15, 3.45], gap="small")
    with lc:
        with st.container(border=True):
            st.markdown('<div class="cg-kpi-label">HISTORY</div>', unsafe_allow_html=True)
            for i, row in enumerate(filtered_rows):
                if i > 0:
                    st.divider()
                row_file = str(row.get("file_name") or "")
                is_selected = row_file == selected_file
                hx1, hx2 = st.columns([3.2, 1.4], vertical_alignment="top")
                with hx1:
                    st.markdown(f"**{row.get('brief_code') or row_file}**")
                    st.caption(str(row.get("week_range") or "-"))
                    st.caption(f"{int(row.get('record_count') or 0)} records | {row.get('created_at_display') or '-'}")
                with hx2:
                    ui.status_badge(
                        str(row.get("status") or "final"),
                        kind=(
                            "success"
                            if str(row.get("status") or "").lower() == "final"
                            else ("warning" if str(row.get("status") or "").lower() == "superseded" else "info")
                        ),
                    )
                    if st.button(
                        ("Opened" if is_selected else "Open"),
                        key=f"wb_saved_pick_{i}_{row_file}",
                        use_container_width=True,
                        type="secondary",
                    ):
                        st.session_state["wb_saved_selected_file"] = row_file
                        st.rerun()

    chosen = next((r for r in filtered_rows if str(r.get("file_name") or "") == selected_file), filtered_rows[0])
    idx = saved_rows.index(chosen)
    chosen_path = Path(str(chosen.get("file_path") or ""))
    if not chosen_path.exists():
        alt_path = BRIEFS_DIR / str(chosen.get("file_name") or "")
        chosen_path = alt_path if alt_path.exists() else chosen_path

    selected_ids = [str(x) for x in (chosen.get("selected_record_ids") or []) if str(x)]
    selected_records = [records_by_id.get(rid, {}) for rid in selected_ids]
    missing_records = sum(1 for rid in selected_ids if rid not in records_by_id)
    priority_counts = Counter(
        str(rec.get("priority") or "-")
        for rec in selected_records
        if isinstance(rec, dict) and rec
    )
    theme_count = len(
        {
            str(theme)
            for rec in selected_records
            if isinstance(rec, dict) and rec
            for theme in (rec.get("macro_themes_detected") or [])
            if str(theme).strip()
        }
    )
    with rc:
        with st.container(border=True):
            st.caption(
                f"{chosen.get('brief_code') or chosen.get('file_name')}  |  "
                f"{chosen.get('week_range') or '-'}  |  "
                f"{chosen.get('record_count')} records"
            )
            if chosen_path.exists():
                _render_brief(chosen_path.read_text(encoding="utf-8"))
            else:
                st.warning("Saved brief markdown file was not found on disk.")
            if missing_records:
                st.caption(f"{missing_records} selected record(s) are missing from current records.jsonl.")

    with st.expander("Included records", expanded=False):
        included_rows = []
        for rid in selected_ids:
            rec = records_by_id.get(str(rid), {})
            included_rows.append(
                {
                    "record_id": str(rid),
                    "title": str(rec.get("title") or "(record missing)"),
                    "priority": str(rec.get("priority") or "-"),
                    "confidence": str(rec.get("confidence") or "-"),
                    "source_type": str(rec.get("source_type") or "-"),
                }
            )
        st.dataframe(pd.DataFrame(included_rows), width='stretch', hide_index=True)
        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            ui.kpi_card("Saved briefs", len(saved_rows))
        with mc2:
            ui.kpi_card("High priority", priority_counts.get("High", 0))
        with mc3:
            ui.kpi_card("Macro themes", theme_count)

    valid_selected_records = [
        rec
        for rec in selected_records
        if isinstance(rec, dict) and rec and str(rec.get("record_id") or "").strip()
    ]
    regen_week_range = str(chosen.get("week_range") or "Last 30 days")

    with st.expander("Regenerate brief", expanded=False):
        r1, r2, r3 = st.columns(3)
        with r1:
            regen_provider = st.selectbox(
                "AI provider",
                ["gemini", "claude", "chatgpt"],
                index=0,
                key=f"wb_saved_provider_{idx}",
            )
        with r2:
            regen_web_check = st.checkbox(
                "Web coherence check (Gemini)",
                value=False,
                disabled=regen_provider != "gemini",
                key=f"wb_saved_web_check_{idx}",
            )
        with r3:
            regen_model_override = st.text_input(
                "Model override",
                value="",
                key=f"wb_saved_model_override_{idx}",
            )
        regen_clicked = st.button(
            "Regenerate This Brief",
            type="primary",
            disabled=not valid_selected_records,
            key=f"wb_saved_regen_btn_{idx}",
        )
        if regen_clicked:
            ok = _synthesize_and_store(
                state_prefix="wb_saved_regen",
                selected_records=valid_selected_records,
                selected_ids=selected_ids,
                week_range=regen_week_range,
                provider=regen_provider,
                web_check_enabled=regen_web_check,
                model_override=regen_model_override,
            )
            if ok:
                st.session_state["wb_saved_regen_file_name"] = str(chosen.get("file_name") or "")

    showing_regen_for = str(st.session_state.get("wb_saved_regen_file_name") or "")
    current_file = str(chosen.get("file_name") or "")
    if current_file and showing_regen_for == current_file and st.session_state.get("wb_saved_regen_text"):
        regen_text = st.session_state.get("wb_saved_regen_text") or ""
        regen_usage = st.session_state.get("wb_saved_regen_usage") or {}
        regen_ids = st.session_state.get("wb_saved_regen_selected_ids") or selected_ids
        suggested_regen_name = _next_regenerated_brief_path(current_file).name
        with st.expander("Regenerated brief (preview)", expanded=True):
            st.markdown(regen_text)
        st.caption(
            f"Model: {regen_usage.get('model', 'unknown')} | "
            f"prompt={regen_usage.get('prompt_tokens', '?')} "
            f"output={regen_usage.get('output_tokens', '?')} "
            f"total={regen_usage.get('total_tokens', '?')} | "
            f"attempts={regen_usage.get('attempts', 1)} | "
            f"validation_err={regen_usage.get('validation_errors_final', 0)}"
        )
        s1, s2 = st.columns(2)
        with s1:
            if st.button("Save regenerated brief", key=f"wb_saved_regen_save_{idx}"):
                path = _save_regenerated_brief(
                    current_file,
                    regen_text,
                    regen_week_range,
                    list(regen_ids),
                    regen_usage,
                )
                st.success(f"Saved: {path}")
        with s2:
            st.download_button(
                "Download regenerated .md",
                data=regen_text.encode("utf-8"),
                file_name=suggested_regen_name,
                mime="text/markdown",
                key=f"wb_saved_regen_dl_{idx}",
            )

    latest_path = _latest_brief_file()
    if latest_path and latest_path.exists() and chosen.get("file_name") == latest_path.name:
        prev_path = _previous_brief_file(latest_path)
        if prev_path:
            with st.expander("Compare with previous brief", expanded=False):
                prev_text = prev_path.read_text(encoding="utf-8")
                latest_text = latest_path.read_text(encoding="utf-8")
                diff, added, removed = _diff_text(prev_text, latest_text)
                st.caption(f"Previous: `{prev_path.name}` | Added {added} | Removed {removed}")
                st.code(diff or "No line-level changes.", language="diff")


records = load_records_cached()
if not records:
    st.info("No records yet.")
    st.stop()

records_by_id = {str(r.get("record_id") or ""): r for r in records}
meta_seed = _brief_sidecar_meta(_latest_brief_file()) or _latest_brief_meta_for_file(_latest_brief_file())
default_days = 30
if isinstance(meta_seed.get("week_range"), str):
    parts = str(meta_seed.get("week_range")).split()
    if len(parts) >= 2 and parts[0].lower() == "last" and parts[1].isdigit():
        default_days = max(7, min(90, int(parts[1])))
today = date.today()
created_dates = [d for d in (_parse_created_at(r.get("created_at")) for r in records) if d]
publish_dates = [d for d in (_parse_publish_date(r.get("publish_date")) for r in records) if d]
default_record_from = min(created_dates) if created_dates else (today - timedelta(days=3650))
default_record_to = max([today, *created_dates]) if created_dates else today
default_publish_from = today - timedelta(days=20)
default_publish_to = max([today, *publish_dates]) if publish_dates else today


def _reset_brief_filters() -> None:
    st.session_state["wb_hide_shared"] = True
    st.session_state["wb_basis"] = "Record added date (created_at)"
    st.session_state["wb_date_from"] = default_record_from
    st.session_state["wb_date_to"] = default_record_to
    st.session_state["wb_include_excluded"] = False
    st.session_state["wb_share_ready"] = False
    st.session_state["wb_use_publish_range"] = False
    st.session_state["wb_record_from"] = default_record_from
    st.session_state["wb_record_to"] = default_record_to
    st.session_state["wb_publish_from"] = default_publish_from
    st.session_state["wb_publish_to"] = default_publish_to
    st.session_state["wb_status"] = ["Pending", "Approved"]
    st.session_state["wb_priority"] = ["High", "Medium", "Low"]
    st.session_state["wb_region"] = []
    st.session_state["wb_theme"] = []
    st.session_state["wb_filter_search"] = ""
    st.session_state["wb_quick_region"] = "All Regions"
    st.session_state["wb_quick_topic"] = "All Topics"
    st.session_state["wb_quick_source"] = "All Sources"


if st.session_state.pop("wb_clear_filters_requested", False):
    _reset_brief_filters()

# One-time reset to avoid stale filter carry-over hiding fresh records.
if not st.session_state.get("_brief_filter_defaults_v3_applied", False):
    _reset_brief_filters()
    st.session_state["_brief_filter_defaults_v3_applied"] = True

# Ensure hide-shared starts enabled by default for existing sessions.
if not st.session_state.get("_brief_hide_shared_default_v1_applied", False):
    st.session_state["wb_hide_shared"] = True
    st.session_state["_brief_hide_shared_default_v1_applied"] = True

tab_build, tab_saved = st.tabs(["Build This Week's Brief", "Saved Brief Browser"])
with tab_saved:
    _render_saved_brief_browser(records_by_id)

with tab_build:
    st.subheader("Selection Workspace")
    basis_label = str(st.session_state.get("wb_basis", "Record added date (created_at)"))
    hide_already_shared = bool(st.session_state.get("wb_hide_shared", True))

    date_basis_field = "publish_date" if "publish_date" in basis_label else "created_at"

    include_excluded = False
    record_from = default_record_from
    record_to = default_record_to
    apply_publish_range = False
    publish_from = default_publish_from
    publish_to = default_publish_to
    region_filter: List[str] = []
    topic_filter: List[str] = []
    source_filter: List[str] = []
    filter_search = ""
    quick_region = "All Regions"
    quick_topic = "All Topics"
    quick_source = "All Sources"
    provider = "gemini"
    web_check_enabled = False
    model_override = ""

    # Get date range from session state (set in filter section)
    filter_date_from = st.session_state.get("wb_date_from", default_record_from)
    filter_date_to = st.session_state.get("wb_date_to", default_record_to)
    week_range = f"{filter_date_from} to {filter_date_to} by {date_basis_field}"
    
    candidates_seed = select_weekly_candidates(records, days=36500, include_excluded=include_excluded)

    missing_basis_dates = 0
    time_window_candidates: List[Dict[str, Any]] = []
    for rec in candidates_seed:
        rd = _record_date_by_basis(rec, date_basis_field)
        if not rd:
            missing_basis_dates += 1
            continue
        if filter_date_from <= rd <= filter_date_to:
            time_window_candidates.append(rec)

    brief_history = load_brief_history()
    annotated_candidates: List[Dict[str, Any]] = []
    for rec in time_window_candidates:
        rec_id = str(rec.get("record_id") or "")
        shared_rows = brief_history.get(rec_id, [])
        latest_shared = shared_rows[-1] if shared_rows else {}
        out = dict(rec)
        out["already_shared"] = "Yes" if shared_rows else "No"
        out["shared_brief_file"] = str(latest_shared.get("file") or "")
        out["shared_brief_week_range"] = str(latest_shared.get("week_range") or "")
        out["shared_brief_created_at"] = str(latest_shared.get("created_at") or "")
        out["_already_shared_bool"] = bool(shared_rows)
        annotated_candidates.append(out)

    candidates = [r for r in annotated_candidates if not r.get("_already_shared_bool")] if hide_already_shared else annotated_candidates
    region_options = sorted({str(x) for r in candidates for x in (r.get("regions_relevant_to_apex_mobility") or []) if str(x).strip()})
    topic_options = sorted({str(x) for r in candidates for x in (r.get("topics") or []) if str(x).strip()})
    source_options = sorted({str(r.get("source_type") or "").strip() for r in candidates if str(r.get("source_type") or "").strip()})

    with st.expander("Filters", expanded=False):
        quick_region_options = ["All Regions"] + region_options
        quick_topic_options = ["All Topics"] + topic_options
        quick_source_options = ["All Sources"] + source_options
        q1, q2, q3, q4 = st.columns([2.3, 1.3, 1.4, 1.3])
        with q1:
            filter_search = st.text_input(
                "Search records",
                key="wb_filter_search",
                placeholder="Search records...",
                label_visibility="collapsed",
            )
        with q2:
            quick_region = st.selectbox(
                "Region",
                quick_region_options,
                key="wb_quick_region",
                label_visibility="collapsed",
            )
        with q3:
            quick_topic = st.selectbox(
                "Topic",
                quick_topic_options,
                key="wb_quick_topic",
                label_visibility="collapsed",
            )
        with q4:
            quick_source = st.selectbox(
                "Source",
                quick_source_options,
                key="wb_quick_source",
                label_visibility="collapsed",
            )
        c1, c2 = st.columns([1.2, 1.8])
        with c1:
            basis_label = st.selectbox(
                "Date basis",
                options=["Published date (publish_date)", "Record added date (created_at)"],
                index=1,
                key="wb_basis",
            )
        with c2:
            date_range = st.date_input(
                "Date range",
                value=(st.session_state.get("wb_date_from", default_record_from), st.session_state.get("wb_date_to", default_record_to)),
                key="wb_date_range",
                label_visibility="collapsed",
            )
            # Handle both single date and range inputs
            if isinstance(date_range, tuple) and len(date_range) == 2:
                filter_date_from, filter_date_to = date_range
            else:
                filter_date_from = filter_date_to = date_range
        hide_already_shared = st.checkbox(
            "Hide records already included in saved briefs",
            value=True,
            key="wb_hide_shared",
        )

    if quick_region != "All Regions" and not region_filter:
        region_filter = [quick_region]
    if quick_topic != "All Topics" and not topic_filter:
        topic_filter = [quick_topic]
    if quick_source != "All Sources" and not source_filter:
        source_filter = [quick_source]

    candidates = [r for r in candidates if normalize_review_status(r.get("review_status")) == "Approved"]
    if region_filter:
        region_set = set(region_filter)
        candidates = [r for r in candidates if region_set & set(r.get("regions_relevant_to_apex_mobility") or [])]
    if topic_filter:
        topic_set = set(topic_filter)
        candidates = [r for r in candidates if topic_set & set(r.get("topics") or [])]
    if source_filter:
        source_set = set(source_filter)
        candidates = [r for r in candidates if str(r.get("source_type") or "").strip() in source_set]
    if filter_search.strip():
        candidates = [r for r in candidates if _matches_filter_search(r, filter_search)]

    def _in_record_range(rec: Dict[str, Any]) -> bool:
        rd = _parse_created_at(rec.get("created_at"))
        return bool(rd and record_from <= rd <= record_to)

    def _in_publish_range(rec: Dict[str, Any]) -> bool:
        pdv = _parse_publish_date(rec.get("publish_date"))
        return bool(pdv and publish_from <= pdv <= publish_to)

    candidates = [r for r in candidates if _in_record_range(r)]
    if apply_publish_range:
        candidates = [r for r in candidates if _in_publish_range(r)]

    if missing_basis_dates:
        st.caption(f"{missing_basis_dates} records missing `{date_basis_field}` were excluded from the time window.")

    if not candidates:
        st.warning("No candidates found for this period.")
        st.stop()

    approved_non_excluded = [
        r for r in candidates if normalize_review_status(r.get("review_status")) == "Approved" and not bool(r.get("is_duplicate", False))
    ]
    default_ids = [str(r.get("record_id")) for r in approved_non_excluded if r.get("record_id")]
    default_set = set(default_ids)
    kpi_slot = st.container()

    selection_rows = []
    for r in candidates:
        rid = str(r.get("record_id") or "")
        if not rid:
            continue
        selection_rows.append(
            {
                "Include": rid in default_set,
                "record_id": rid,
                "title": str(r.get("title") or "Untitled"),
                "source": str(r.get("source_type") or "-"),
                "priority": str(r.get("priority") or "-"),
                "confidence": str(r.get("confidence") or "-"),
                "in_brief": "Yes" if bool(r.get("_already_shared_bool")) else "No",
            }
        )

    with st.expander("See included records", expanded=False):
        selection_df = pd.DataFrame(selection_rows)
        edited_df = st.data_editor(
            selection_df,
            width='stretch',
            hide_index=True,
            disabled=["record_id", "title", "source", "priority", "confidence", "in_brief"],
            column_config={"Include": st.column_config.CheckboxColumn(required=True)},
            key="weekly_selection_editor",
        )
    selected_ids = edited_df.loc[edited_df["Include"], "record_id"].astype(str).tolist() if not edited_df.empty else []
    selected_set = set(selected_ids)
    selected_records = [r for r in candidates if str(r.get("record_id")) in selected_set]

    eligible_ids = set(default_ids)
    missing_approved = eligible_ids - selected_set
    if missing_approved:
        st.warning(f"{len(missing_approved)} approved, non-excluded records are not selected for this brief.")

    priority_counts = Counter(str(r.get("priority") or "-") for r in selected_records)
    region_counts = Counter(str(x) for r in selected_records for x in (r.get("regions_relevant_to_apex_mobility") or []))
    theme_counts = Counter(str(x) for r in selected_records for x in (r.get("macro_themes_detected") or []))
    with kpi_slot:
        bc1, bc2, bc3, bc4, bc5, bc6 = st.columns(6)
        with bc1:
            ui.kpi_card("Selected", len(selected_records))
        with bc2:
            ui.kpi_card("High priority", priority_counts.get("High", 0))
        with bc3:
            ui.kpi_card("Medium priority", priority_counts.get("Medium", 0))
        with bc4:
            ui.kpi_card("Low priority", priority_counts.get("Low", 0))
        with bc5:
            ui.kpi_card("Regions covered", len(region_counts))
        with bc6:
            ui.kpi_card("Macro themes covered", len(theme_counts))

    st.divider()
    st.markdown("## Executive-Ready Output")

    g1, g2 = st.columns(2)
    with g1:
        generate_clicked = st.button("Generate AI Brief", type="primary", disabled=not selected_records)
    with g2:
        regenerate_clicked = st.button("Regenerate AI Brief", disabled=not selected_records)

    if generate_clicked or regenerate_clicked:
        _synthesize_and_store(
            state_prefix="weekly_ai_brief",
            selected_records=selected_records,
            selected_ids=selected_ids,
            week_range=week_range,
            provider=provider,
            web_check_enabled=web_check_enabled,
            model_override=model_override,
        )

    saved_text = st.session_state.get("weekly_ai_brief_text")
    saved_usage = st.session_state.get("weekly_ai_brief_usage", {}) if saved_text else {}
    saved_week_range = st.session_state.get("weekly_ai_brief_week_range", week_range) if saved_text else week_range
    saved_ids = st.session_state.get("weekly_ai_brief_selected_ids", selected_ids) if saved_text else selected_ids
    quick_preview_text = _build_quick_preview_text(selected_records)

    with st.expander("Deterministic Preview", expanded=False):
        st.caption(f"Quick preview for {week_range}")
        st.markdown(quick_preview_text)

    st.subheader("AI Brief")
    if saved_text:
        _render_brief_collapsible(saved_text)
        st.caption(
            f"Model: {saved_usage.get('model', 'unknown')} | "
            f"prompt={saved_usage.get('prompt_tokens', '?')} "
            f"output={saved_usage.get('output_tokens', '?')} "
            f"total={saved_usage.get('total_tokens', '?')} | "
            f"attempts={saved_usage.get('attempts', 1)} | "
            f"validation_err={saved_usage.get('validation_errors_final', 0)}"
        )
        a1, a2 = st.columns(2)
        with a1:
            if st.button("Save brief"):
                path = _save_brief(saved_text, saved_week_range, list(saved_ids), saved_usage)
                st.success(f"Saved: {path}")
        with a2:
            st.download_button(
                "Download brief",
                data=saved_text.encode("utf-8"),
                file_name=f"weekly_brief_{saved_week_range.replace(' ', '_')}.md",
                mime="text/markdown",
            )
        with st.expander("Copy / Export (raw text)", expanded=False):
            st.text_area("Copy-friendly version", value=saved_text, height=280)
    else:
        st.info("Generate the AI brief to compare it with the deterministic preview.")
