# Insights Top 3 Charts Revert Note

Date: 2026-02-20

Purpose: keep a rollback reference for the pre-interactive top-3 chart layout.

## Previous behavior (before interactivity)
- `Records by topic`: static horizontal bar chart with tooltip.
- `Coverage by region`: static donut chart + right-side text legend.
- `Top companies by records`: custom row layout using `st.progress` bars (not Altair).
- No click-based chart filters.
- No chart-driven drilldown table.

## Current interactive behavior (after update)
- Topic, region, and company charts now support click selection.
- Active chart filters are shown above charts.
- A `Clear chart filters` button resets chart selections.
- A drilldown table appears when one or more chart filters are active.
- Top companies chart is now an Altair bar chart (replaced `st.progress` rows).

## Code location
- File: `pages/04_Insights.py`
- Section marker: `# Requested top 3 charts`

## Quick rollback guidance
1. Replace the current `# Requested top 3 charts` section with the prior static implementation.
2. Remove chart-selection session keys:
- `ins_chart_topic_pick`
- `ins_chart_region_pick`
- `ins_chart_company_pick`
3. Remove helper function:
- `_extract_point_selection_value(...)`
4. Remove `Top chart drilldown records` expander block.

