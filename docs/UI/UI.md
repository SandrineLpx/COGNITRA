# UI Iteration Summary (Streamlit)

## Why this document exists
Refactoring and visual redesign took multiple iterations because Streamlit supports fast product UI, but has hard limits for pixel-perfect parity with React/Tailwind UI kits.

This document keeps the important history: what changed, what failed, what worked, and what should stay as a design contract.

## High-impact iterations completed

1. Global UI baseline and consistency
- Added shared UI rules and reusable helpers in `src/ui.py`.
- Standardized KPI visual treatment across pages using `ui.kpi_card(...)` in `src/ui.py:406`.
- Unified card spacing, borders, and hierarchy to reduce per-page CSS drift.

2. Navigation cleanup
- Removed numbered naming style (`01`, `02`, `03`, `04`) from page framing and sidebar labels.
- Removed top workflow strip usage from pages (renderer still exists in `src/ui.py`).

3. Ingest page rework (layout-only; pipeline logic preserved)
- Reordered sections to match analyst workflow: header, KPIs, input mode, status, recent uploads, advanced.
- Made paste-text title mandatory for cleaner downstream record context.
- Reduced upload dropzone footprint for better visual balance.

4. Review page decision-flow cleanup
- Reduced KPI row to pending, approved, total records.
- Standardized compact filters (search, priority, status, region).
- Simplified queue row metadata and replaced text action with eye icon entry.
- Changed status actions to a dropdown in detail view for single-point lifecycle update.

5. Brief page flow simplification
- Removed low-value instructional noise and generation settings clutter.
- Split Build and Saved Browser into tabbed workflow.
- Moved included-records table under `See included records` in `pages/03_Brief.py:1049`.
- Defaulted hide-already-included to ON in `pages/03_Brief.py:974`.
- Added regeneration versioning and superseding behavior for brief history continuity.

6. Insights page layout updates
- Added top chart block: records by topic, coverage by region, top companies by records in `pages/04_Insights.py:560`.
- Moved remaining visualizations to two collapsible groups:
- `Record insights` in `pages/04_Insights.py:679`.
- `Quality related` in `pages/04_Insights.py:895`.

## Additions from UX Flow Audit

1. Ingest flow lessons to retain
- Always expose pipeline stage and failure location (extraction vs validation vs dedupe).
- Keep duplicate handling explicit with default block and intentional override path.
- Surface computed metadata summary immediately after successful save.
- Keep diagnostics consolidated under one advanced section.

2. Review flow lessons to retain
- Keep governance defaults stable: short record-date window and hide-briefed ON by default.
- Keep queue first, detail second; do not mix lifecycle actions with deep diagnostics.
- Keep deterministic "why" signals visible in plain language, not only raw JSON fields.
- Preserve independent status decisioning even when JSON editor has issues.

3. Brief flow lessons to retain
- Keep selection workspace filterable like review (not a narrow one-off picker).
- Keep coverage counters visible for selected records (priority, region, theme).
- Keep saved brief browser as first-class workspace, not latest-only output.
- Avoid secondary UX (for example email draft panels) in main flagship workflow.

4. Insights flow lessons to retain
- Lead with executive snapshot before heavy drilldown charts.
- Keep direct traceability from trend views to underlying records.
- Keep quality signals visible but separated from narrative analytics.

5. Admin information architecture lessons to retain
- Keep provider availability explicit.
- Keep schema and guardrail diagnostics visible.
- Keep quality run controls and exports grouped together.
- Keep destructive tools isolated in a clear danger zone.

## Important problems encountered (and fixes)

1. Duplicate widget keys
- Error: `StreamlitDuplicateElementKey` (`ing_status_view_review`).
- Fix: enforce unique keys by render path and avoid duplicate control rendering.

2. Session state ownership conflicts
- Warning: widget default + direct `st.session_state` assignment on same key.
- Fix: use one owner pattern per widget key.

3. Filters hiding records unexpectedly
- Symptom: queue count did not match visible rows.
- Cause: stale filters persisted across reruns/sessions.
- Fix: deterministic one-time defaults and full clear reset.
- References: `pages/02_Review.py:652`, `pages/03_Brief.py:865`.

4. Design mismatch vs Lovable screenshots
- Cause: Streamlit native component DOM/chrome constraints.
- Result: close visual approximation is realistic; exact parity is not.

## What Streamlit does well here
- Fast iteration for enterprise workflows.
- Stable deterministic UI state with simple Python patterns.
- Reusable styling contract through `src/ui.py`.

## What Streamlit is not ideal for here
- Pixel-perfect design system parity (Tailwind/shadcn-level control).
- Deep custom uploader/table micro-interactions.
- Highly custom icon-only interaction patterns without compromises.

## Recommendation going forward
If exact design fidelity is the top requirement, move UI to React/Vite/TypeScript/Tailwind and keep this Python stack as backend/domain logic.

If speed and deterministic analyst workflow are the top requirement, stay on Streamlit and keep `src/ui.py` as the single UI contract.
