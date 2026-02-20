import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from src import ui
from src.constants import FOOTPRINT_REGIONS
from src.dedupe import dedupe_records
from src.quality import (
    QUALITY_REPORT_XLSX,
    QUALITY_RUNS_LOG,
    _read_jsonl,
    run_quality_pipeline,
    run_record_only_qc,
)
from src.storage import RECORDS_PATH, overwrite_records
from src.ui_helpers import clear_brief_history_cache, clear_records_cache, enforce_navigation_lock, load_records_cached


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        return None


def _to_overview_table(df_rows: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "record_id",
        "title",
        "source_type",
        "publish_date",
        "created_at",
        "priority",
        "confidence",
        "review_status",
    ]
    keep = [c for c in cols if c in df_rows.columns]
    if not keep:
        return pd.DataFrame()
    return df_rows[keep].copy()

st.set_page_config(page_title="Cognitra", page_icon="assets/logo/cognitra-icon.png", layout="wide")
enforce_navigation_lock("admin")
ui.init_page(active_step=None)
ui.render_page_header(
    "Admin",
    subtitle="Power-user operations and diagnostics",
    active_step=None,
)
ui.render_sidebar_utilities(model_label="gemini")

tab_quality, tab_maintenance, tab_download, tab_danger = st.tabs(
    ["Quality", "Maintenance", "Download records", "Danger Zone"]
)

