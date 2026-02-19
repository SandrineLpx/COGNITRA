# COGNITRA — Automotive Competitive Intelligence Platform

## What this is

Streamlit multipage app (Home.py + 5 pages) that ingests PDFs of automotive industry articles, extracts structured intelligence records via Gemini LLM, and produces weekly executive briefs for Kiekert (closure systems supplier: door latches, strikers, handles, smart entry, cinch systems).

Minimal-AI approach: one model call per document for strict JSON extraction, deterministic postprocessing and validation, deterministic brief rendering from stored JSON (no second model call). Human review before executive reporting.

Storage: file-based JSONL (`data/records.jsonl`). No database.

### Kiekert domain scope

This platform focuses on **closure systems and car entry markets**:
- Latches, cinching, handles, power closures
- Door modules and related mechatronics
- Smart entry and access technologies (UWB, digital key)
- Safety and regulatory impacts relevant to closures/access
- Strikers, cinch systems

The `Closure Technology & Innovation` topic should only fire when explicit terms appear (latch, door, handle, digital key, smart entry, cinch).

## Architecture invariants

### LLM-extracted vs computed fields

This is the most important boundary in the codebase. Respect it.

- **LLM schema** (`src/model_router.py` → `record_response_schema()`): only factual extraction fields. The Gemini structured-output schema defines what the LLM returns.
- **Computed fields** (`src/postprocess.py` → `postprocess_record()`): `priority`, `confidence`, `macro_themes_detected`, and all `_` prefixed audit keys are set deterministically by Python rules, never by the LLM.
- **Guardrail**: `_COMPUTED_FIELDS` whitelist in `record_response_schema()` prevents silent misalignment between `REQUIRED_KEYS` and schema properties. If you add a field to `REQUIRED_KEYS` that isn't in schema properties or `_COMPUTED_FIELDS`, the app crashes at import time.

### Extraction prompt design constraints

The prompt in `model_router.py` → `extraction_prompt()` uses 13 numbered rules. Key constraints for anyone editing the prompt or reviewing extractions:

- **evidence_bullets vs key_insights**: `evidence_bullets` = verbatim facts (2–4 bullets, ≤25 words each, directly grounded in source text). `key_insights` = analytical interpretation — must not repeat bullets verbatim; must add meaning.
- **keywords**: include brands and actors that play a material role in the article. **Exclude** country names, region names, publisher names, and generic measurement phrases (e.g. "year-over-year", "production volume"). Countries belong in `country_mentions`; regions belong in `regions_mentioned`.
- **country_mentions**: operational markets only — countries where the article's subject operates, manufactures, or sells. Not geographic color or incidental mentions.
- **regions_mentioned**: geographic scope framing using `DISPLAY_REGIONS` display buckets only. Not operational precision.
- **notes**: leave empty (`""`) unless there is a genuine caveat not captured by any other field (e.g., paywall-truncated content, obvious translation artifact).
- **COMPETITORS block placement**: the closure-systems competitor list appears immediately after the actor_type rule (rule 3), so the model sees it before deciding to default to `"other"`.

### Postprocess pipeline order

`postprocess_record()` runs in this order — do not reorder:
1. Set defaults (`priority`, `confidence` via `setdefault`)
2. Normalize fields (publish_date, URL, actor_type, countries, regions, companies, government_entities)
3. `_boost_priority()` — rule-based priority escalation
4. `_compute_confidence()` — deterministic confidence from observable signals
5. `_detect_macro_themes()` — keyword/company/topic/region pattern matching

`_publisher_date_override_applied` / `_publisher_date_override_source` are computed diagnostics for publisher header parsing.
`_region_migrations` / `_region_ambiguity` are optional diagnostics for legacy region migration and generic-Europe defaulting.

### Two-tier region architecture

Region values are driven by `data/new_country_mapping.csv`. The key design principle: **every footprint value is its own display value** — `FOOTPRINT_TO_DISPLAY` is an empty dict (identity mapping).

