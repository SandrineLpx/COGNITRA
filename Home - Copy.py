from pathlib import Path
from pathlib import Path
import streamlit as st

from src import ui
from src.postprocess import validate_csv_consistency
from src.ui_helpers import enforce_navigation_lock, load_records_cached

st.set_page_config(page_title="Cognitra", page_icon="assets/logo/cognitra-icon.png", layout="wide")
enforce_navigation_lock("home")
ui.init_page(active_step=None)

ui.render_page_header(
    "Cognitra",
    subtitle="Automotive market intelligence workspace",
    active_step=None,
)


def _path_signature(path: Path) -> tuple[bool, int, int]:
    try:
        stat = path.stat()
    except OSError:
        return (False, 0, 0)
    return (True, int(stat.st_size), int(stat.st_mtime_ns))


@st.cache_data(show_spinner=False, ttl=300)
def _cached_csv_warnings(_csv_sig: tuple[bool, int, int]) -> list[str]:
    return validate_csv_consistency()


records = load_records_cached()

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

_csv_warnings = _cached_csv_warnings(_path_signature(Path("data/new_country_mapping.csv")))
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
