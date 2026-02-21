from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from difflib import unified_diff
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import re

import pandas as pd
import streamlit as st

import src.ui as ui
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


_BRIEF_SECTION_HEADERS = [
    "AUTOMOTIVE COMPETITIVE INTELLIGENCE BRIEF",
    "EXECUTIVE ALERT",
    "EXECUTIVE SUMMARY",
    "HIGH PRIORITY DEVELOPMENTS",
    "FOOTPRINT REGION SIGNALS",
    "KEY DEVELOPMENTS BY TOPIC",
    "EMERGING TRENDS",
    "CONFLICTS & UNCERTAINTY",
    "RECOMMENDED ACTIONS",
    "APPENDIX",
]
_DETAILS_SUMMARY_RE = re.compile(r"^\s*<summary>\s*(.*?)\s*</summary>\s*$", re.IGNORECASE)
_DETAILS_SUMMARY_ANY_RE = re.compile(r"<summary>\s*(.*?)\s*</summary>", re.IGNORECASE)
_REC_ID_RE = re.compile(r"\bREC\s*[:#]\s*([A-Za-z0-9_-]+)\b", re.IGNORECASE)
_REC_CITATION_PAREN_RE = re.compile(r"\(([^)]*\bREC\s*[:#][^)]+)\)", re.IGNORECASE)


def _split_brief_sections(text: str) -> List[Tuple[str, str]]:
    lines = (text or "").splitlines()
    if not lines:
        return []

    header_set = {h.upper() for h in _BRIEF_SECTION_HEADERS}
    marks: List[Tuple[int, str]] = []
    for idx, raw in enumerate(lines):
        line = str(raw).strip()
        if not line:
            continue
        if line.upper() in header_set:
            marks.append((idx, line.upper()))
            continue
        m = _DETAILS_SUMMARY_RE.match(line) or _DETAILS_SUMMARY_ANY_RE.search(line)
        if m:
            summary_header = str(m.group(1) or "").strip().upper()
            if summary_header in header_set:
                marks.append((idx, summary_header))

    if not marks:
        return []

    sections: List[Tuple[str, str]] = []
    for i, (start_idx, header) in enumerate(marks):
        end_idx = marks[i + 1][0] if i + 1 < len(marks) else len(lines)
        body_lines: List[str] = []
        for raw in lines[start_idx + 1:end_idx]:
            s = str(raw).strip()
            line_no_tags = re.sub(r"</?\s*details\s*>", "", s, flags=re.IGNORECASE)
            line_no_tags = _DETAILS_SUMMARY_ANY_RE.sub("", line_no_tags).strip()
            if not line_no_tags:
                continue
            body_lines.append(line_no_tags)
        body = "\n".join(body_lines).strip()
        sections.append((header, body))
    return sections


def _source_label_for_record(rec: Dict[str, Any]) -> str:
    label = str(rec.get("source_type") or "").strip()
    return label if label else "Source"


def _first_nonempty_line(values: Any) -> str:
    if isinstance(values, list):
        for item in values:
            txt = str(item or "").strip()
            if txt:
                return txt
        return ""
    return str(values or "").strip()


def _source_tooltip_for_record(rec: Dict[str, Any], rid: str) -> str:
    _ = rid  # keep signature stable for call sites
    snippet = _first_nonempty_line(rec.get("evidence_bullets")) or _first_nonempty_line(rec.get("key_insights"))
    if not snippet:
        snippet = str(rec.get("title") or "").strip()
    snippet = re.sub(r"\s+", " ", snippet).strip()
    return snippet or "Evidence snippet unavailable."


def _wrap_tooltip_lines(text: str, width: int = 64) -> str:
    words = str(text or "").split()
    if not words:
        return ""
    lines: List[str] = []
    current: List[str] = []
    current_len = 0
    for w in words:
        wlen = len(w)
        if current and (current_len + 1 + wlen) > width:
            lines.append(" ".join(current))
            current = [w]
            current_len = wlen
        else:
            current.append(w)
            current_len = (current_len + 1 + wlen) if current_len else wlen
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)


