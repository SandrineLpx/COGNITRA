# CHANGELOG

Milestone-level project history (curated summary). Detailed logs: `Docs/ITERATION_LOG.md` (clean) and `Docs/ITERATION_LOG_FULL.md` (full historical, not fully mirrored here).

## 2026-02-21 - Alignment & Documentation Pass

- Rewrote README for GitHub sharing (project overview, pipeline diagram, setup instructions, architecture summary)
- Added UX concept prototype link (Lovable mockup)
- Replaced "weekly brief" wording with "executive brief" across codebase
- Added anonymization note for Apex Mobility in technical report
- Fixed 4 failing tests (time-sensitive dates, Bloomberg date override logic)
- Moved prompt snapshot tests to `scripts/one_off/` (brittle, not CI-suitable)
- Cleaned up stale filenames in CHANGELOG
- Backfilled CHANGELOG with milestone history

## 2026-02-19 - UX Flow Upgrade

Full UX rework across all pages, no schema break:
- **Ingest**: Nine-stage pipeline stepper, saved record snapshot, consolidated diagnostics, improved failure UX, dedupe override controls
- **Review**: Queue-centric filter model (default last 7 days), compact card queue, tabbed detail panel (Brief, Evidence, Fields, Advanced), deterministic diagnostics explaining every score
- **Brief**: Checkbox-based record selection, coverage counters, saved brief browser with version comparison, hide-already-briefed toggle
- **Insights**: Executive snapshot tiles (WoW momentum), drilldown views by theme/region/company, underlying record traceability
- **Admin**: Quality run actions, schema diagnostics, macro theme rules viewer, isolated danger zone

## 2026-02-17 - Region Architecture & Documentation Consolidation

- Two-tier region model: `DISPLAY_REGIONS` (broad buckets) + `FOOTPRINT_REGIONS` (country-level granularity), driven by `data/new_country_mapping.csv`
- Expanded country-to-footprint mappings (~90 countries), added Japan as standalone footprint region
- Consolidated agent instructions into single `AGENTS.md`; removed duplicate spec files
- Embedded topic tagging guidance and competitor list directly into extraction prompt
- Added `pyproject.toml`, `requirements.txt`, standardized repo hygiene

## 2026-02-16 - Deterministic Scoring & Macro Themes

- Deterministic priority boosting (`_boost_priority`) with Apex Mobility-specific criteria
- Deterministic confidence scoring (`_compute_confidence`) from observable signals
- Macro-theme detection engine (`_detect_macro_themes`) with keyword/company/topic/region pattern matching
- Publisher header date parsing (Bloomberg, Reuters, S&P) with override diagnostics
- Source-grounded `mentions_our_company` detection
- Meta-based model routing: noise classification routes high-noise docs directly to Flash

## 2026-02-14 - Analytics & Quality

- Trend analysis dashboards: topic momentum, company mentions, priority distribution over time
- API quota tracker with per-model usage display
- Priority classification rules added to extraction prompt
- Quality monitoring pipeline (`scripts/run_quality.py`) with R1-R5 and B1-B5 KPIs

## 2026-02-13 - Extraction Pipeline Hardening

- Deterministic text cleanup and chunking (`src/text_clean_chunk.py`)
- Chunked extraction with per-chunk repair and cross-chunk merge
- Two-pass model strategy: Flash-Lite (cost-efficient) with Flash fallback on failure
- LLM-synthesized executive brief generation from approved records
- Bulk PDF ingest with progress tracking
- Simplified review model: Pending/Approved with deterministic auto-approve at ingest

## 2026-02-12 - Core System

- End-to-end extraction pipeline: PDF upload, Gemini structured JSON extraction, postprocessing, validation, JSONL storage
- Duplicate detection and story-level deduplication with publisher ranking
- Executive briefing module with candidate selection and email generation
- Comprehensive test suite (25+ scenarios)
- Secrets management, Gemini API wiring, schema hardening

## 2026-02-11 - Foundation

- Initial extraction pipeline (`src/model_router.py`)
- Two-layer geography processing (`src/postprocess.py`)
- Schema validation (`src/schema_validate.py`)
- Centralized constants (`src/constants.py`)
