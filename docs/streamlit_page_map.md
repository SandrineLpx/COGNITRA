# COGNITRA Streamlit Page Map

Generated: 2026-02-25

This document reflects the current sidebar navigation implemented in `src/ui.py`.

## Navigation Map

| Order | Sidebar Label | Route File | Purpose | Primary Modules |
|---|---|---|---|---|
| 0 | Home | `Home.py` | Landing page and workflow orientation | `src/ui_helpers`, `src/ui` |
| 1 | Ingest | `pages/01_Ingest.py` | PDF/text ingest, extraction pipeline, postprocess, validation, save | `src/pdf_extract`, `src/text_clean_chunk`, `src/model_router`, `src/postprocess`, `src/schema_validate`, `src/storage` |
| 2 | Review | `pages/02_Review.py` | Governance queue, filtering, record detail, JSON edit, approve/disapprove | `src/ui_helpers`, `src/storage`, `src/schema_validate`, `src/render_brief` |
| 3 | Brief | `pages/03_Brief.py` | Candidate selection, `Generate Brief`, `Generate Demo Brief`, saved brief browser | `src/briefing`, `src/ui_helpers`, `src/storage` |
| 4 | Insights | `pages/04_Insights.py` | Trend analytics and quality score views | `src/quality`, `src/dedupe`, `src/ui_helpers` |
| 5 | Settings | `pages/Admin.py` | Maintenance utilities, quality runs, cache controls, demo reset | `src/quality`, `src/storage`, `src/ui_helpers` |

## Notes

- Sidebar label is `Settings`, backed by `pages/Admin.py`.
- The app has six visible pages total: Home + five functional pages.
- Route declarations are in `src/ui.py` (`st.page_link(...)`).
