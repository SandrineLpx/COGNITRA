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
    "Because volume exceeds processing capacity."
    "</p>"
    "<p style='margin:0 0 0.25rem; font-size:0.9rem; color:#64748B;'>"
    "Cognitra turns documents into validated records — then synthesizes."
    "</p>"
    "<div class='cg-divider'></div>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# 2. Differentiator statement
# ---------------------------------------------------------------------------

st.markdown(
    "<p style='text-align:center; font-size:1.05rem; font-weight:600; "
    "color:#0F172A; margin:0.75rem 0 0.2rem;'>"
    "Not a summarization tool."
    "</p>"
    "<p style='text-align:center; font-size:1.05rem; font-weight:600; "
    "color:#0F172A; margin:0 0 1.1rem;'>"
    "A governed intelligence pipeline."
    "</p>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# 3. Start here CTA
# ---------------------------------------------------------------------------

st.markdown(
    "<p style='font-size:0.85rem; color:#64748B; margin:0 0 0.4rem;'>Start here:</p>",
    unsafe_allow_html=True,
)
b1, b2, b3, _ = st.columns([1, 1, 1, 3])
with b1:
    if st.button("Ingest a PDF", use_container_width=True):
        st.switch_page("pages/01_Ingest.py")
with b2:
    if st.button("Review queue", use_container_width=True):
        st.switch_page("pages/02_Review.py")
with b3:
    if st.button("Generate weekly brief", use_container_width=True):
        st.switch_page("pages/03_Brief.py")

# ---------------------------------------------------------------------------
# 4. Live metrics row
# ---------------------------------------------------------------------------

k1, k2, k3, k4 = st.columns(4)
with k1:
    ui.kpi_card("Validated Records", len(canonical), caption="Structured \u00b7 Scored \u00b7 Approved")
with k2:
    ui.kpi_card("Pending Governance", pending_count, caption="Human gate pending")
with k3:
    ui.kpi_card("Surfaced Signals", high_pri_count, caption="Elevated by rule-based scoring")
with k4:
    ui.kpi_card("Latest Structured Ingest", last_ingest, caption="Last document structured")

# ---------------------------------------------------------------------------
# 5. Architecture strip
# ---------------------------------------------------------------------------

st.markdown(
    "<p style='font-size:0.8rem; font-weight:600; color:#64748B; "
    "letter-spacing:0.06em; text-transform:uppercase; margin:1rem 0 0.25rem;'>"
    "How Cognitra Works (Controlled Pipeline)"
    "</p>",
    unsafe_allow_html=True,
)

_PIPELINE = [
    ("Extract", "Strict JSON schema — factual fields only"),
    ("Score", "Priority \u00b7 Confidence \u00b7 Macro-themes — deterministic rules"),
    ("Approve", "Analyst review — human gate before any synthesis"),
    ("Render", "From validated records only — never from raw PDFs"),
]

with ui.card("STRUCTURE BEFORE SYNTHESIS"):
    cols = st.columns(len(_PIPELINE))
    for col, (step, desc) in zip(cols, _PIPELINE):
        with col:
            st.markdown(f"**{step}**")
            st.caption(desc)

# ---------------------------------------------------------------------------
# 6. Controlled AI usage
# ---------------------------------------------------------------------------

with ui.card("Controlled AI Usage"):
    st.markdown(
        "- One model call per document\n"
        "- Deterministic postprocessing\n"
        "- No synthesis from raw PDFs\n"
        "- Human review before reporting"
    )
    st.markdown(
        "<p style='font-size:0.8rem; color:#64748B; margin-top:0.6rem;'>"
        "Cost-aware: one extraction call per document. Deterministic rendering thereafter."
        "</p>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# 7. Page footer
# ---------------------------------------------------------------------------

st.markdown(
    "<p style='text-align:center; font-size:0.8rem; color:#94A3B8; margin:1.5rem 0 0.5rem;'>"
    "Briefs are rendered from approved records — never from raw documents."
    "</p>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# 8. CSV drift warning (operational — keep at bottom)
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
