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