- **`FOOTPRINT_REGIONS`** / **`DISPLAY_REGIONS`**: same list (~34 values). Includes individual Kiekert-relevant countries by name (`France`, `Germany`, `Japan`, `South Korea`, `United States`, `Czech Republic`, `Morocco`, etc.) and sub-regional buckets (`West Europe`, `Central Europe`, `East Europe`, `NAFTA`, `ASEAN`, `Andean`, `Mercosul`, `Central America`, `Indian Subcontinent`, `Africa`, `Middle East`, `Oceania`, `Rest of World`) plus generic catch-alls (`Europe`, `South America`, `South Asia`).
- **`FOOTPRINT_TO_DISPLAY`**: `{}` (empty dict). Code uses `FOOTPRINT_TO_DISPLAY.get(r, r)` — identity for all values.
- **`COUNTRY_TO_FOOTPRINT`** in `postprocess.py`: maps ~90 countries to footprint regions. Rule from CSV: if `relevant to Kiekert` ≠ "" → use that value; else use market bucket. Countries not in the CSV → `Rest of World`.
- **`REGION_ALIASES`** in `postprocess.py`: normalizes LLM-returned strings to canonical names. `"us"` alias intentionally absent (pronoun false-positive problem). Old long-form names are kept as aliases for backward compatibility: `"Western Europe"` → `"West Europe"`, `"Eastern Europe"` → `"East Europe"`, `"Latin America"` → `"South America"`, `"Asia"` → `"South Asia"`.

Both `regions_mentioned` and `regions_relevant_to_kiekert` use the same value set. `regions_relevant_to_kiekert` is derived strictly from `country_mentions` via `COUNTRY_TO_FOOTPRINT`. `regions_mentioned` also incorporates text hints from `_regions_from_text_hints()`.

Backward compatibility:
- Legacy `Europe (including Russia)` is migrated to `Europe` (generic catch-all) unless Russia is explicitly present in `country_mentions`.
- Old values (`Western Europe`, `Eastern Europe`, `Latin America`, `Asia`, `US`) in stored records should be migrated once using `scripts/migrate_region_overhaul.py --apply`.

**Region guards**: `_regions_from_text_hints()` does a bare substring scan of evidence/keywords text and can inject footprint regions from incidental text. Deterministic guards in `postprocess_record()` remove `"United States"` and `"China"` from merged regions if not backed by `country_mentions`. These guards are not redundant with the extraction prompt — the prompt is probabilistic guidance; the guards are deterministic enforcement on a different code path.

### Record lifecycle

Every code path runs `postprocess_record()` before `validate_record()`. This means computed fields (priority, confidence) are always present when validation runs. Do not call `validate_record()` without postprocessing first.
Ingest chunking is automatic (derived from cleaned-document chunk metadata); there is no manual chunk-mode toggle.

### Ingest flow

1. User uploads PDF (or pastes text).
2. System extracts text (`pdf_extract`) or uses pasted text.
3. System cleans and chunks the text (`text_clean_chunk`); `choose_extraction_strategy()` classifies noise level from chunk metadata and selects the initial model.
4. Model routing executes extraction: one model call → schema validation → single repair attempt if needed → fallback provider on schema failure.
5. Output is postprocessed (`postprocess_record`) and validated (`validate_record`).
6. Duplicate check (exact title + similar story dedup).
7. Record stored in JSONL; brief rendered deterministically from JSON.

## Key files

| File | Role |
|---|---|
| `src/constants.py` | Canonical topics, regions, allowed values, `REQUIRED_KEYS`, `FIELD_POLICY`, `MACRO_THEME_RULES`, `PREMIUM_OEMS` |
| `src/model_router.py` | LLM extraction schema, prompt, Gemini API calls |
| `src/postprocess.py` | All deterministic post-processing: normalization, priority, confidence, macro themes |
| `src/schema_validate.py` | Record validation (runs after postprocess) |
| `src/briefing.py` | Weekly brief selection, rendering, LLM synthesis prompt |
| `src/storage.py` | JSONL read/write, record IDs, PDF storage |
| `src/dedupe.py` | Duplicate detection and story-level dedup (canonical implementation) |
| `src/dedup_rank.py` | Backward-compatible wrapper around `src/dedupe.py`; not actively imported |
| `src/render_brief.py` | Single-record intelligence brief markdown rendering |
| `src/quality.py` | Post-hoc QC engine: record + brief checks, KPI computation, Excel export |
| `scripts/run_quality.py` | CLI entrypoint for quality pipeline (`--latest-brief` or `--brief-id`) |
| `pages/01_Ingest.py` | PDF upload → LLM extraction → postprocess → validate → store |
| `pages/02_Review_Approve.py` | Queue review, record detail/edit, approve/disapprove |
| `pages/03_Weekly_Executive_Brief.py` | Weekly brief generation and saved-brief review |
| `pages/04_Insights.py` | Analytics and trend monitoring |
| `pages/08_Admin.py` | Advanced/admin utilities |

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

