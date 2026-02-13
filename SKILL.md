# SKILL.md — COGNITRA MVP Product Spec

## 1) Purpose
COGNITRA MVP converts automotive intelligence documents into structured, analyst-reviewable records for weekly intelligence workflows.

The MVP prioritizes reliability over stylistic generation:
- strict JSON extraction
- deterministic validation and normalization
- deterministic brief rendering from stored JSON

## 2) MVP Scope (Current)
### Inputs
- PDF upload
- Optional manual text paste (can override extracted PDF text)
- Optional manual `original_url` input

### Outputs
- One schema-valid JSON record per ingest
- Deterministic rendered Intelligence Brief from JSON (no second model call)
- JSONL persistence (`data/records.jsonl`)
- Optional CSV export from UI

## 3) User Flow
1. User uploads PDF (or pastes text).
2. System extracts text (`pdf_extract`) or uses pasted text.
3. System builds a bounded context pack (`context_pack`) from scored chunks.
4. Model routing executes extraction:
   - 1 model call
   - schema validation
   - single repair attempt if needed
   - fallback provider only on schema failure
5. Output is postprocessed and validated again.
6. Record is stored in JSONL.
7. Brief is rendered deterministically from the stored JSON.

## 4) MVP Architecture
### UI Layer (Streamlit)
- `Home.py`
- `pages/01_Ingest.py` (ingest + run pipeline)
- `pages/02_Inbox.py` (filter/list records)
- `pages/03_Record.py` (record review/edit)
- `pages/04_Dashboard.py` (analytics)
- `pages/05_Export_Admin.py` (CSV/admin)
- `pages/06_Weekly_Brief.py` (weekly briefing)

### Pipeline Modules
- `src/pdf_extract.py` — robust text extraction from PDF
- `src/context_pack.py` — deterministic chunking/scoring/selection under hard max size
- `src/model_router.py` — provider routing + strict extraction/repair logic
- `src/schema_validate.py` — schema gatekeeping
- `src/postprocess.py` — normalization (countries/regions/entities/URL/date handling)
- `src/storage.py` — JSONL persistence and PDF file storage
- `src/render_brief.py` — deterministic markdown brief from JSON

## 5) Routing and Quality Gate Logic
- Provider chain supports `auto` mode.
- Per provider:
  1. extraction call
  2. parse JSON
  3. postprocess
  4. validate
- If invalid: one repair call, then parse → postprocess → validate.
- Fallback to next provider only if schema validation fails.
- If all providers fail: no record written.

## 6) Metadata Contract (MVP Rules)
### Allowed `source_type`
- `S&P`
- `MarkLines`
- `Bloomberg`
- `Automotive News`
- `Reuters`
- `Patent`
- `Press Release`
- `Other`

### Topics
`topics` must contain 1-3 values from:
- OEM Strategy & Powertrain Shifts
- Closure Technology & Innovation
- OEM Programs & Vehicle Platforms
- Regulatory & Safety
- Supply Chain & Manufacturing
- Technology Partnerships & Components
- Market & Competition
- Financial & Business Performance
- Executive & Organizational

### Closure Topic Guardrail
`Closure Technology & Innovation` should be selected only if explicit terms appear, such as:
- latch
- door
- handle
- digital key
- smart entry
- cinch

## 7) Two-Layer Region Logic
1. `regions_mentioned`  
   Controlled footprint buckets inferred from:
   - `country_mentions` mapping
   - explicit region hints  
   Buckets: `India`, `China`, `Europe (including Russia)`, `Africa`, `US`, `Mexico`, `Thailand`

2. `regions_relevant_to_kiekert`  
   Strict footprint subset derived from `country_mentions` only.

## 8) Storage and Determinism
- Records saved as JSON Lines in `data/records.jsonl`
- Source PDFs stored in `data/pdfs/`
- Brief rendering is deterministic from JSON (`render_brief`) and does not call an LLM.

## 9) Out of Scope (Current MVP)
- Automated SharePoint ingestion
- Power BI direct pipeline
- Multi-system enterprise orchestration

## 10) Future Integration (Post-MVP)
- SharePoint integration for source ingestion and distribution
- Power BI integration for executive dashboards
- Expanded provider orchestration and observability
