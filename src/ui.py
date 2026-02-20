from __future__ import annotations

from contextlib import contextmanager
from html import escape
from pathlib import Path
from typing import Dict, Iterator, Optional

import streamlit as st

from src.quota_tracker import get_usage, reset_date

_WORKFLOW_ORDER = ["Ingest", "Review", "Brief", "Insights"]
_BADGE_CLASS = {
    "info": "cg-badge-info",
    "success": "cg-badge-success",
    "warning": "cg-badge-warning",
    "danger": "cg-badge-danger",
}


def _inject_css() -> None:
    st.markdown(
        """
<style>
:root {
  --cg-app-bg: #F5F7FA;
  --cg-card-bg: #FFFFFF;
  --cg-sidebar-bg: #111827;
  --cg-text-primary: #0F172A;
  --cg-text-secondary: #64748B;
  --cg-border: #E5E7EB;
  --cg-accent: #2563EB;
  --cg-success: #16A34A;
  --cg-warning: #D97706;
  --cg-danger: #DC2626;
}

.stApp {
  background: var(--cg-app-bg);
  color: var(--cg-text-primary);
}

.main .block-container {
  max-width: 100%;
  padding-top: 1rem;
  padding-bottom: 1.25rem;
}

[data-testid="stSidebar"] {
  background: var(--cg-sidebar-bg);
  border-right: 1px solid rgba(255, 255, 255, 0.08);
}

[data-testid="stSidebar"] * {
  color: #E5E7EB;
}

[data-testid="stSidebar"] [data-testid="stExpander"] details {
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.02);
  overflow: hidden;
}

[data-testid="stSidebar"] [data-testid="stExpander"] summary {
  background: rgba(255, 255, 255, 0.06) !important;
  color: #E5E7EB !important;
}

[data-testid="stSidebar"] [data-testid="stExpander"] summary:hover {
  background: rgba(255, 255, 255, 0.1) !important;
}

[data-testid="stSidebar"] [data-testid="stExpander"] summary p,
[data-testid="stSidebar"] [data-testid="stExpander"] summary span {
  color: #E5E7EB !important;
}

[data-testid="stSidebar"] [data-testid="stExpander"] summary svg {
  color: #E5E7EB !important;
  fill: #E5E7EB !important;
}

[data-testid="stSidebar"] hr {
  border-color: rgba(255, 255, 255, 0.16);
}

.cg-page-title {
  margin: 0;
  font-size: 2rem;
  line-height: 1.2;
  font-weight: 700;
  color: var(--cg-text-primary);
}

.cg-page-subtitle {
  margin-top: 0.35rem;
  margin-bottom: 0.75rem;
  font-size: 0.9rem;
  color: var(--cg-text-secondary);
}

.cg-divider {
  border-top: 1px solid var(--cg-border);
  margin: 0.4rem 0 1rem 0;
}

.cg-workflow {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: nowrap;
  gap: 0.6rem;
  margin-bottom: 0.75rem;
  width: 100%;
}

.cg-step-item {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-width: 6.5rem;
}

.cg-step-label {
  color: #94A3B8;
  color: var(--cg-text-secondary);
  font-size: 0.82rem;
  font-weight: 500;
  letter-spacing: 0.01em;
  line-height: 1.2;
  white-space: nowrap;
}

.cg-step-item.active .cg-step-label {
  color: var(--cg-accent);
  font-weight: 700;
}

.cg-step-dot {
  width: 0.4rem;
  height: 0.4rem;
  border-radius: 50%;
  margin-top: 0.24rem;
  opacity: 0;
  background: transparent;
}

.cg-step-item.active .cg-step-dot {
  opacity: 1;
  background: var(--cg-accent);
}

.cg-step-connector {
  width: 2rem;
  border-top: 1px solid #D1D5DB;
  flex: 0 0 auto;
}

.cg-card-title {
  margin: 0;
  font-size: 1.02rem;
  font-weight: 600;
  color: var(--cg-text-primary);
}

.cg-card-help {
  margin-top: 0.2rem;
  margin-bottom: 0.7rem;
  font-size: 0.85rem;
  color: var(--cg-text-secondary);
}

.cg-kpi-card {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 3px 8px rgba(15, 23, 42, 0.05);
  padding: 0.75rem 0.85rem;
  min-height: 86px;
  margin-bottom: 0.6rem;
}

.cg-kpi-label {
  font-size: 0.75rem;
  color: #475569;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  margin-bottom: 0.2rem;
  font-weight: 600;
}

.cg-kpi-value {
  font-size: 1.75rem;
  font-weight: 700;
  color: #1e293b;
  line-height: 1.2;
}

.cg-kpi-caption {
  font-size: 0.78rem;
  color: #64748b;
  margin-top: 0.2rem;
}

.stVerticalBlockBorderWrapper,
[data-testid="stVerticalBlockBorderWrapper"] {
  border: 1px solid #E2E8F0 !important;
  border-radius: 8px !important;
  background: var(--cg-card-bg) !important;
  box-shadow: 0 3px 8px rgba(15, 23, 42, 0.05) !important;
}

.stMetric,
[data-testid="stMetric"] {
  border: 1px solid #E2E8F0;
  border-radius: 8px;
  padding: 0.45rem 0.65rem;
  background: #FFFFFF;
}

[data-testid="stMetricLabel"] {
  color: var(--cg-text-secondary);
  font-weight: 600;
}

[data-testid="stMetricValue"] {
  color: #1E293B;
  font-weight: 600;
}

.stButton > button[kind="primary"] {
  background: var(--cg-accent);
  border-color: var(--cg-accent);
}

.stButton > button[kind="primary"]:hover {
  background: #1D4ED8;
  border-color: #1D4ED8;
}

[data-testid="stTabs"] [role="tablist"] button {
  border-radius: 10px;
}

[data-testid="stMarkdownContainer"] h3,
.stSubheader {
  font-family: inherit;
  letter-spacing: normal;
  font-variant: normal;
  font-weight: 600;
  color: var(--cg-text-primary);
}

.cg-badge {
  display: inline-block;
  border-radius: 999px;
  padding: 0.1rem 0.5rem;
  font-size: 0.76rem;
  font-weight: 600;
  border: 1px solid transparent;
}

.cg-badge-info {
  background: #DBEAFE;
  color: #1D4ED8;
  border-color: #BFDBFE;
}

.cg-badge-success {
  background: #DCFCE7;
  color: #166534;
  border-color: #BBF7D0;
}

.cg-badge-warning {
  background: #FEF3C7;
  color: #92400E;
  border-color: #FDE68A;
}

.cg-badge-danger {
  background: #FEE2E2;
  color: #991B1B;
  border-color: #FECACA;
}

.cg-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 2px;
}

.cg-brand-name {
  font-size: 0.9rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  line-height: 1.1;
}

.cg-brand-tagline {
  margin-top: 0;
  margin-bottom: 0.1rem;
  font-size: 0.75rem;
  color: #94A3B8;
  line-height: 1.15;
}

.cg-sidebar-divider {
  border-top: 1px solid rgba(255, 255, 255, 0.16);
  margin: 0.35rem 0 0.3rem 0;
}

.cg-util-label {
  font-size: 0.8rem;
  color: #CBD5E1;
  margin-top: 0.35rem;
  margin-bottom: 0.2rem;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def render_workflow_bar(active_step: str) -> None:
    active = str(active_step or "").strip().lower()
    parts = ['<div class="cg-workflow">']
    for idx, step in enumerate(_WORKFLOW_ORDER, start=1):
        cls = "cg-step-item active" if step.lower() == active else "cg-step-item"
        label = escape(step)
        parts.append(f'<span class="{cls}"><span class="cg-step-label">{label}</span><span class="cg-step-dot"></span></span>')
        if idx < len(_WORKFLOW_ORDER):
            parts.append('<span class="cg-step-connector"></span>')
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def render_page_header(title: str, subtitle: Optional[str] = None, active_step: Optional[str] = None) -> None:
    st.markdown(f'<h1 class="cg-page-title">{title}</h1>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="cg-page-subtitle">{subtitle}</div>', unsafe_allow_html=True)
    st.markdown('<div class="cg-divider"></div>', unsafe_allow_html=True)


def _render_sidebar_brand() -> None:
    logo_path = Path("assets/logo/cognitra-logo.png")
    icon_path = Path("assets/logo/cognitra-icon.png")
    if logo_path.exists():
        st.sidebar.image(str(logo_path), width=165)
    elif icon_path.exists():
        st.sidebar.image(str(icon_path), width=40)
        st.sidebar.markdown("### COGNITRA")
    else:
        st.sidebar.markdown("### COGNITRA")
    st.sidebar.caption("Automotive competitive intelligence")
    st.sidebar.divider()


def _render_override_items(overrides: Dict[str, int]) -> None:
    if not overrides:
        st.caption("No overrides recorded.")
        return
    top = sorted(overrides.items(), key=lambda x: int(x[1] or 0), reverse=True)[:6]
    for name, cnt in top:
        st.caption(f"- {str(name)}: {int(cnt)}")


def _render_sidebar_nav() -> None:
    with st.sidebar:
        st.page_link("Home.py", label="Home")
        st.page_link("pages/01_Ingest.py", label="Ingest")
        st.page_link("pages/02_Review.py", label="Review")
        st.page_link("pages/03_Brief.py", label="Brief")
        st.page_link("pages/04_Insights.py", label="Insights")
        st.page_link("pages/Admin.py", label="Settings", icon=":material/settings:")


def render_sidebar_utilities(
    model_label: Optional[str] = None,
    overrides: Optional[Dict[str, int]] = None,
) -> None:
    usage = get_usage()
    with st.sidebar:
        st.markdown('<div class="cg-sidebar-divider"></div>', unsafe_allow_html=True)
        st.markdown('<div class="cg-util-label">Utilities</div>', unsafe_allow_html=True)
        with st.expander("API quota", expanded=False):
            st.caption(f"Tracking date: {reset_date()}")
            if not usage:
                st.caption("No calls recorded yet.")
            for model_name, info in usage.items():
                short = str(model_name).replace("gemini-", "")
                used = int(info.get("used", 0))
                quota = int(info.get("quota", 0))
                rem = int(info.get("remaining", 0))
                pct = used / max(quota, 1)
                st.progress(min(pct, 1.0), text=f"{short}: {used}/{quota} ({rem} left)")
        with st.expander("Model (routing)", expanded=False):
            st.caption(str(model_label or "auto"))
        with st.expander("Overrides applied", expanded=False):
            _render_override_items(overrides or {})


def init_page(active_step: Optional[str] = None) -> None:
    _inject_css()
    _render_sidebar_brand()
    _render_sidebar_nav()
    st.session_state["_ui_active_step"] = str(active_step or "")


@contextmanager
def card(title: str, help_text: Optional[str] = None) -> Iterator[None]:
    with st.container(border=True):
        st.markdown(f'<div class="cg-card-title">{title}</div>', unsafe_allow_html=True)
        if help_text:
            st.markdown(f'<div class="cg-card-help">{help_text}</div>', unsafe_allow_html=True)
        yield


def status_badge(label: str, kind: str = "info", help_text: Optional[str] = None) -> None:
    cls = _BADGE_CLASS.get(kind, _BADGE_CLASS["info"])
    tip_attr = f' title="{escape(str(help_text), quote=True)}"' if help_text else ""
    safe_label = escape(str(label))
    st.markdown(f'<span class="cg-badge {cls}"{tip_attr}>{safe_label}</span>', unsafe_allow_html=True)


def kpi_card(
    label: str,
    value: object,
    caption: Optional[str] = None,
    help_text: Optional[str] = None,
) -> None:
    safe_label = escape(str(label))
    safe_value = escape(str(value))
    tip_attr = f' title="{escape(str(help_text), quote=True)}"' if help_text else ""
    parts = [
        f'<div class="cg-kpi-card"{tip_attr}>',
        f'<div class="cg-kpi-label">{safe_label}</div>',
        f'<div class="cg-kpi-value">{safe_value}</div>',
    ]
    if caption:
        parts.append(f'<div class="cg-kpi-caption">{escape(str(caption))}</div>')
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def section_divider() -> None:
    st.markdown('<div class="cg-divider"></div>', unsafe_allow_html=True)
