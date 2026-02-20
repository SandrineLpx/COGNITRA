# COGNITRA — Automotive Competitive Intelligence Platform

## Run locally
1) Create a virtual environment
2) Install dependencies:
   - **Production**: `pip install -r requirements.txt` (or `pip install .`)
   - **Development** (includes pytest): `pip install .[dev]`
   - Core packages: `streamlit`, `pandas`, `matplotlib`, `altair`, `pymupdf`, `pdfplumber`, `google-genai`
   - Test runner (included in `requirements.txt` and `.[dev]`): `pytest`
3) Run:
   ```bash
   streamlit run Home.py
   ```

## Model routing
- `src/model_router.py` is wired for Gemini via `google-genai` with structured JSON output.
- Set `GEMINI_API_KEY` in your environment before running.
- Claude and ChatGPT providers are placeholders and not yet implemented.

## Data
- Records: `data/records.jsonl` (JSON Lines)
- PDFs saved to: `data/pdfs/`
- Quality logs: `data/quality/` (record_qc.jsonl, brief_qc.jsonl, quality_runs.jsonl, quality_report.xlsx)

## Ingest behavior
- Chunking is automatic based on cleaned document structure (`chunks_count`).
- The app surfaces chunk-count guidance and estimated API-call impact in the Ingest UI.

## Workflow navigation
- `01 Ingest` -> `02 Review` -> `03 Brief` -> `04 Insights` -> `Admin`
- Record governance (approve/disapprove/edit/re-ingest/delete) is centralized in `02 Review`.
- `03 Brief` is executive-focused output generation (no record status editing).
- `Admin` contains developer/analyst utilities and maintenance actions.

## Region mapping

Region values are defined in `data/new_country_mapping.csv` and implemented in Python constants:

| What | File | Variable |
|---|---|---|
| Valid region values | `src/constants.py` | `FOOTPRINT_REGIONS` / `DISPLAY_REGIONS` |
| Country → footprint | `src/postprocess.py` | `COUNTRY_TO_FOOTPRINT` |
| LLM string aliases | `src/postprocess.py` | `REGION_ALIASES` |

**Individual Apex Mobility countries** (appear by name in both fields): Czech Republic, France, Germany, Italy, Morocco, Mexico, Portugal, Russia, Spain, Sweden, United Kingdom, United States, Thailand, India, China, Taiwan, Japan, South Korea.

**Sub-regional buckets**: West Europe, Central Europe, East Europe, Africa, Middle East, NAFTA, ASEAN, Indian Subcontinent, Andean, Mercosul, Central America, Oceania, Rest of World.

**Generic catch-alls** (from broad LLM aliases): Europe, South America, South Asia.

### Updating the mapping

1. Edit `data/new_country_mapping.csv` — this is the design document and source of truth.
2. Apply the changes to the Python constants:
   - New **country row** → add entry to `COUNTRY_TO_FOOTPRINT` in `src/postprocess.py`
   - New **footprint_region row** → add value to `FOOTPRINT_REGIONS` in `src/constants.py`
   - New **alias row** → add entry to `REGION_ALIASES` in `src/postprocess.py`
3. If existing records use the old value, run the migration script:
   ```bash
   python scripts/migrate_region_overhaul.py          # dry run
   python scripts/migrate_region_overhaul.py --apply  # apply
   ```
4. Run tests to verify: `python -m pytest -q`

**Drift detection**: the Home page warns automatically if the CSV and Python constants diverge. No manual check needed — just open the app after editing the CSV.

## Quality monitoring
- Run: `python scripts/run_quality.py` (checks latest brief + its records)
- Checks: evidence grounding, geo determinism, macro theme rules, confidence alignment, uncertainty compliance, overreach detection
- KPIs: R1–R5 (records) + B1–B5 (briefs), weighted scores 0–100
- Outputs: append-only JSONL logs + Excel report in `data/quality/`
- Standards: `References/Quality/` (QUALITY_CHECKLIST.md, QUALITY_KPIS.md, BRIEF_GENERATION_STANDARDS.md)

## Tests
- `pytest` is required for tests.
- Canonical command:
  - `python -m pytest -q`

## Date Extraction Semantics
- Publisher-specific PDF header timestamps are used as source-of-truth dates when available (Bloomberg, S&P, Reuters, etc.).
- Store `publish_date` as date-only (`YYYY-MM-DD`) with no timezone conversion.
- This avoids PST/UTC rollover flip-flops (for example, Feb 1 PST vs Feb 2 UTC).
- December 31 dates found in PDF headers are automatically filtered out (fiscal year-end dates, not publication dates).
