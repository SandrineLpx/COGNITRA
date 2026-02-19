import hashlib
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from src import ui
from src.constants import MACRO_THEME_RULES, REQUIRED_KEYS
from src.dedupe import dedupe_records
from src.model_router import record_response_schema
from src.quota_tracker import get_usage, reset_date
from src.quality import (
    QUALITY_REPORT_XLSX,
    QUALITY_RUNS_LOG,
    _read_jsonl,
    run_quality_pipeline,
    run_record_only_qc,
)
from src.storage import RECORDS_PATH, load_records, overwrite_records
from src.ui_helpers import enforce_navigation_lock

st.set_page_config(page_title="Cognitra", page_icon="assets/logo/cognitra-icon.png", layout="wide")
enforce_navigation_lock("admin")
ui.init_page(active_step=None)
ui.render_page_header(
    "Admin",
    subtitle="Power-user operations and diagnostics",
    active_step=None,
)
ui.render_sidebar_utilities(model_label="gemini")

with ui.card("Provider Availability"):
    st.selectbox(
        "LLM provider",
        options=["Gemini (Enabled)", "Claude (Not available yet)", "ChatGPT (Not available yet)"],
        index=0,
        disabled=True,
    )
    st.caption("Provider switching is currently unavailable in this app.")

with ui.card("Token / Model Usage"):
    st.caption(f"Quota tracking date: {reset_date()} (resets midnight PT)")
    usage = get_usage()
    if usage:
        for model_name, info in usage.items():
            used = int(info.get("used", 0))
            quota = int(info.get("quota", 0))
            remaining = int(info.get("remaining", 0))
            pct = used / max(quota, 1)
            short = model_name.replace("gemini-", "")
            st.progress(min(pct, 1.0), text=f"{short}: {used}/{quota} used ({remaining} left)")
    else:
        st.caption("No model usage recorded yet.")

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

with ui.card("Schema / Version Diagnostics"):
    schema = record_response_schema()
    schema_props = set((schema.get("properties") or {}).keys())
    required = set(REQUIRED_KEYS)
    missing_in_schema = sorted(required - schema_props)
    schema_fingerprint = hashlib.sha256(json.dumps(schema, sort_keys=True).encode("utf-8")).hexdigest()[:12]

    s1, s2, s3 = st.columns(3)
    s1.metric("Required keys", len(required))
    s2.metric("Schema properties", len(schema_props))
    s3.metric("Schema fingerprint", schema_fingerprint)
    if missing_in_schema:
        st.warning(f"{len(missing_in_schema)} required keys missing from schema properties.")
        st.caption(", ".join(missing_in_schema))
    else:
        st.caption("Schema guardrail check passed: all required keys are represented.")

    with st.expander("Schema properties", expanded=False):
        st.json(sorted(schema_props))

with ui.card("Macro Theme Rules (Read-Only)"):
    macro_rows = []
    for rule in MACRO_THEME_RULES:
        signals = rule.get("signals") or {}
        macro_rows.append(
            {
                "name": str(rule.get("name") or ""),
                "min_groups": int(rule.get("min_groups") or 0),
                "premium_gate": bool(rule.get("premium_company_gate")),
                "region_requirements": ", ".join(str(x) for x in (rule.get("region_requirements") or [])),
                "signal_groups": ", ".join(sorted(signals.keys())),
                "rollup": str(rule.get("rollup") or ""),
            }
        )
    st.dataframe(pd.DataFrame(macro_rows), width='stretch', hide_index=True)

with ui.card("Data Maintenance"):
    records = load_records()
    if records:
        canonical, dups = dedupe_records(records)
        m1, m2, m3 = st.columns(3)
        m1.metric("Total records", len(records))
        m2.metric("Canonical", len(canonical))
        m3.metric("Duplicates", len(dups))
        export_df = pd.json_normalize(canonical)
        st.download_button(
            "Download canonical records CSV",
            data=export_df.to_csv(index=False).encode("utf-8"),
            file_name="intelligence_records_canonical.csv",
            mime="text/csv",
        )
    else:
        st.caption("No records found.")

    with st.expander("Danger Zone", expanded=False):
        st.caption("Warning: this permanently clears stored records and cannot be undone.")
        confirm_clear = st.checkbox("I understand this will permanently clear all records", value=False)
        if st.button("Clear all records (demo reset)", type="secondary", disabled=not confirm_clear):
            overwrite_records([])
            st.success("Cleared.")
            st.caption(f"Data file: {RECORDS_PATH}")
