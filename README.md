# Auto Intelligence (MVP) — Streamlit Multi-page Skeleton

## Run locally
1) Create a virtual environment
2) Install dependencies:
   - streamlit
   - pymupdf
   - pdfplumber
   - pandas
   - matplotlib

3) Run:
   streamlit run Home.py

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

## Footprint regions
- `India`, `China`, `Western Europe`, `Eastern Europe`, `Russia`, `Africa`, `US`, `Mexico`, `Thailand`
- Legacy `Europe (including Russia)` values are migrated to `Western Europe` unless Russia is explicitly present.

## Tests
- `pytest` is required for tests.
- Canonical command:
  - `python -m pytest -q`

## Bloomberg Date Semantics
- Use Bloomberg PDF header timestamp as the source-of-truth date when available.
- Store `publish_date` as date-only (`YYYY-MM-DD`) with no timezone conversion.
- This avoids PST/UTC rollover flip-flops (for example, Feb 1 PST vs Feb 2 UTC).
