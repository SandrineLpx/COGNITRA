from datetime import datetime
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
# 1. Problem hook
# ---------------------------------------------------------------------------

st.markdown(
    "<p style='font-size:1.05rem; color:#64748B; margin-bottom:1.5rem;'>"
    "Automotive intelligence teams subscribe to Bloomberg, S&P Global, and Automotive News "
    "— then miss signals because volume exceeds processing capacity. "
    "Cognitra converts unstructured PDFs into evidence-backed intelligence records and "
    "executive-ready briefs, automatically."
    "</p>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# 2. Live KPI row
# ---------------------------------------------------------------------------

k1, k2, k3, k4 = st.columns(4)
with k1:
    ui.kpi_card("Intelligence Records", len(canonical), caption="Canonical, non-duplicate")
with k2:
    ui.kpi_card("Awaiting Review", pending_count, caption="Pending analyst approval")
with k3:
    ui.kpi_card("High-Priority Signals", high_pri_count, caption="Surfaced for executive briefing")
with k4:
    ui.kpi_card("Last Ingest", last_ingest, caption="Most recent article processed")

# ---------------------------------------------------------------------------
# 3. Workflow guide
# ---------------------------------------------------------------------------

_STEPS = [
    ("Ingest", "Upload PDFs, extract structured records via Gemini LLM"),
    ("Review", "Validate, edit, and approve records before briefing"),
    ("Brief", "AI-synthesized weekly executive briefs in one click"),
    ("Insights", "Track topic momentum, company signals, and quality trends"),
    ("Admin", "Export data, run quality checks, manage maintenance"),
]

with ui.card("How it works", "Use the left sidebar to navigate to any step."):
    cols = st.columns(len(_STEPS))
    for col, (step, desc) in zip(cols, _STEPS):
        with col:
            st.markdown(f"**{step}**")
            st.caption(desc)

# ---------------------------------------------------------------------------
# 4. Design philosophy
# ---------------------------------------------------------------------------

_PILLARS = [
    (
        "One LLM call per document",
        "Extraction only. Deduplication, priority classification, confidence scoring, "
        "and macro theme detection are deterministic Python — auditable and cost-predictable.",
    ),
    (
        "Evidence-backed records",
        "Every record carries 2–4 verifiable bullets traceable to source text. "
        "No summaries, no hallucinations dressed up as facts.",
    ),
    (
        "Human-in-the-loop gate",
        "No record reaches an executive brief without analyst review. "
        "Auto-approve heuristics handle clean extractions; weak ones stay Pending.",
    ),
]

with ui.card("Minimal AI — by design"):
    p1, p2, p3 = st.columns(3)
    for col, (title, desc) in zip([p1, p2, p3], _PILLARS):
        with col:
            st.markdown(f"**{title}**")
            st.caption(desc)

# ---------------------------------------------------------------------------
# 5. CSV drift warning (operational — keep at bottom)
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