def _replace_rec_citations_with_sources(text: str, record_lookup: Optional[Dict[str, Dict[str, Any]]]) -> str:
    lookup = record_lookup or {}
    if not lookup:
        return text

    def _repl(match: re.Match[str]) -> str:
        inner = str(match.group(1) or "")
        ids = _REC_ID_RE.findall(inner)
        if not ids:
            return match.group(0)
        ordered_ids: List[str] = []
        for rid in ids:
            rs = str(rid or "").strip()
            if rs and rs not in ordered_ids:
                ordered_ids.append(rs)
        if not ordered_ids:
            return match.group(0)

        tags: List[str] = []
        for rid in ordered_ids:
            rec = lookup.get(rid) or {}
            label = _source_label_for_record(rec) if rec else f"REC:{rid}"
            tooltip = _source_tooltip_for_record(rec, rid) if rec else f"REC:{rid}"
            tooltip_multiline = _wrap_tooltip_lines(tooltip)
            tags.append(
                f'<span class="brief-source" data-tooltip="{escape(tooltip_multiline, quote=True)}" '
                f'tabindex="0">{escape(label)}</span>'
            )
        return "(" + ", ".join(tags) + ")"

    return _REC_CITATION_PAREN_RE.sub(_repl, text or "")


def _ensure_brief_source_css() -> None:
    if st.session_state.get("_brief_source_css_injected"):
        return
    st.markdown(
        """
<style>
.brief-source {
  color: #1d4ed8;
  border-bottom: 1px dotted #1d4ed8;
  cursor: help;
  white-space: nowrap;
  font-weight: 600;
  position: relative;
  display: inline-block;
}
.brief-source:hover {
  color: #1e40af;
  border-bottom-color: #1e40af;
}
.brief-source:hover::after,
.brief-source:focus::after {
  content: attr(data-tooltip);
  position: absolute;
  left: 0;
  top: 1.45em;
  background: #111827;
  color: #f9fafb;
  border-radius: 6px;
  padding: 8px 10px;
  max-width: 420px;
  min-width: 180px;
  white-space: normal;
  line-height: 1.3;
  font-weight: 400;
  font-size: 0.85rem;
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.25);
  z-index: 10000;
}
</style>
""",
        unsafe_allow_html=True,
    )
    st.session_state["_brief_source_css_injected"] = True