## Priority scoring heuristics

Used by `_boost_priority()` in `postprocess.py`:

**High priority:**
- Major OEM strategy shifts affecting platform/powertrain mix or sourcing strategy
- Major competitor moves affecting closures/access content or capacity
- Regulatory or safety changes with compliance impact
- Supply disruptions (plant shutdowns, sanctions, border constraints) affecting footprint regions
- M&A, insolvency, major restructurings affecting supply stability
- Awards/wins or major sourcing decisions tied to closures/car entry

**Medium priority:**
- Market demand/mix changes in footprint regions
- Partnerships or component sourcing with plausible impact on closures/access
- Program updates with meaningful timing/volume implications

**Low priority:**
- Generic commentary with limited operational detail
- Weak signals without concrete facts (unless footprint impact is explicit)

## Review gating

Records auto-approve if confidence is Medium+ with a publish date and a known source type. Human review is required when:
- `confidence = Low`
- `source_type = "Other"`
- `publish_date` is missing

## Running tests

```bash
python -m pytest tests/ -q
```

To run specific suites:

```bash
python -m pytest tests/test_scenarios.py tests/test_macro_themes.py tests/test_regions_bucketed.py -v
```

## Quality monitoring

Automated QC runs post-hoc on records and briefs via `python scripts/run_quality.py`.

- **Record checks**: evidence grounding (PDF text overlap), geo determinism (country→footprint completeness, display bucket leakage), macro theme rule validation (min_groups, premium gate, region requirements), confidence-evidence alignment, priority reason audit.
- **Brief checks**: REC citation consistency, uncertainty section compliance, overreach detection.
- **Shared constants**: `UNCERTAINTY_WORDS` and `UNCERTAINTY_TOPICS` in `constants.py` — single source of truth consumed by both `briefing.py` (synthesis prompt) and `quality.py` (QC checker). Do not define uncertainty word lists elsewhere.
- **Quality standards**: `References/Quality/` contains QUALITY_CHECKLIST.md, QUALITY_KPIS.md, BRIEF_GENERATION_STANDARDS.md.
- **Output**: append-only JSONL logs in `data/quality/`, Excel report with 4 sheets.
- **Read-only invariant**: the quality module never modifies records or briefs. It observes and reports.

## TODO (next session)

### Macro theme refinements

0. **Future improvement (deferred):** consider relaxing SDV theme firing (for example, allow tech-company + SDV keyword combinations), but keep current strict `min_groups=2` for now.

1. **Widen PREMIUM_OEMS for non-European premium**: Add "genesis", "lexus", and optionally "acura", "infiniti" to `PREMIUM_OEMS` in `constants.py`. Current set is Europe-supercar heavy — may miss Kiekert-relevant premium programs from Korean/Japanese OEMs.

2. **Company normalization edge cases**: Extend deterministic legal-entity canonicalization beyond current covered variants (for example, additional OEM legal suffix patterns) if misses appear in real records.

3. **Rollup elevation in weekly brief**: The "Premium OEM Financial/Strategy Stress" rollup is the Kiekert headline signal. Consider surfacing `_macro_theme_rollups` in the weekly synthesis prompt or brief rendering so it gets elevated automatically.

## External dependencies

- **Gemini API** (google-genai): primary LLM provider, structured JSON output
- **Streamlit**: UI framework (multipage app)
- **PyMuPDF / pdfplumber**: PDF text extraction
- API keys in `.streamlit/secrets.toml` (GEMINI_API_KEY required)
