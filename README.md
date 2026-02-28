# COGNITRA — Automotive Market Intelligence Platform

A governed intelligence system that transforms automotive industry doucments (reports, articles) into structured, analyst-reviewed executive briefs for strategic decision-making.

Built for **Apex Mobility**, a closure systems supplier (door latches, strikers, handles, smart entry, cinch systems), COGNITRA ensures that market signals reach decision-makers with full provenance, deterministic scoring, and human oversight.

## How it works

COGNITRA follows a four-stage governed pipeline — no unreviewed AI output reaches executives.

```
  Extract            Score              Approve            Render
 ─────────        ──────────         ───────────       ──────────
 PDF / text  →    Priority ·    →    Analyst     →     Executive
 Gemini LLM       Confidence ·       review            briefs
 strict JSON      Macro-themes       gate              
                  (deterministic)
```

**UX concept prototype:** [cognitra-mockup.lovable.app](https://cognitra-mockup.lovable.app/) — interactive mockup of the intended production UI (static, not connected to live data).

1. **Extract** — Upload a PDF or paste text (OCR not supported at this stage). Gemini extracts structured intelligence into a strict JSON schema. One model call per document.
2. **Score** — Deterministic Python rules assign priority, confidence, and macro-theme tags. No LLM involved.
3. **Approve** — Analysts review, edit, and approve records through a governance queue. Low-confidence or incomplete records require human sign-off.
4. **Render** — Executive briefs are generated from approved records only, with full citation traceability (REC links). Weekly synthesis uses Gemini on approved JSON records, with one optional repair pass when validation flags issues.

## Pages

| Page | Purpose |
|---|---|
| **Home** | KPI dashboard — validated records, pending governance, surfaced signals, latest ingest |
| **Ingest** | PDF upload (single or bulk), URL download, paste-text mode. Nine-stage pipeline with live progress |
| **Review** | Analyst governance queue — filter, inspect, approve/disapprove records. Deterministic diagnostics explain every score |
| **Brief** | Generate and manage executive briefs for any time window. Compare versions, regenerate, download markdown |
| **Insights** | Analytics dashboards — topic signals, region coverage, company rankings, trend momentum, quality scores |
| **Settings (Admin)** | Maintenance utilities — quality checks, data export, demo state management, cache controls |

Detailed page map (routes + modules): [`docs/streamlit_page_map.md`](docs/streamlit_page_map.md)

## Setup

**Requirements:** Python >= 3.11

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
.venv\Scripts\activate           # Windows

# 2. Install dependencies
pip install -r requirements.txt          # production
pip install .[dev]                       # development (includes pytest)

# 3. Configure API key
#    Create .streamlit/secrets.toml with:
#    GEMINI_API_KEY = "your-key-here"

# 4. Run
streamlit run Home.py
```

### Core dependencies

`streamlit` · `pandas` · `matplotlib` · `altair` · `pymupdf` · `pdfplumber` · `google-genai`

## Data storage

All data is file-based (no database):

| Path | Contents |
|---|---|
| `data/records.jsonl` | Structured intelligence records (JSON Lines) |
| `data/canonical.jsonl` | Deduplicated canonical records |
| `data/duplicates.jsonl` | Duplicate tracking |
| `data/pdfs/` | Stored source PDFs |
| `data/briefs/` | Generated executive briefs + metadata |
| `data/quality/` | QC logs and Excel reports |
| `data/new_country_mapping.csv` | Region mapping (source of truth) |

## Quality monitoring

Automated post-hoc QC checks records and briefs without modifying them:

```bash
python scripts/run_quality.py              # check latest brief + its records
python scripts/run_quality.py --latest-brief   # explicit latest brief
python scripts/run_quality.py --brief-id <id>  # specific brief
```

- **Record KPIs** (R1–R5): evidence grounding, geo determinism, macro-theme rules, confidence alignment, priority audit
- **Brief KPIs** (B1–B5): citation consistency, uncertainty compliance, overreach detection
- **Output**: append-only JSONL logs + Excel report in `data/quality/`
- **Standards**: documented in `docs/quality/`

## Tests

```bash
python -m pytest tests/ -q
```

Five test suites covering macro-theme detection, region bucketing, date extraction, end-to-end scenarios, and brief QC.

## Architecture

Key design decisions:

- **LLM boundary** — The LLM extracts facts only. Priority, confidence, and macro-themes are computed deterministically by Python rules. No interpretive fields in the extraction schema.
- **Postprocess-before-validate** — Every code path runs `postprocess_record()` before `validate_record()`. Computed fields are always present when validation runs.
- **Two-tier regions** — Region values are driven by `data/new_country_mapping.csv`. The Home page warns automatically if CSV and Python constants diverge.
- **Minimal AI** — One model call per document for extraction. Scoring/classification stay deterministic in Python; weekly executive synthesis is an LLM step over approved stored JSON with an optional single repair call.

## Project structure

```
Home.py                    # Landing page and KPI dashboard
pages/
  01_Ingest.py             # PDF upload and extraction pipeline
  02_Review.py             # Analyst governance queue
  03_Brief.py              # Executive brief generation
  04_Insights.py           # Analytics and trend dashboards
  Admin.py                 # Maintenance and admin utilities
src/
  model_router.py          # Gemini LLM extraction (schema + prompt)
  postprocess.py           # Deterministic scoring and normalization
  constants.py             # Topics, regions, OEMs, macro-theme rules
  schema_validate.py       # Record validation
  briefing.py              # Brief synthesis and rendering
  storage.py               # JSONL read/write and PDF storage
  dedupe.py                # Duplicate detection
  quality.py               # Post-hoc QC engine
  pdf_extract.py           # PDF text extraction
  text_clean_chunk.py      # Text cleaning and chunking
  ui.py / ui_helpers.py    # Streamlit UI components
tests/                     # pytest test suites
scripts/                   # Migration and quality scripts
data/                      # Records, PDFs, briefs, quality logs
```
