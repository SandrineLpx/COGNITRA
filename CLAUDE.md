# COGNITRA — Automotive Competitive Intelligence Platform

## What this is

Streamlit multipage app (Home.py + pages/01–08) that ingests PDFs of automotive industry articles, extracts structured intelligence records via Gemini LLM, and produces weekly executive briefs for Kiekert (closure systems supplier: door latches, strikers, handles, smart entry, cinch systems).

Storage: file-based JSONL (`data/records.jsonl`). No database.

## Architecture invariants

### LLM-extracted vs computed fields

This is the most important boundary in the codebase. Respect it.

- **LLM schema** (`src/model_router.py` → `record_response_schema()`): only factual extraction fields. The Gemini structured-output schema defines what the LLM returns.
- **Computed fields** (`src/postprocess.py` → `postprocess_record()`): `priority`, `confidence`, `macro_themes_detected`, and all `_` prefixed audit keys are set deterministically by Python rules, never by the LLM.
- **Guardrail**: `_COMPUTED_FIELDS` whitelist in `record_response_schema()` prevents silent misalignment between `REQUIRED_KEYS` and schema properties. If you add a field to `REQUIRED_KEYS` that isn't in schema properties or `_COMPUTED_FIELDS`, the app crashes at import time.

### Postprocess pipeline order

`postprocess_record()` runs in this order — do not reorder:
1. Set defaults (`priority`, `confidence` via `setdefault`)
2. Normalize fields (publish_date, URL, actor_type, countries, regions, companies, government_entities)
3. `_boost_priority()` — rule-based priority escalation
4. `_compute_confidence()` — deterministic confidence from observable signals
5. `_detect_macro_themes()` — keyword/company/topic/region pattern matching

`_publisher_date_override_applied` / `_publisher_date_override_source` are computed diagnostics for publisher header parsing.
`_region_migrations` / `_region_ambiguity` are optional diagnostics for legacy region migration and generic-Europe defaulting.

### Footprint regions (current)

`FOOTPRINT_REGIONS` currently uses:
- `India`, `China`, `Western Europe`, `Eastern Europe`, `Russia`, `Africa`, `US`, `Mexico`, `Thailand`

Backward compatibility:
- Legacy `Europe (including Russia)` is migrated to `Western Europe` unless Russia is explicitly present in source signals.

### Record lifecycle

Every code path runs `postprocess_record()` before `validate_record()`. This means computed fields (priority, confidence) are always present when validation runs. Do not call `validate_record()` without postprocessing first.
Ingest chunking is automatic (derived from cleaned-document chunk metadata); there is no manual chunk-mode toggle.

## Key files

| File | Role |
|---|---|
| `src/constants.py` | Canonical topics, regions, allowed values, `REQUIRED_KEYS`, `FIELD_POLICY`, `MACRO_THEME_RULES`, `PREMIUM_OEMS` |
| `src/model_router.py` | LLM extraction schema, prompt, Gemini API calls |
| `src/postprocess.py` | All deterministic post-processing: normalization, priority, confidence, macro themes |
| `src/schema_validate.py` | Record validation (runs after postprocess) |
| `src/briefing.py` | Weekly brief selection, rendering, LLM synthesis prompt |
| `src/storage.py` | JSONL read/write, record IDs, PDF storage |
| `src/dedupe.py` / `src/dedup_rank.py` | Duplicate detection and story-level dedup |
| `src/render_brief.py` | Single-record intelligence brief markdown rendering |
| `pages/01_Ingest.py` | PDF upload → LLM extraction → postprocess → validate → store |
| `pages/04_Dashboard.py` | Analytics dashboard |
| `pages/05_Weekly_Brief.py` / `pages/06_Review_Brief.py` | Weekly brief generation and review |

## How to add a new macro theme

Append a dict to `MACRO_THEME_RULES` in `src/constants.py`. No code changes needed in postprocess.py.

```python
{
    "name": "Theme Name",
    "min_groups": 2,                    # how many signal groups must match
    "signals": {
        "companies": {"company_a", "company_b"},   # lowercased
        "keywords": [r"regex_pattern"],             # searched in title, evidence_bullets, key_insights, keywords
        "topics": {"Canonical Topic Name"},         # exact match against CANON_TOPICS
        "regions": {"US", "China"},                 # match against regions_mentioned + regions_relevant_to_kiekert
    },
    # Optional:
    "anti_keywords": [r"pattern"],      # suppress if matched and <3 groups hit
    "premium_company_gate": True,       # require company in PREMIUM_OEMS
    "region_requirements": {"US"},      # require at least one of these regions present
    "rollup": "Cluster Label",          # shared label for overlapping themes
}
```

## Common constraints

- Do NOT add interpretive fields (strategic_implications, recommended_actions, etc.) back to the LLM schema. Those were removed intentionally for lean/deterministic ingest.
- NEVER assign strategic interpretation, priority, confidence, macro themes, or risk labels. Those are deterministic only.
- Do NOT add fields to `REQUIRED_KEYS` without also adding them to schema `properties` or `_COMPUTED_FIELDS`.
- Do NOT reorder the postprocess pipeline steps.
- Do NOT call `validate_record()` without running `postprocess_record()` first.
- Backward compatibility: old records may lack newer computed fields. Always use `.get()` with defaults in UI/rendering code.

## Running tests

pytest required for tests.

```bash
python -m pytest -q
```

To run the main suites explicitly:

```bash
python -m pytest test_scenarios.py test_macro_themes.py -v
```

## TODO (next session)

### Macro theme refinements

0. **Future improvement (deferred):** consider relaxing SDV theme firing (for example, allow tech-company + SDV keyword combinations), but keep current strict `min_groups=2` for now.

1. **Widen PREMIUM_OEMS for non-European premium**: Add "genesis", "lexus", and optionally "acura", "infiniti" to `PREMIUM_OEMS` in `constants.py`. Current set is Europe-supercar heavy — may miss Kiekert-relevant premium programs from Korean/Japanese OEMs.

2. **Company normalization edge cases**: Extend deterministic legal-entity canonicalization beyond current covered variants (for example, additional OEM legal suffix patterns) if misses appear in real records.

3. **Validate macro themes on real Bloomberg record**: Ingest a Mercedes Bloomberg article and verify the output produces:
   - `macro_themes_detected`: ["Luxury OEM Stress", "Margin Compression at Premium OEMs", "Software-Defined Premium Shift"]
   - `_macro_theme_rollups`: ["Premium OEM Financial/Strategy Stress"]
   - "Tariff & Trade Disruption" fires only if region gate + keyword both hit
   - Paste one `_macro_theme_detail` theme block and review audit readability — consider formatting tweaks for executive-debug-friendliness.

4. **Rollup elevation in weekly brief**: The "Premium OEM Financial/Strategy Stress" rollup is the Kiekert headline signal (pricing pressure cascade + premium content risk/opportunity). Consider surfacing `_macro_theme_rollups` in the weekly synthesis prompt or brief rendering so it gets elevated automatically.

## External dependencies

- **Gemini API** (google-genai): primary LLM provider, structured JSON output
- **Streamlit**: UI framework (multipage app)
- **PyMuPDF / pdfplumber**: PDF text extraction
- API keys in `.streamlit/secrets.toml` (GEMINI_API_KEY required)
