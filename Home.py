from datetime import datetime
from pathlib import Path

import streamlit as st

import src.ui as ui
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


# HERO
st.markdown(
    "<h1 style='margin:0; font-size:2.2rem; font-weight:700; color:#0F172A; line-height:1.2;'>"
    "Most intelligence never reaches decision-makers."
    "</h1>"
    "<p style='margin:0.3rem 0 0.5rem; font-size:1.25rem; font-weight:400; color:#64748B;'>"
    "Because teams can’t process the volume."
    "</p>"
    "<p style='margin:0 0 0.25rem; font-size:0.9rem; color:#64748B;'>"
    "Cognitra turns documents into validated records — then synthesizes."
    "</p>"
    "<p style='margin:0.4rem 0 0; font-size:0.82rem; color:#94A3B8;'>"
    "Currently deployed for <strong style='color:#64748B;'>Apex Mobility</strong> "
    "(automotive closure systems) — designed to extend to any industry."
    "</p>",
    unsafe_allow_html=True,
)
st.markdown("<div style='height:0.95rem;'></div>", unsafe_allow_html=True)


# DIFFERENTIATION
st.markdown(
    "<p style='text-align:center; font-size:1.05rem; font-weight:600; color:#0F172A; margin:0;'>"
    "Not a summarization tool."
    "</p>"
    "<p style='text-align:center; font-size:1.05rem; font-weight:600; color:#0F172A; margin:0.12rem 0 0;'>"
    "A governed intelligence system."
    "</p>",
    unsafe_allow_html=True,
)
st.markdown("<div style='height:1.0rem;'></div>", unsafe_allow_html=True)


# PIPELINE
st.markdown(
    "<p style='font-size:0.8rem; font-weight:600; color:#64748B; "
    "letter-spacing:0.06em; text-transform:uppercase; margin:0 0 0.2rem;'>"
    "How Cognitra Works"
    "</p>",
    unsafe_allow_html=True,
)

_PIPELINE = [
    ("Extract", "Strict JSON schema - factual fields only"),
    ("Score", "Priority · Confidence · Macro-themes (deterministic)"),
    ("Approve", "Analyst review - human gate"),
    ("Render", "From approved records only - never from raw PDFs"),
]

with ui.card("Pipeline Overview"):
    cols = st.columns(len(_PIPELINE))
    for col, (step, desc) in zip(cols, _PIPELINE):
        with col:
            st.markdown(f"**{step}**")
            st.caption(desc)

st.markdown("<div style='height:0.9rem;'></div>", unsafe_allow_html=True)


# KPI (STATUS)
st.markdown(
    """
<style>
.home-kpi-muted .cg-kpi-card {
  background: #f8fafc !important;
  border: 1px solid #e2e8f0 !important;
}
.home-kpi-muted .cg-kpi-label {
  font-size: 0.72rem !important;
  color: #64748b !important;
  letter-spacing: 0.05em !important;
}
.home-kpi-muted .cg-kpi-value {
  font-weight: 600 !important;
  color: #1e293b !important;
}
</style>
""",
    unsafe_allow_html=True,
)
st.markdown("<div class='home-kpi-muted'>", unsafe_allow_html=True)

k1, k2, k3, k4 = st.columns(4)
with k1:
    ui.kpi_card("VALIDATED RECORDS", len(canonical), caption="Structured · Scored · Approved")
with k2:
    ui.kpi_card("PENDING GOVERNANCE", pending_count, caption="Human gate pending")
with k3:
    ui.kpi_card("SURFACED SIGNALS", high_pri_count, caption="Elevated by rule-based scoring")
with k4:
    ui.kpi_card("LATEST STRUCTURED INGEST", last_ingest, caption="Last document structured")

st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)


# CTA (PRIMARY START)
b1, b2, b3, _ = st.columns([1, 1, 1, 3])
with b1:
    if st.button("Ingest a PDF", type="primary", use_container_width=True):
        st.switch_page("pages/01_Ingest.py")
with b2:
    if st.button("Review queue", type="secondary", use_container_width=True):
        st.switch_page("pages/02_Review.py")
with b3:
    if st.button("Generate executive brief", type="secondary", use_container_width=True):
        st.switch_page("pages/03_Brief.py")


# DESIGN PRINCIPLES
st.markdown(
    "<p style='text-align:center; font-size:0.78rem; color:#94A3B8; margin:1.2rem 0 0.3rem; letter-spacing:0.03em;'>"
    "One model call per document · Deterministic scoring · Human review before reporting"
    "</p>",
    unsafe_allow_html=True,
)

# UX CONCEPT
st.markdown(
    "<p style='text-align:center; font-size:0.82rem; color:#64748B; margin:0.8rem 0 0.3rem;'>"
    "This Streamlit app is the working system. "
    "For the intended production UX, see the "
    "<a href='https://cognitra-mockup.lovable.app/' target='_blank' "
    "style='color:#3B82F6; text-decoration:none; font-weight:600;'>"
    "interactive prototype</a> (static mockup — not connected to live data)."
    "</p>",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# CSV drift warning (operational — keep at bottom)
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