with tab_quality:
    with ui.card("Quality Operations"):
        q1, q2 = st.columns(2)
        with q1:
            if st.button("Run full quality checks (latest brief)", type="primary"):
                with st.spinner("Running quality pipeline..."):
                    result = run_quality_pipeline(use_latest_brief=True)
                st.success(
                    f"Completed run {result.get('run_id')} | target={result.get('target_record_count')} | "
                    f"brief={result.get('brief_id') or '(none)'}"
                )
        with q2:
            if st.button("Run record-only quality checks"):
                with st.spinner("Running record-only QC..."):
                    result = run_record_only_qc()
                st.success(f"Completed run {result.get('run_id')} | target={result.get('target_record_count')}")

        quality_runs = _read_jsonl(QUALITY_RUNS_LOG)
        if quality_runs:
            latest_run = quality_runs[-1]
            st.caption(
                f"Latest run: {latest_run.get('run_id')} | "
                f"created_at={latest_run.get('created_at')} | "
                f"overall={latest_run.get('weighted_overall_score')}"
            )
        if QUALITY_REPORT_XLSX.exists():
            st.download_button(
                "Download quality report (.xlsx)",
                data=QUALITY_REPORT_XLSX.read_bytes(),
                file_name=QUALITY_REPORT_XLSX.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            st.caption("Quality report file not found yet. Run quality checks first.")

with tab_maintenance:
    with ui.card("Data Maintenance"):
        records = load_records_cached()
        if records:
            canonical, dups = dedupe_records(records)
            m1, m2, m3 = st.columns(3)
            with m1:
                ui.kpi_card("Total records", len(records))
            with m2:
                ui.kpi_card("Canonical", len(canonical))
            with m3:
                ui.kpi_card("Duplicates", len(dups))
            export_df = pd.json_normalize(canonical)
            st.download_button(
                "Download canonical records CSV",
                data=export_df.to_csv(index=False).encode("utf-8"),
                file_name="intelligence_records_canonical.csv",
                mime="text/csv",
            )
        else:
            st.caption("No records found.")

        with st.expander("Region normalization", expanded=False):
            _REGION_FIX_MAP = {k.lower(): v for k, v in {
                "US": "United States", "U.S.": "United States", "USA": "United States",
                "UK": "United Kingdom", "U.K.": "United Kingdom",
                "Western Europe": "West Europe", "Eastern Europe": "East Europe",
                "Latin America": "South America", "LATAM": "South America",
                "EU": "Europe", "E.U.": "Europe", "Europe (including Russia)": "Europe",
                "Asia": "South Asia", "Asia-Pacific": "South Asia", "APAC": "South Asia",
                "Asia Pacific": "South Asia", "North America": "NAFTA",
                "Korea": "South Korea",
            }.items()}
            _FOOTPRINT_SET = set(FOOTPRINT_REGIONS)

            stale_counts: dict[str, int] = {}
            for rec in records:
                for field in ("regions_relevant_to_apex_mobility", "regions_mentioned"):
                    for val in (rec.get(field) or []):
                        s = str(val).strip()
                        if s and s not in _FOOTPRINT_SET and s.lower() in _REGION_FIX_MAP:
                            stale_counts[s] = stale_counts.get(s, 0) + 1

            if stale_counts:
                st.caption(f"Found {sum(stale_counts.values())} stale region value(s) across records:")
                for val, cnt in sorted(stale_counts.items(), key=lambda x: -x[1]):
                    st.caption(f"  `{val}` → `{_REGION_FIX_MAP[val.lower()]}` ({cnt}x)")
                if st.button("Normalize stale regions", type="secondary"):
                    touched = 0
                    for rec in records:
                        changed = False
                        for field in ("regions_relevant_to_apex_mobility", "regions_mentioned"):
                            vals = rec.get(field)
                            if not isinstance(vals, list):
                                continue
                            new_vals = []
                            for v in vals:
                                s = str(v).strip()
                                mapped = _REGION_FIX_MAP.get(s.lower(), s)
                                new_vals.append(mapped)
                                if mapped != s:
                                    changed = True
                            seen: set[str] = set()
                            deduped: list[str] = []
                            for v in new_vals:
                                if v not in seen:
                                    seen.add(v)
                                    deduped.append(v)
                            rec[field] = deduped
                        if changed:
                            touched += 1
                    if touched:
                        overwrite_records(records)
                        clear_records_cache()
                        st.success(f"Normalized regions in {touched} record(s).")
                        st.rerun()
                    else:
                        st.info("No changes needed.")
            else:
                st.caption("All region values are already normalized.")

        with st.expander("Purge deleted briefs", expanded=False):
            BRIEFS_DIR = Path("data") / "briefs"
            BRIEF_INDEX = BRIEFS_DIR / "index.jsonl"

            # Scan index for entries whose .md file no longer exists
            index_rows = []
            if BRIEF_INDEX.exists():
                for line in BRIEF_INDEX.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        index_rows.append(json.loads(line))
                    except Exception:
                        continue

            orphaned_index: list[dict] = []
            kept_index: list[dict] = []
            for row in index_rows:
                file_name = Path(str(row.get("file") or "")).name
                md_path = BRIEFS_DIR / file_name if file_name else None
                if not md_path or not md_path.exists():
                    orphaned_index.append(row)
                else:
                    kept_index.append(row)

            # Scan for orphaned .meta.json sidecars (no matching .md)
            orphaned_sidecars: list[Path] = []
            if BRIEFS_DIR.exists():
                for sidecar in BRIEFS_DIR.glob("brief_*.meta.json"):
                    md_path = sidecar.with_name(sidecar.name.replace(".meta.json", ".md"))
                    if not md_path.exists():
                        orphaned_sidecars.append(sidecar)

            if orphaned_index or orphaned_sidecars:
                st.caption(
                    f"Found {len(orphaned_index)} orphaned index entry(ies) and "
                    f"{len(orphaned_sidecars)} orphaned sidecar file(s)."
                )
                for row in orphaned_index:
                    st.caption(f"  Index: `{Path(str(row.get('file') or '')).name}` ({row.get('created_at', '-')})")
                for sc in orphaned_sidecars:
                    st.caption(f"  Sidecar: `{sc.name}`")
                if st.button("Purge deleted briefs", type="secondary"):
                    # Rewrite index keeping only entries with existing .md files
                    if BRIEF_INDEX.exists():
                        BRIEF_INDEX.write_text(
                            "\n".join(json.dumps(r, ensure_ascii=False) for r in kept_index) + ("\n" if kept_index else ""),
                            encoding="utf-8",
                        )
                    # Delete orphaned sidecars
                    for sc in orphaned_sidecars:
                        try:
                            sc.unlink()
                        except Exception:
                            pass
                    clear_brief_history_cache()
                    st.success(
                        f"Purged {len(orphaned_index)} index entry(ies) and "
                        f"{len(orphaned_sidecars)} sidecar file(s)."
                    )
                    st.rerun()
            else:
                st.caption("No orphaned brief entries found. Index is clean.")

with tab_download:
    with ui.card("Records Overview"):
        records = load_records_cached()
        if not records:
            st.caption("No records found.")
        else:
            overview_df = _to_overview_table(pd.json_normalize(records))
            if overview_df.empty:
                st.caption("No overview fields available.")
            else:
                st.dataframe(overview_df, width='stretch', hide_index=True)
                st.download_button(
                    "Download overview CSV",
                    data=overview_df.to_csv(index=False).encode("utf-8"),
                    file_name="insights_overview.csv",
                    mime="text/csv",
                )

with tab_danger:
    with ui.card("Danger Zone"):
        st.caption("Warning: this permanently clears stored records and cannot be undone.")
        st.caption("Demo helper: remove only records and briefs created today.")
        confirm_today = st.checkbox("I understand this removes only today's records/briefs", value=False)
        if st.button("Delete today's records and briefs (demo)", type="secondary", disabled=not confirm_today):
            today = date.today()

            records = load_records_cached()
            kept_records: list[dict] = []
            removed_records = 0
            removed_pdfs = 0
            for rec in records:
                rec_date = _parse_iso_date(rec.get("created_at"))
                if rec_date == today:
                    removed_records += 1
                    pdf_path = Path(str(rec.get("source_pdf_path") or "")).expanduser()
                    if pdf_path.is_file():
                        try:
                            pdf_path.unlink()
                            removed_pdfs += 1
                        except OSError:
                            pass
                    continue
                kept_records.append(rec)

            if removed_records:
                overwrite_records(kept_records)
                clear_records_cache()

            briefs_dir = Path("data") / "briefs"
            brief_index = briefs_dir / "index.jsonl"
            index_rows: list[dict] = []
            if brief_index.exists():
                for line in brief_index.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        index_rows.append(json.loads(line))
                    except Exception:
                        continue

            kept_index: list[dict] = []
            removed_briefs = 0
            removed_sidecars = 0
            for row in index_rows:
                row_date = _parse_iso_date(row.get("created_at"))
                if row_date == today:
                    removed_briefs += 1
                    file_name = Path(str(row.get("file") or "")).name
                    md_path = briefs_dir / file_name if file_name else None
                    if md_path and md_path.is_file():
                        try:
                            md_path.unlink()
                        except OSError:
                            pass
                    sidecar = md_path.with_suffix(".meta.json") if md_path else None
                    if sidecar and sidecar.is_file():
                        try:
                            sidecar.unlink()
                            removed_sidecars += 1
                        except OSError:
                            pass
                    continue
                kept_index.append(row)

            if brief_index.exists():
                brief_index.write_text(
                    "\n".join(json.dumps(r, ensure_ascii=False) for r in kept_index) + ("\n" if kept_index else ""),
                    encoding="utf-8",
                )
            clear_brief_history_cache()

            quality_dir = Path("data") / "quality"
            quality_files = [
                quality_dir / "record_qc.jsonl",
                quality_dir / "brief_qc.jsonl",
                quality_dir / "quality_runs.jsonl",
                quality_dir / "quality_report.xlsx",
            ]
            removed_quality = 0
            for qf in quality_files:
                if qf.is_file():
                    try:
                        qf.unlink()
                        removed_quality += 1
                    except OSError:
                        pass

            dup_index = Path("data") / "duplicates.jsonl"
            removed_dup_index = 0
            if dup_index.is_file():
                try:
                    dup_index.unlink()
                    removed_dup_index = 1
                except OSError:
                    removed_dup_index = 0

            st.success(
                "Deleted today's data. "
                f"Records: {removed_records}, PDFs: {removed_pdfs}, "
                f"Briefs: {removed_briefs}, Sidecars: {removed_sidecars}, "
                f"Quality files: {removed_quality}, Duplicate index: {removed_dup_index}."
            )
            st.rerun()

        confirm_clear = st.checkbox("I understand this will permanently clear all records", value=False)
        if st.button("Clear all records (demo reset)", type="secondary", disabled=not confirm_clear):
            overwrite_records([])
            clear_records_cache()
            st.success("Cleared.")
            st.caption(f"Data file: {RECORDS_PATH}")
