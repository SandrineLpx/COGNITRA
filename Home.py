import streamlit as st

st.set_page_config(page_title="Auto Intelligence (MVP)", layout="wide")

st.title("Automotive Market Intelligence (MVP)")
st.caption("Multi-page app: Ingest → Inbox → Record → Dashboard → Weekly Brief → Review Brief → Documents → Admin")

st.markdown("""
Use the left sidebar to navigate pages.
- **Ingest**: upload PDF (single or bulk) or paste text, extract with meta-based model routing, save record
- **Inbox**: filter/browse records with inline approve, batch actions, search
- **Record**: view/edit one record, confidence detail breakdown, review status controls
- **Dashboard**: KPI metrics, trend charts (topic momentum, company mentions, priority & confidence distribution)
- **Weekly Brief**: curate approved items, generate deterministic or AI-powered executive brief
- **Review Brief**: inspect latest saved brief, compare to previous, approve/exclude source records
- **Documents**: original source library with filters, evidence previews, and link fallback
- **Admin**: export CSV/JSONL, bulk deduplication, clear demo data
""")
