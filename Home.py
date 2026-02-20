from datetime import datetime
from pathlib import Path

import streamlit as st

from src import ui
from src.postprocess import validate_csv_consistency
from src.ui_helpers import enforce_navigation_lock, load_records_cached

st.set_page_config(page_title="Cognitra", page_icon="assets/logo/cognitra-icon.png", layout="wide")
enforce_navigation_lock("home")
ui.init_page(active_step=None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _path_signature(path: Path) -> tuple[bool, int, int]:
    try:
        stat = path.stat()
    except OSError:
        return (False, 0, 0)
    return (True, int(stat.st_size), int(stat.st_mtime_ns))


@st.cache_data(show_spinner=False, ttl=300)
def _cached_csv_warnings(_csv_sig: tuple[bool, int, int]) -> list[str]:
    return validate_csv_consistency()


def _format_last_ingest(records: list) -> str:
    """Return a human-readable date string for the most recent record."""
    candidates = [r.get("created_at", "") or "" for r in records]
    latest = max((c for c in candidates if c), default="")
    if not latest:
        return "—"
    try:
        dt = datetime.fromisoformat(latest[:10])
        return dt.strftime("%b %d")
    except ValueError:
        return latest[:10]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

records = load_records_cached()
canonical = [r for r in records if not r.get("is_duplicate")]
pending_count = sum(1 for r in canonical if r.get("review_status") == "Pending")
high_pri_count = sum(1 for r in canonical if r.get("priority") == "High")
last_ingest = _format_last_ingest(records)

# ---------------------------------------------------------------------------
# 1. Hero block
# ---------------------------------------------------------------------------

st.markdown(
    "<h1 style='margin:0; font-size:2.2rem; font-weight:700; color:#0F172A; line-height:1.2;'>"
    "Most intelligence is never shared."
    "</h1>"
    "<p style='margin:0.3rem 0 0.5rem; font-size:1.25rem; font-weight:400; color:#64748B;'>"
    "Because there's too much of it."
    "</p>"
    "<p style='margin:0 0 0.25rem; font-size:0.9rem; color:#64748B;'>"
    "Cognitra structures information into validated records before it allows synthesis."
    "</p>"
    "<div class='cg-divider'></div>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# 2. Differentiator statement
# ---------------------------------------------------------------------------

st.markdown(
    "<p style='text-align:center; font-size:0.95rem; font-style:italic; "
    "color:#64748B; margin:0.75rem 0 1.25rem;'>"
    "This is not a summarization tool. It is a controlled intelligence architecture."
    "</p>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# 3. Live metrics row
# ---------------------------------------------------------------------------

k1, k2, k3, k4 = st.columns(4)
with k1:
    ui.kpi_card("Validated Records", len(canonical), caption="Structured and approved")
with k2:
    ui.kpi_card("Pending Governance", pending_count, caption="Awaiting analyst sign-off")
with k3:
    ui.kpi_card("Surfaced Signals", high_pri_count, caption="Escalated by deterministic rules")
with k4:
    ui.kpi_card("Latest Structured Ingest", last_ingest, caption="Last document structured")

# ---------------------------------------------------------------------------
# 4. Architecture strip
# ---------------------------------------------------------------------------

_PIPELINE = [
    ("Extract", "Strict JSON schema — factual fields only"),
    ("Score", "Priority \u00b7 Confidence \u00b7 Macro-themes — deterministic rules"),
    ("Approve", "Analyst review — human gate before any synthesis"),
    ("Render", "From validated records only — never from raw PDFs"),
]

with ui.card("STRUCTURE BEFORE SYNTHESIS", "Use the left sidebar to navigate to any step."):
    cols = st.columns(len(_PIPELINE))
    for col, (step, desc) in zip(cols, _PIPELINE):
        with col:
            st.markdown(f"**{step}**")
            st.caption(desc)

# ---------------------------------------------------------------------------
# 5. Controlled AI usage
# ---------------------------------------------------------------------------

with ui.card("Controlled AI Usage"):
    st.markdown(
        "- One model call per document\n"
        "- Deterministic postprocessing\n"
        "- No synthesis from raw PDFs\n"
        "- Human review before reporting"
    )

# ---------------------------------------------------------------------------
# 6. CSV drift warning (operational — keep at bottom)
# ---------------------------------------------------------------------------

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
