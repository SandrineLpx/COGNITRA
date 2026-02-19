import streamlit as st

from src import ui
from src.postprocess import validate_csv_consistency
from src.ui_helpers import enforce_navigation_lock

st.set_page_config(page_title="Cognitra", page_icon="assets/logo/cognitra-icon.png", layout="wide")
enforce_navigation_lock("home")
ui.init_page(active_step=None)

ui.render_page_header(
    "Cognitra",
    subtitle="Automotive market intelligence workspace",
    active_step=None,
)
ui.render_sidebar_utilities(model_label="auto")

with ui.card("Workflow", "Use the left sidebar to navigate pages."):
    st.markdown(
        """
- **01 Ingest**: upload PDF (single or bulk) or paste text, extract with model routing, save record
- **02 Review**: filter queue, inspect details, edit JSON, approve/disapprove, exclude from brief
- **03 Brief**: select approved records, generate deterministic/AI brief, compare saved briefs
- **04 Insights**: optional analytics and trend monitoring
- **Admin**: exports and maintenance utilities
"""
    )

_csv_warnings = validate_csv_consistency()
if _csv_warnings:
    with ui.card("Region Mapping Drift", "Detected between CSV mapping and Python constants."):
        with st.expander(f"{len(_csv_warnings)} issue(s)", expanded=False):
            st.caption(
                "The CSV `data/new_country_mapping.csv` and the Python constants in "
                "`src/postprocess.py` / `src/constants.py` are out of sync. "
                "Edit the Python constants to match the CSV, then re-run tests."
            )
            for warning in _csv_warnings:
                st.markdown(f"- {warning}")
