# CHANGELOG

## 2026-02-19 - UX Flow Upgrade (No Schema Break)

### `pages/01_Ingest.py`
- Added explicit pipeline stepper/status covering: Upload -> extraction/cleaning -> context pack -> LLM -> postprocess -> validation -> dedupe -> save.
- Added post-run "Saved Record Snapshot" with key metadata: title, source, publish date, record ID, priority/confidence, review status, regions vs footprint regions.
- Consolidated advanced diagnostics under one `Advanced` expander with:
  - bounded context/cleaned text preview
  - raw JSON output
  - routing + validation logs
- Improved failure UX:
  - clear stage failure context
  - repair attempt status
  - fallback provider status
  - summarized provider errors
- Dedupe UX update:
  - default behavior blocks likely duplicates
  - advanced override checkbox allows intentional separate save
  - duplicate messaging includes likely REC match details

Acceptance checks:
- Given a normal ingest run, when pipeline completes, then user sees stepper as complete and key computed metadata immediately.
- Given extraction/validation failure, when run stops, then user sees failed stage + repair/fallback status + error summary.
- Given a likely duplicate, when advanced override is OFF, then save is blocked with REC match context.
- Given a likely duplicate, when advanced override is ON, then pipeline can continue and save intentionally.

### `pages/02_Review_Approve.py`
- Added queue-centric filter model with defaults for execution workflow:
  - record added date range (default last 7 days)
  - optional publish date range
  - status, priority, footprint region, macro theme, search
  - hide already briefed toggle (default ON)
- Added first-class "in brief" status via saved brief metadata mapping.
- Added summary KPI row:
  - Pending
  - High priority pending
  - Low confidence pending
  - Auto-approve eligible
  - Macro themes detected this week
- Reworked queue panel as left-side compact cards (title, source/date, priority/confidence, status, footprint, in-brief tag).
- Reworked detail panel with tabs:
  - Summary
  - Evidence & Insights
  - Deterministic Diagnostics
  - Advanced
- Added deterministic diagnostics explanations:
  - priority explanation sentence
  - confidence signal drivers
  - macro theme group/gate diagnostics table
- Decision controls remain independent of JSON editor validity:
  - Save changes (validated JSON)
  - Needs edit (save draft as Pending)
  - Approve
  - Disapprove

Acceptance checks:
- Given records briefed previously, when hide already briefed is ON, then those records are excluded from queue.
- Given JSON editor has invalid JSON, when Approve/Disapprove is clicked, then lifecycle action still works.
- Given a selected record, when opening Deterministic Diagnostics tab, then user sees why priority/confidence/themes were produced.
- Given last-7-day default filter, when page loads, then queue focuses on current operational workload.

### `pages/03_Weekly_Executive_Brief.py`
- Expanded selection workspace to align with review-style controls:
  - days back + basis (`publish_date` or `created_at`)
  - record added range + optional publish range
  - status, priority, footprint region, macro theme
  - hide already briefed toggle
- Kept missing-date exclusion messaging for chosen date basis.
- Upgraded record selection to checkbox workspace via data editor (include/exclude per REC row).
- Added brief coverage counters:
  - selected count
  - selected by priority
  - regions covered
  - macro themes covered
- Removed executive email draft UI.
- Added Saved Brief Browser:
  - list-style summary (created_at, week_range, record_count, key themes, file)
  - open selected brief markdown
  - show included REC list
  - compare latest vs previous when applicable
- Continued using saved brief index/sidecar metadata as source of truth for "already briefed" mapping.

Acceptance checks:
- Given time basis switch, when user selects `created_at`, then time-window filtering uses record added date.
- Given hide already briefed is ON, when candidate list is rendered, then briefed records are hidden by default.
- Given selected records, when coverage counters render, then counts reflect current include/exclude choices.
- Given saved briefs exist, when selecting one in browser, then markdown and included REC list are visible.

### `pages/04_Insights.py`
- Added top-level Executive Snapshot tiles:
  - macro theme momentum (WoW)
  - footprint region signal density
  - OEM stress/strategy signals (7d)
  - confidence/quality health (low-confidence rate + QC high issues)
- Added deeper drilldown views with underlying REC lists:
  - By Theme
  - By Region
  - By Company
- Kept existing analytics (histogram, heatmap, momentum, quality charts) and added REC-oriented path to inspect underlying records quickly.

Acceptance checks:
- Given filtered dataset, when opening Executive Snapshot, then user gets a quick week-over-week state summary.
- Given a selected theme/region/company in drilldown tabs, then underlying REC rows are listed for traceability.

### `pages/08_Admin.py`
- Reworked Admin into power-user operations:
  - provider availability (Gemini enabled; others labeled Not available yet and disabled)
  - token/model usage stats
  - quality run actions (full + record-only) and report download
  - schema/version diagnostics (required keys vs schema properties + fingerprint)
  - macro theme rules read-only viewer
  - retained advanced maintenance + isolated danger zone

Acceptance checks:
- Given non-Gemini providers are not enabled, when viewing provider config, then options are shown as not available.
- Given quality pipeline is run from Admin, when complete, then run metadata and report download path are surfaced.
- Given schema diagnostics section, when loaded, then guardrail mismatch visibility is explicit.
