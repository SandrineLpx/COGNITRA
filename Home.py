import streamlit as st

st.set_page_config(page_title="Auto Intelligence (MVP)", layout="wide")

st.title("Automotive Market Intelligence (MVP)")
st.caption("Multi-page app: Ingest → Inbox → Record → Dashboard → Export/Admin")

st.markdown("""
Use the left sidebar to navigate pages.
- **Ingest**: upload PDF or paste text, run pipeline, save record
- **Inbox**: filter and browse saved records
- **Record**: view/edit one record and update review status
- **Dashboard**: analytics over saved records
- **Export/Admin**: export CSV, clear demo data
""")
