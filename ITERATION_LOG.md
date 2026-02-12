# Iteration Log (Clean)

Concise milestone log. Full detailed history is preserved in `ITERATION_LOG_FULL.md`.

| Iteration | Date | Update | Reason | Improvement |
|---|---|---|---|---|
| v1.0 | 2026-02-11 | Replaced `call_model()` stub in `src/model_router.py` with a working extraction pipeline. | App was blocked by `NotImplementedError` during ingest. | End-to-end ingest path became runnable. |
| v1.1 | 2026-02-11 | Expanded source taxonomy (`S&P`, `MarkLines`) and centralized schema constants in `src/constants.py`. | Needed additional publisher labels and cleaner shared config. | Consistent enums and easier maintenance across modules. |
| v1.2 | 2026-02-11 | Introduced two-layer geography processing in `src/postprocess.py` and integrated it into ingest/router flow. | Needed normalized geographic fields and strict footprint relevance. | Cleaner `country_mentions`, controlled `regions_mentioned`, reliable `regions_relevant_to_kiekert`. |
| v1.3 | 2026-02-11 | Strengthened validation in `src/schema_validate.py` (duplicates, size bounds, footprint checks). | Reduce malformed records entering storage. | Higher record quality and safer downstream analytics. |
| v1.4 | 2026-02-12 | Wired Gemini via `google-genai` with structured output schema and provider routing/logging. | Needed production model calls instead of local-only behavior. | Deterministic JSON extraction with clearer provider errors. |
| v1.5 | 2026-02-12 | Hardened Gemini schema compatibility (SDK-valid types/nullable handling) and prompt rules for extraction reliability. | Early API calls failed on unsupported schema shapes. | Stable Gemini request/response behavior and better extraction consistency. |
| v1.6 | 2026-02-12 | Added secrets support (`.streamlit/secrets.toml` + env fallback), secrets template, and `.gitignore` protection. | Simplify local key management and avoid leaking credentials. | Safer configuration workflow for API keys. |
| v1.7 | 2026-02-12 | Aligned docs and repo hygiene (`README` updates, constants consistency, data normalization pass). | Version drift between implementation and documentation. | Clearer onboarding and consistent behavior across existing/new records. |
