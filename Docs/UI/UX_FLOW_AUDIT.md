# UX Flow Audit - Cognitra Streamlit Pages

Date: 2026-02-19

## 01 Ingest
Current flow:
- User uploads PDF or pastes text.
- Preview/cleaning and chunk diagnostics are shown.
- User runs extraction pipeline.
- Record is postprocessed, validated, deduped, and saved.
- Rendered intelligence brief is displayed.

Top friction points:
- Pipeline stage was implicit; failure location was unclear.
- Failures did not clearly separate extraction vs validation vs dedupe.
- Duplicate handling was binary and not explicit about override intent.
- Important computed metadata was not summarized immediately.
- Advanced diagnostics were spread out and inconsistent.

Improved flow implemented:
- Explicit pipeline stepper with completed/failed state.
- Failure surface includes repair attempt and fallback provider status.
- Duplicate behavior defaults to block, with explicit advanced override.
- Saved record snapshot shows computed fields and region split.
- Advanced expander consolidates context preview, JSON, and logs.

## 02 Review & Approve
Current flow:
- User filters queue, selects record, edits JSON, approves/disapproves.
- Evidence and insights are viewable.
- Iteration/re-ingest operations are available.

Top friction points:
- Queue filters lacked record-date/publish-date governance defaults.
- No first-class "already briefed" visibility/filter.
- Detail panel mixed lifecycle and diagnostics without clear IA.
- Deterministic outputs lacked plain-language "why" explanations.
- Queue lacked compact status-rich cards for rapid triage.

Improved flow implemented:
- Queue-centric layout with left queue cards and right detail workspace.
- Added record-date (default last 7 days) + optional publish-date filters.
- Added status/priority/region/macro-theme filters and hide-briefed default ON.
- Added top operational summary row (pending/high/low-conf/auto-eligible/macro-week).
- Record detail tabs: Summary, Evidence & Insights, Deterministic Diagnostics, Advanced.
- Approve/Disapprove remain independent from JSON editor validity.
- Added "Needs edit (save draft)" lifecycle path.

## 03 Weekly Executive Brief
Current flow:
- User set days window and selected candidate records.
- AI brief could be generated and saved.
- Limited saved-brief review was available.

Top friction points:
- Selection controls were narrower than review workflow.
- Inclusion decisions were not workspace-like (checkbox row-by-row).
- Coverage visibility by priority/region/theme was limited.
- Saved brief view centered on latest brief only.
- Email draft section diluted flagship brief workflow.

Improved flow implemented:
- Selection workspace expanded with review-like filters and hide-briefed control.
- Added record-date range and optional publish-date range filters.
- Added status/priority/region/macro-theme filters.
- Candidate selection now supports include/exclude per REC row via checkbox grid.
- Added brief coverage counters for selected set (priority/region/theme coverage).
- Removed executive email draft UI.
- Added Saved Brief Browser (list + open brief + included REC list + latest diff support).

## 04 Insights
Current flow:
- User explored charts (volume, heatmap, momentum, companies, quality).
- Drilldown to exact records required manual cross-check.

Top friction points:
- No executive snapshot for "what changed this week" at first glance.
- Theme/region/company pathways were not unified into record drilldowns.
- Quality and confidence signals were present but not surfaced as quick health cues.
- Trend views were chart-heavy without immediate REC linkage path.
- Discoverability of record-level evidence from trends was weak.

Improved flow implemented:
- Added Executive Snapshot tiles (momentum, footprint density, stress/strategy signals, confidence/quality health).
- Added dedicated drilldown tabs by theme, region, and company.
- Each drilldown tab outputs underlying REC table for traceability.
- Existing charts retained while adding a direct path from trend dimensions to records.

## 08 Admin
Current flow:
- Admin focused mainly on dedupe export and destructive reset.

Top friction points:
- Missing operational controls for quality and diagnostics.
- Provider availability status was not explicit.
- Schema guardrail visibility was limited.
- Macro theme rules were not centrally viewable.
- Admin information architecture mixed utility and destructive actions.

Improved flow implemented:
- Added provider availability block (Gemini enabled, others explicitly not available).
- Added token/model usage stats panel.
- Added quality run controls and quality report export.
- Added schema/version diagnostics with guardrail mismatch visibility.
- Added read-only macro theme rules viewer.
- Kept destructive operations isolated in danger zone.
