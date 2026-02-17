import streamlit as st

from src.ui_helpers import workflow_ribbon

st.set_page_config(page_title="Auto Intelligence (MVP)", layout="wide")

st.title("Automotive Market Intelligence (MVP)")
workflow_ribbon(1)
st.caption("Workflow: Ingest -> Review & Approve -> Weekly Executive Brief -> Insights")

st.markdown(
    """
Use the left sidebar to navigate pages.
- **Ingest**: upload PDF (single or bulk) or paste text, extract with model routing, save record
- **Review & Approve**: filter queue, inspect details, edit JSON, approve/disapprove, exclude from brief
- **Weekly Executive Brief**: select approved records, generate deterministic/AI brief, compare saved briefs
- **Insights**: optional analytics and trend monitoring
- **Advanced / Admin**: exports and maintenance utilities
"""
)