def _render_brief(text: str, record_lookup: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
    normalized = _normalize_brief_markdown(text)
    rendered = _replace_rec_citations_with_sources(normalized, record_lookup)
    if rendered:
        if record_lookup:
            _ensure_brief_source_css()
        st.markdown(rendered, unsafe_allow_html=bool(record_lookup))


def _render_brief_collapsible(text: str, record_lookup: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
    normalized = _normalize_brief_markdown(text)
    sections = _split_brief_sections(normalized)
    if not sections:
        _render_brief(normalized, record_lookup=record_lookup)
        return
    if record_lookup:
        _ensure_brief_source_css()

    always_open = {
        "AUTOMOTIVE COMPETITIVE INTELLIGENCE BRIEF",
        "EXECUTIVE ALERT",
        "EXECUTIVE SUMMARY",
    }

    for header, body in sections:
        if header in always_open:
            if header in {"AUTOMOTIVE COMPETITIVE INTELLIGENCE BRIEF", "EXECUTIVE ALERT"}:
                st.markdown(f"## {header}")
            else:
                st.markdown(f"### {header}")
            if body:
                body_rendered = _replace_rec_citations_with_sources(body, record_lookup)
                st.markdown(body_rendered, unsafe_allow_html=bool(record_lookup))
            else:
                st.caption("No content in this section.")
            continue

        with st.expander(header, expanded=False):
            if body:
                body_rendered = _replace_rec_citations_with_sources(body, record_lookup)
                st.markdown(body_rendered, unsafe_allow_html=bool(record_lookup))
            else:
                st.caption("No content in this section.")


def _to_saved_collapsible_markdown(text: str) -> str:
    """Persist sections as markdown collapsibles, keeping title + Executive Summary open."""
    raw = str(text or "").strip()
    if not raw:
        return ""
    if "<details>" in raw.lower():
        return raw

    sections = _split_brief_sections(raw)
    if not sections:
        return raw

    always_open = {
        "AUTOMOTIVE COMPETITIVE INTELLIGENCE BRIEF",
        "EXECUTIVE ALERT",
        "EXECUTIVE SUMMARY",
    }

    out: List[str] = []
    for header, body in sections:
        body_text = str(body or "").strip()
        if header in always_open:
            out.append(header)
            if body_text:
                out.append(body_text)
            out.append("")
            continue

        out.append("<details>")
        out.append(f"<summary>{header}</summary>")
        out.append("")
        if body_text:
            out.append(body_text)
        else:
            out.append("_No content in this section._")
        out.append("")
        out.append("</details>")
        out.append("")

    return "\n".join(out).strip() + "\n"


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


def _delete_saved_brief(file_name: str, file_path: Optional[str] = None) -> Tuple[bool, str]:
    target_name = Path(str(file_name or "")).name
    if not target_name:
        return False, "Invalid brief file name."

    removed_any = False
    errors: List[str] = []

    candidates = []
    if file_path:
        candidates.append(Path(str(file_path)))
    candidates.append(BRIEFS_DIR / target_name)

    seen_paths: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if key in seen_paths:
            continue
        seen_paths.add(key)
        try:
            if candidate.exists():
                candidate.unlink()
                removed_any = True
        except Exception as exc:
            errors.append(f"Failed to delete {candidate.name}: {exc}")

        sidecar = candidate.with_suffix(".meta.json")
        try:
            if sidecar.exists():
                sidecar.unlink()
                removed_any = True
        except Exception as exc:
            errors.append(f"Failed to delete {sidecar.name}: {exc}")

    rows = _read_jsonl(BRIEF_INDEX)
    if rows:
        kept = [row for row in rows if Path(str(row.get("file") or "")).name != target_name]
        if len(kept) != len(rows):
            _rewrite_brief_index(kept)
            removed_any = True

    clear_brief_history_cache()

    if errors:
        return removed_any, " | ".join(errors)
    if removed_any:
        return True, f"Deleted {target_name}."
    return False, f"No files found for {target_name}."


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
    saved_text = _to_saved_collapsible_markdown(brief_text)
    path.write_text(saved_text, encoding="utf-8")
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
) -> bool:
    with st.spinner("Synthesizing executive brief..."):
        try:
            brief_text, usage = synthesize_weekly_brief_llm(
                selected_records,
                week_range,
                provider=provider,
                web_check=bool(web_check_enabled and provider == "gemini"),
                model_override=None,
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


def _publish_week_range_from_records(records: List[Dict[str, Any]], fallback_range: str = "") -> str:
    publish_dates = sorted(
        d for d in (_parse_publish_date(rec.get("publish_date")) for rec in (records or [])) if d
    )
    if publish_dates:
        return f"{publish_dates[0]} to {publish_dates[-1]} (Publish date)"
    fallback = str(fallback_range or "").strip()
    if fallback:
        return fallback.replace("(Upload date)", "(Publish date)")
    return "Publish date unavailable"


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
    st.subheader("Saved Briefs")
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
        if "wb_saved_status_filter_initialized" not in st.session_state:
            st.session_state["wb_saved_status_filter"] = "Final"
            st.session_state["wb_saved_status_filter_initialized"] = True
        status_filter = st.selectbox(
            "Status",
            options=["All Statuses", "Final", "Superseded", "Draft"],
            index=1,
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

    displayed_rows = filtered_rows[:5]
    if len(filtered_rows) > 5:
        st.caption("Showing latest 5 briefs. Refine filters to view older briefs.")

    selected_file = str(st.session_state.get("wb_saved_selected_file") or "")
    selectable_files = {str(r.get("file_name") or "") for r in displayed_rows}
    if selected_file not in selectable_files:
        selected_file = str(displayed_rows[0].get("file_name") or "")
        st.session_state["wb_saved_selected_file"] = selected_file

    lc, rc = st.columns([1.15, 3.45], gap="small")
    with lc:
        with st.container(border=True):
            st.markdown('<div class="cg-kpi-label">HISTORY</div>', unsafe_allow_html=True)
            for i, row in enumerate(displayed_rows):
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

    chosen = next((r for r in displayed_rows if str(r.get("file_name") or "") == selected_file), displayed_rows[0])
    idx = saved_rows.index(chosen)
    chosen_path = Path(str(chosen.get("file_path") or ""))
    if not chosen_path.exists():
        alt_path = BRIEFS_DIR / str(chosen.get("file_name") or "")
        chosen_path = alt_path if alt_path.exists() else chosen_path

    selected_ids = [str(x) for x in (chosen.get("selected_record_ids") or []) if str(x)]
    selected_records = [records_by_id.get(rid, {}) for rid in selected_ids]
    missing_records = sum(1 for rid in selected_ids if rid not in records_by_id)
    with rc:
        with st.container(border=True):
            st.caption(
                f"{chosen.get('brief_code') or chosen.get('file_name')}  |  "
                f"{chosen.get('week_range') or '-'}  |  "
                f"{chosen.get('record_count')} records"
            )
            chosen_text = ""
            if chosen_path.exists():
                chosen_text = chosen_path.read_text(encoding="utf-8")
                _render_brief_collapsible(chosen_text, record_lookup=records_by_id)
                st.download_button(
                    "Download saved brief (.md)",
                    data=chosen_text.encode("utf-8"),
                    file_name=str(chosen.get("file_name") or chosen_path.name),
                    mime="text/markdown",
                    key=f"wb_saved_download_{idx}_{chosen_path.name}",
                )

                delete_key = f"wb_saved_delete_confirm_{idx}_{chosen_path.name}"
                confirm_delete = st.checkbox("Confirm delete selected brief", value=False, key=delete_key)
                if st.button(
                    "Delete selected brief",
                    type="secondary",
                    disabled=not confirm_delete,
                    key=f"wb_saved_delete_btn_{idx}_{chosen_path.name}",
                ):
                    deleted, msg = _delete_saved_brief(
                        str(chosen.get("file_name") or chosen_path.name),
                        str(chosen_path),
                    )
                    if deleted:
                        st.session_state["wb_saved_selected_file"] = ""
                        st.success(msg)
                        st.rerun()
                    else:
                        st.warning(msg)
            else:
                st.warning("Saved brief markdown file was not found on disk.")
            if missing_records:
                st.caption(f"{missing_records} selected record(s) are missing from current records.jsonl.")

    with st.expander("Included records", expanded=False):
        included_rows = []
        for rid in selected_ids:
            rec = records_by_id.get(str(rid), {})
            themes = [str(x).strip() for x in (rec.get("macro_themes_detected") or []) if str(x).strip()]
            included_rows.append(
                {
                    "record_id": str(rid),
                    "title": str(rec.get("title") or "(record missing)"),
                    "priority": str(rec.get("priority") or "-"),
                    "micro_theme": " | ".join(themes) if themes else "-",
                    "source_type": str(rec.get("source_type") or "-"),
                }
            )
        st.dataframe(pd.DataFrame(included_rows), width='stretch', hide_index=True)

    valid_selected_records = [
        rec
        for rec in selected_records
        if isinstance(rec, dict) and rec and str(rec.get("record_id") or "").strip()
    ]
    regen_week_range = _publish_week_range_from_records(
        valid_selected_records,
        fallback_range=str(chosen.get("week_range") or "Last 30 days"),
    )

    with st.expander("Regenerate brief", expanded=False):
        r1, r2 = st.columns(2)
        with r1:
            regen_provider = st.selectbox(
                "AI provider",
                ["gemini", "claude", "chatgpt"],
                index=0,
                key=f"wb_saved_provider_{idx}",
            )
        with r2:
            regen_web_check = st.checkbox(
                "Web coherence check (planned feature)",
                value=False,
                disabled=True,
                key=f"wb_saved_web_check_{idx}",
            )
            st.caption("Currently disabled.")
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
                web_check_enabled=False,
            )
            if ok:
                current_file = str(chosen.get("file_name") or "")
                regen_text = st.session_state.get("wb_saved_regen_text") or ""
                regen_usage = st.session_state.get("wb_saved_regen_usage") or {}
                regen_ids = st.session_state.get("wb_saved_regen_selected_ids") or selected_ids
                if regen_text and current_file:
                    path = _save_regenerated_brief(
                        current_file,
                        regen_text,
                        regen_week_range,
                        list(regen_ids),
                        regen_usage,
                    )
                    st.session_state["wb_saved_regen_compare_base_file"] = current_file
                    st.session_state["wb_saved_regen_compare_new_file"] = path.name
                    st.session_state["wb_saved_regen_compare_before_text"] = str(chosen_text or "")
                    st.session_state["wb_saved_regen_compare_after_text"] = regen_text
                    st.session_state["wb_saved_regen_compare_usage"] = regen_usage
                    st.session_state["wb_saved_selected_file"] = path.name
                    st.rerun()
                else:
                    st.warning("Regeneration succeeded but no brief text was returned.")

    current_file = str(chosen.get("file_name") or "")
    compare_base_file = str(st.session_state.get("wb_saved_regen_compare_base_file") or "")
    compare_new_file = str(st.session_state.get("wb_saved_regen_compare_new_file") or "")
    compare_before_text = str(st.session_state.get("wb_saved_regen_compare_before_text") or "")
    compare_after_text = str(st.session_state.get("wb_saved_regen_compare_after_text") or "")
    compare_usage = st.session_state.get("wb_saved_regen_compare_usage") or {}
    if compare_after_text and current_file and current_file in {compare_base_file, compare_new_file}:
        diff, added, removed = _diff_text(compare_before_text, compare_after_text)
        with st.expander(f"Before vs After (auto-saved as `{compare_new_file or 'new version'}`)", expanded=True):
            st.caption(f"Compared `{compare_base_file or 'previous'}` to `{compare_new_file or 'new'}` | Added {added} | Removed {removed}")
            st.code(diff or "No line-level changes.", language="diff")
            st.caption(
                f"Model: {compare_usage.get('model', 'unknown')} | "
                f"prompt={compare_usage.get('prompt_tokens', '?')} "
                f"output={compare_usage.get('output_tokens', '?')} "
                f"total={compare_usage.get('total_tokens', '?')} | "
                f"attempts={compare_usage.get('attempts', 1)} | "
                f"validation_err={compare_usage.get('validation_errors_final', 0)}"
            )
            regen_download_text = _to_saved_collapsible_markdown(compare_after_text)
            st.download_button(
                "Download regenerated .md",
                data=regen_download_text.encode("utf-8"),
                file_name=str(compare_new_file or _next_regenerated_brief_path(current_file).name),
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
default_record_from = today - timedelta(days=7)
default_record_to = today
default_publish_from = today - timedelta(days=7)
default_publish_to = max([today, *publish_dates]) if publish_dates else today


def _reset_brief_filters() -> None:
    st.session_state["wb_hide_shared"] = True
    st.session_state["wb_basis"] = "Upload date"
    st.session_state["wb_basis_prev"] = "Upload date"
    st.session_state["wb_date_range"] = (default_record_from, default_record_to)
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
    st.session_state.pop("wb_selected_ids_manual", None)


if st.session_state.pop("wb_clear_filters_requested", False):
    _reset_brief_filters()

# One-time reset to avoid stale filter carry-over hiding fresh records.
if not st.session_state.get("_brief_filter_defaults_v6_applied", False):
    _reset_brief_filters()
    st.session_state["_brief_filter_defaults_v6_applied"] = True

# Ensure hide-shared starts enabled by default for existing sessions.
if not st.session_state.get("_brief_hide_shared_default_v1_applied", False):
    st.session_state["wb_hide_shared"] = True
    st.session_state["_brief_hide_shared_default_v1_applied"] = True

tab_build, tab_saved = st.tabs(["Generate Brief", "Saved Briefs"])
with tab_saved:
    _render_saved_brief_browser(records_by_id)

with tab_build:
    st.subheader("Selected records")
    hide_already_shared = bool(st.session_state.get("wb_hide_shared", True))

    include_excluded = False
    region_filter: List[str] = []
    topic_filter: List[str] = []
    filter_search = ""
    quick_region = "All Regions"
    quick_topic = "All Topics"
    provider = "gemini"
    web_check_enabled = False

    basis_options = ["Upload date", "Publish date"]
    basis_label = str(st.session_state.get("wb_basis") or "Upload date")
    if basis_label not in basis_options:
        basis_label = "Upload date"
        st.session_state["wb_basis"] = basis_label
    date_basis_field = "created_at" if basis_label == "Upload date" else "publish_date"

    basis_default_from = default_record_from if date_basis_field == "created_at" else default_publish_from
    basis_default_to = default_record_to if date_basis_field == "created_at" else default_publish_to

    if str(st.session_state.get("wb_basis_prev") or "") != basis_label:
        st.session_state["wb_date_range"] = (basis_default_from, basis_default_to)
        st.session_state["wb_basis_prev"] = basis_label

    current_range = st.session_state.get("wb_date_range", (basis_default_from, basis_default_to))
    if isinstance(current_range, tuple):
        if len(current_range) == 2:
            filter_date_from, filter_date_to = current_range
        elif len(current_range) == 1:
            filter_date_from = filter_date_to = current_range[0]
        else:
            filter_date_from = basis_default_from
            filter_date_to = basis_default_to
    else:
        filter_date_from = filter_date_to = current_range
    if filter_date_from > filter_date_to:
        filter_date_from, filter_date_to = filter_date_to, filter_date_from

    st.session_state["wb_date_from"] = filter_date_from
    st.session_state["wb_date_to"] = filter_date_to
    week_range = f"{filter_date_from} to {filter_date_to} ({basis_label})"
    
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

    with st.container():
        quick_region_options = ["All Regions"] + region_options
        quick_topic_options = ["All Topics"] + topic_options
        q1, q2, q3, q4, q5 = st.columns([2.0, 1.3, 1.3, 1.2, 1.6])
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
            basis_label = st.selectbox(
                "Date basis",
                basis_options,
                key="wb_basis",
                label_visibility="collapsed",
            )
            date_basis_field = "created_at" if basis_label == "Upload date" else "publish_date"
            st.session_state["wb_basis_prev"] = basis_label
        with q5:
            date_range = st.date_input(
                "Date range",
                value=(basis_default_from, basis_default_to),
                key="wb_date_range",
                label_visibility="collapsed",
            )
            # Handle incomplete date range selection
            if isinstance(date_range, tuple):
                if len(date_range) == 2:
                    filter_date_from, filter_date_to = date_range
                elif len(date_range) == 1:
                    st.warning("⚠️ Please select both start and end dates for the range.")
                    filter_date_from = filter_date_to = date_range[0]
                else:
                    filter_date_from = basis_default_from
                    filter_date_to = basis_default_to
            else:
                filter_date_from = filter_date_to = date_range
            if filter_date_from > filter_date_to:
                filter_date_from, filter_date_to = filter_date_to, filter_date_from
            st.session_state["wb_date_from"] = filter_date_from
            st.session_state["wb_date_to"] = filter_date_to
        hide_already_shared = st.checkbox(
            "Hide records already included in saved briefs",
            value=True,
            key="wb_hide_shared",
        )

    if quick_region != "All Regions" and not region_filter:
        region_filter = [quick_region]
    if quick_topic != "All Topics" and not topic_filter:
        topic_filter = [quick_topic]

    candidates = [r for r in candidates if normalize_review_status(r.get("review_status")) == "Approved"]
    if region_filter:
        region_set = set(region_filter)
        candidates = [r for r in candidates if region_set & set(r.get("regions_relevant_to_apex_mobility") or [])]
    if topic_filter:
        topic_set = set(topic_filter)
        candidates = [r for r in candidates if topic_set & set(r.get("topics") or [])]
    if filter_search.strip():
        candidates = [r for r in candidates if _matches_filter_search(r, filter_search)]

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
    candidate_ids = [str(r.get("record_id") or "") for r in candidates if str(r.get("record_id") or "")]
    candidate_set = set(candidate_ids)
    stored_ids_raw = st.session_state.get("wb_selected_ids_manual")
    if isinstance(stored_ids_raw, list):
        selected_seed = {str(x) for x in stored_ids_raw if str(x)} & candidate_set
    else:
        selected_seed = default_set & candidate_set

    for r in candidates:
        rid = str(r.get("record_id") or "")
        if not rid:
            continue
        selection_rows.append(
            {
                "Include": rid in selected_seed,
                "record_id": rid,
                "title": str(r.get("title") or "Untitled"),
                "source": str(r.get("source_type") or "-"),
                "priority": str(r.get("priority") or "-"),
                "confidence": str(r.get("confidence") or "-"),
                "in_brief": "Yes" if bool(r.get("_already_shared_bool")) else "No",
            }
        )

    with st.expander("See included records", expanded=False):
        a1, a2 = st.columns(2)
        with a1:
            if st.button("Select all", key="wb_select_all_rows", use_container_width=True):
                selected_seed = set(candidate_ids)
        with a2:
            if st.button("Deselect all", key="wb_deselect_all_rows", use_container_width=True):
                selected_seed = set()

        selection_df = pd.DataFrame(selection_rows)
        if not selection_df.empty:
            selection_df["Include"] = selection_df["record_id"].astype(str).isin(selected_seed)
        edited_df = st.data_editor(
            selection_df,
            width='stretch',
            hide_index=True,
            disabled=["record_id", "title", "source", "priority", "confidence", "in_brief"],
            column_config={"Include": st.column_config.CheckboxColumn(required=True)},
            key="weekly_selection_editor",
        )
    selected_ids = edited_df.loc[edited_df["Include"], "record_id"].astype(str).tolist() if not edited_df.empty else []
    st.session_state["wb_selected_ids_manual"] = list(selected_ids)
    selected_set = set(selected_ids)
    selected_records = [r for r in candidates if str(r.get("record_id")) in selected_set]
    brief_week_range = _publish_week_range_from_records(selected_records, fallback_range=week_range)

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

    generate_clicked = st.button("Generate AI Brief", type="primary", disabled=not selected_records)

    if generate_clicked:
        generated = _synthesize_and_store(
            state_prefix="weekly_ai_brief",
            selected_records=selected_records,
            selected_ids=selected_ids,
            week_range=brief_week_range,
            provider=provider,
            web_check_enabled=web_check_enabled,
        )
        if generated:
            try:
                auto_path = _save_brief(
                    str(st.session_state.get("weekly_ai_brief_text") or ""),
                    str(st.session_state.get("weekly_ai_brief_week_range") or brief_week_range),
                    list(st.session_state.get("weekly_ai_brief_selected_ids") or selected_ids),
                    st.session_state.get("weekly_ai_brief_usage") or {},
                )
                st.session_state["weekly_ai_brief_last_autosave_path"] = str(auto_path)
                st.success(f"Auto-saved: {auto_path}")
            except Exception as exc:
                st.error(f"Generated, but auto-save failed: {exc}")

    saved_text = st.session_state.get("weekly_ai_brief_text")
    saved_usage = st.session_state.get("weekly_ai_brief_usage", {}) if saved_text else {}
    saved_week_range = (
        st.session_state.get("weekly_ai_brief_week_range", brief_week_range) if saved_text else brief_week_range
    )
    saved_ids = st.session_state.get("weekly_ai_brief_selected_ids", selected_ids) if saved_text else selected_ids
    quick_preview_text = _build_quick_preview_text(selected_records)

    with st.expander("Deterministic Preview", expanded=False):
        st.caption(f"Quick preview for {week_range}")
        st.markdown(quick_preview_text)

    st.subheader("AI Brief")
    if saved_text:
        auto_saved_path = str(st.session_state.get("weekly_ai_brief_last_autosave_path") or "").strip()
        if auto_saved_path:
            st.caption(f"Auto-saved to `{auto_saved_path}`")
        _render_brief_collapsible(saved_text, record_lookup=records_by_id)
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
            if st.button("Save another copy", type="secondary"):
                path = _save_brief(saved_text, saved_week_range, list(saved_ids), saved_usage)
                st.success(f"Saved: {path}")
        with a2:
            download_text = _to_saved_collapsible_markdown(saved_text)
            st.download_button(
                "Download brief",
                data=download_text.encode("utf-8"),
                file_name=f"weekly_brief_{saved_week_range.replace(' ', '_')}.md",
                mime="text/markdown",
            )
        with st.expander("Copy / Export (raw text)", expanded=False):
            st.text_area("Copy-friendly version", value=saved_text, height=280)
    else:
        st.info("Generate the AI brief to compare it with the deterministic preview.")
