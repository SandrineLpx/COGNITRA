# Auto Intelligence (MVP) - Streamlit Multi-page Skeleton

## Run locally
1) Create a virtual environment
2) Install dependencies:
   - `pip install -r requirements.txt`
   - or `pip install .[dev]`
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

## Ingest behavior
- Chunking is automatic based on cleaned document structure (`chunks_count`).
- The app surfaces chunk-count guidance and estimated API-call impact in the Ingest UI.

## Workflow navigation
- `Ingest` -> `Review & Approve` -> `Weekly Executive Brief` -> `Insights`
- Record governance (approve/disapprove/edit/re-ingest/delete) is centralized in `Review & Approve`.
- `Weekly Executive Brief` is executive-focused output generation (no record status editing).
- `Advanced / Admin` contains developer/analyst utilities and maintenance actions.

## Footprint regions
- `India`, `China`, `Western Europe`, `Eastern Europe`, `Russia`, `Africa`, `US`, `Mexico`, `Latin America`, `Thailand`
- Legacy `Europe (including Russia)` values are migrated to `Western Europe` unless Russia is explicitly present.

## Tests
- `pytest` is required for tests.
- Canonical command:
  - `python -m pytest -q`

## Bloomberg Date Semantics
- Use Bloomberg PDF header timestamp as the source-of-truth date when available.
- Store `publish_date` as date-only (`YYYY-MM-DD`) with no timezone conversion.
- This avoids PST/UTC rollover flip-flops (for example, Feb 1 PST vs Feb 2 UTC).
