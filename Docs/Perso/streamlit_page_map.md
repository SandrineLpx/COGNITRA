# COGNITRA — Streamlit Page Map

> Generated 2026-02-18. Reflects current codebase state including: `is_duplicate` rename, 14-rule cleaner, `raw_chars`/`clean_chars` in `routing_metrics`.

---

## Summary

| Page | What it does | Key modules |
|---|---|---|
| **Home** | Landing page, workflow description | `ui_helpers` |
| **01 Ingest** | Upload PDF or paste text → extract → clean → LLM → postprocess → dedupe → save | `pdf_extract`, `text_clean_chunk`, `model_router`, `postprocess`, `schema_validate`, `dedupe`, `storage` |
| **02 Review** | Filter queue, inspect records, edit JSON, approve/disapprove, re-ingest from stored PDF | `storage`, `model_router`, `postprocess`, `schema_validate`, `render_brief` |
| **03 Weekly Executive Brief** | Select approved records, generate AI brief, export as MD / email, diff vs previous brief | `briefing`, `storage` |
| **04 Insights** | Analytics: volume histogram, region×topic heatmap, topic momentum, company mentions, quality score trend, drilldown table | `storage`, `dedupe`, `quality` |
| **08 Admin** | CSV/JSONL export, deduplication stats, demo reset | `storage`, `dedupe` |

### Ingest pipeline at a glance

```
PDF bytes
  → extract_text_robust     PyMuPDF first, pdfplumber fallback, no OCR
  → clean_and_chunk         strip junk (14 rules), split into 9k-char chunks
  → choose_strategy         noise level → model choice; chunks_count → chunked mode
  → LLM extraction          gemini-2.5-flash-lite → repair with flash if schema fails
  → postprocess             deterministic: priority, confidence, regions, macro themes
  → validate                hard schema gate; failure triggers strong-model repair
  → dedupe check            exact title block; fuzzy ≥0.88 → score & flag is_duplicate
  → auto-approve            High/Med confidence + date + source ≠ Other + ≥2 bullets
  → save to JSONL
```

---

## Detailed Page Map

---

### Home (`Home.py`)

**UI:** Landing page with workflow description and sidebar navigation guide.
**Modules:** `src.ui_helpers.workflow_ribbon`

---

### Page 01 — Ingest (`pages/01_Ingest.py`)

**UI:** Upload single or multiple PDFs (or paste text manually). Sidebar shows model selector, daily API quota meters per model, and override rule impact per run. After processing: displays the saved JSON record + rendered intelligence brief.

#### Full Pipeline with Decision Criteria

##### Step 1 — PDF → text
`src.pdf_extract` → `extract_text_robust`, `extract_pdf_publish_date_hint`

**Text extraction — actual order:**
```
1. PyMuPDF (fitz)  → if result ≥ 500 chars → done, method = "pymupdf"
2. pdfplumber      → if it yields MORE text than PyMuPDF → done, method = "pdfplumber"
3. No OCR fallback → returns whatever PyMuPDF gave (even if short), method = "pymupdf"
```

No OCR — both libraries only work on selectable-text PDFs. If both return < 500 chars (scanned image PDF), the pipeline gets weak text and extraction will likely produce a low-quality or failed record.

**Publish date hint — actual priority order:**
```
1. Header date   → regex scan of first 60 lines of extracted text
                   patterns: "Feb 4, 2026" (MDY), "4 Feb 2026" (DMY), "2026-02-04" (ISO)
                   source tag: "pdf_header_publish_date"

2. Metadata date → PyMuPDF reads PDF metadata fields:
                   creationDate / modDate (format "D:20260204..." or ISO)
                   source tag: "pdf_metadata_publish_date"

3. Nothing found → returns (None, None)
```

The hint is only used by postprocess (Step 5) if the LLM returned null for `publish_date` — it never overwrites a date the LLM already extracted.

---

##### Step 2 — Clean + chunk
`src.text_clean_chunk` → `clean_and_chunk`

Normalizes whitespace, strips junk lines, then splits into overlapping chunks (max 9,000 chars, 800-char overlap).

**Line drop rules (evaluated in order, first match wins):**

| Rule | Trigger | Example |
|---|---|---|
| `repeated_header_footer` | Line appears ≥ max(3, 1.5% of all lines) times | Publication name repeating in every page header |
| `page_number` | Matches `^\d{1,4}$` or `Page X`, `Page X of Y`, `X/Y` | `4`, `Page 12`, `Page 12 of 44` |
| `link_heavy` | ≥ 2 URLs on one line | Nav bars with multiple hrefs |
| `link_heavy` (bare URL) | Line is a single URL AND position > line 10 | `https://www.spglobal.com/...` mid-doc |
| `symbol_heavy` | > 35% non-letter chars, not a table row, not a publish timestamp | `* * * * * *` |
| `nav` | subscribe, sign in, log in, newsletter, cookie, privacy policy, `terms of (use/service/conditions)`, contact us, follow us | "Subscribe to continue reading" |
| `promo` | advertisement, sponsored, promoted, our partners | "Sponsored content" |
| `related` | related articles, recommended, read next, you may also like | "Read next: EV sales drop" |
| `social` | share on, facebook, twitter, linkedin, copy link | "Share on LinkedIn" |
| `paywall` | already a subscriber, create an account, for unlimited access, subscribe to continue | "Create an account for full access" |
| `legal` | `© YYYY`, `copyright YYYY`, all rights reserved, no portion of this report, without written permission, for informational purposes only, this report has been prepared/produced | "© 2025 S&P Global. All rights reserved." |
| `image_credit_short` | Contains photo/credit/getty/stock AND < 8 words | "Photo: Getty Images" |
| `short_allcaps_menu` | ≤ 6 words, all uppercase, ≤ 60 chars — first occurrence near top of doc is kept | `MARKETS AUTOS INDUSTRY` |
| `byline` | Starts with `By`, `Author:`, `Written by`, `Reported by` AND ≤ 8 words | "By John Smith and Jane Doe" |

> Note: the old rule `\bterms\b` was narrowed to `terms of (use/service/conditions)` to stop dropping legitimate content like *"under the terms of the agreement"*.

> Note: `max(3, 1.5%)` means the threshold scales with document length — on a 100-line article the floor of 3 applies; on a 400-line report 6 repetitions are required. This prevents over-firing on long paginated documents where a phrase may legitimately repeat a few times.

**Output `meta` dict** (passed to next step):
`raw_chars`, `clean_chars`, `removed_chars`, `removed_line_count`, `chunks_count`, `detected_title`, `top_removed_patterns`, `chunk_ids`

---

##### Step 3 — Choose strategy
`src.model_router` → `choose_extraction_strategy(meta)`

```
Noise level:
  IF  removed_ratio > 18%
  OR  removed_lines > 250
  OR  top_removed_patterns ∩ {ocr, table, header, footer, page} ≠ ∅
  → noise = "high"   → primary = gemini-2.5-flash  (strong)

  ELIF removed_ratio < 8% AND removed_lines < 80
  → noise = "low"    → primary = gemini-2.5-flash-lite

  ELSE
  → noise = "normal" → primary = gemini-2.5-flash-lite

  fallback_model = gemini-2.5-flash (always, regardless of noise level)

Chunked mode:
  IF chunks_count > 1  → chunked_mode = True  (one LLM call per chunk)
  ELSE                 → chunked_mode = False (single LLM call)
```

**Stored in every record** as `_router_log.routing_metrics`:
```json
{
  "noise_level": "normal",
  "chunks_count": 1,
  "raw_chars": 14320,
  "clean_chars": 9180,
  "removed_ratio": 0.359,
  "removed_line_count": 42,
  "top_removed_patterns": [["legal", 5], ["page_number", 3], ["byline", 1]]
}
```

`raw_chars` = original PDF text size. `clean_chars` = what the LLM actually saw.
Older records (pre-2026-02-18) only have `removed_ratio`, `removed_line_count`, `top_removed_patterns`.

---

##### Step 4 — LLM extraction
`src.model_router` → `route_and_extract` / `extract_single_pass`

**Single-pass path (not chunked):**
```
1. Call primary model with extraction prompt + enforced JSON schema
   → parse JSON → postprocess → validate
   IF valid → done ✓

2. IF validation fails (schema error / JSON parse error / missing required keys):
   → Call fallback gemini-2.5-flash with fix_json_prompt(broken_output, errors)
   → parse JSON → postprocess → validate
   IF valid → done ✓  ELSE → failure
```

**Chunked path:**
```
Phase 1: all N chunks → primary model (sequential loop)
Phase 2: failed chunks only → fallback model (repair, only if primary ≠ fallback)

Merge all successful chunk records:
  source_type      : majority vote (excluding "Other")
  actor_type       : majority vote; tiebreak → "oem" if companies present
  title            : first non-empty title across chunks
  publish_date     : highest confidence wins; tiebreak → newest date
  lists            : union, deduplicated, capped (topics ≤ 3, keywords ≤ 12, bullets ≤ 4)
  evidence_bullets : prefer bullets ≤ 25 words
```

**Provider fallback chain (auto mode):** `gemini → claude → chatgpt`
Claude and ChatGPT raise `NotImplementedError` — Gemini is the only active provider.

**Extraction prompt encodes:** Kiekert domain context (door latches, strikers, handles, smart entry, cinch systems), 9 topic classification rules with disambiguation guidance, source_type / actor_type assignment rules, closure systems competitor list (Hi-Lex, Aisin, Brose, Huf, Magna, Inteva, Mitsui Kinzoku…), evidence bullet rules (2–4 bullets ≤ 25 words; must include a verbatim numeric fact if present in the article).

---

##### Step 5 — Postprocess
`src.postprocess` → `postprocess_record`

Deterministic normalization applied after every LLM call. `priority`, `confidence`, and `macro_themes_detected` are **never set by the LLM** — always computed here.

| Rule | What it does |
|---|---|
| Company canonicalization | Normalizes OEM names via `_OEM_CANONICAL_BY_LOWER` map |
| Country normalization | `COUNTRY_ALIASES`: USA/U.S./us → United States |
| Region normalization | `REGION_ALIASES`: LATAM → South America, EU → Europe, "Asia" → South Asia, "Western Europe" → West Europe |
| `regions_relevant_to_kiekert` | Derived from `country_mentions` via `COUNTRY_TO_FOOTPRINT` map; never LLM-set |
| `priority` | Computed from source type + topic + company signals + macro theme escalation |
| `confidence` | Computed from evidence quality, date presence, topic clarity |
| `macro_themes_detected` | Pattern-matched from topics + keywords against `MACRO_THEME_RULES` |
| `publish_date` | Only filled if LLM returned null AND a hint was found in Step 1; never overwrites existing valid date |
| Provenance tracking | All mutations logged to `_mutations`, `_provenance`, `_rule_impact` |

---

##### Step 6 — Validate
`src.schema_validate` → `validate_record`

Hard gate — record passes only if all constraints are satisfied. Failure triggers the strong-model repair call in Step 4, or fails the record entirely.

| Field | Constraint |
|---|---|
| All `REQUIRED_KEYS` | Present |
| `source_type` | In `ALLOWED_SOURCE_TYPES` |
| `actor_type` | In `ALLOWED_ACTOR_TYPES` |
| `publish_date` | `YYYY-MM-DD` format or null |
| `topics` | List of 1–4 items, all from `CANON_TOPICS` |
| `keywords` | List of 3–15 items |
| `evidence_bullets` | List of exactly 2–4 items |
| `key_insights` | List of exactly 2–4 items |
| `regions_mentioned` | All in `DISPLAY_REGIONS`, no duplicates, ≤ 15 |
| `regions_relevant_to_kiekert` | All in `FOOTPRINT_REGIONS` |

---

##### Step 7 — Dedupe check
`src.dedupe` → `find_exact_title_duplicate`, `find_similar_title_records`, `score_source_quality`

```
1. Exact title match (lowercase + strip punctuation)
   → found: reject ingestion entirely (hard block, no record saved)

2. Fuzzy title similarity (SequenceMatcher ratio ≥ 0.88)
   → found: compare source quality scores
       score = publisher_score + confidence_score + completeness_score

       publisher_score : S&P=100, Bloomberg=90, Reuters=80, MarkLines=76,
                         Automotive News=75, Industry Publication=72, Other=50
       confidence_score: High=3, Medium=2, Low=1
       completeness    : +1 each for publish_date present, original_url present,
                         regions_relevant_to_kiekert non-empty, evidence_bullets ≥ 3

       IF new record scores higher  → existing.is_duplicate = True
       IF existing scores higher    → new.is_duplicate = True

   pick_canonical tiebreak order:
     publisher_score → confidence → completeness →
     newest publish_date → newest created_at → record_id
```

---

##### Step 8 — Auto-approve
```
IF confidence ∈ {High, Medium}
   AND publish_date is present
   AND source_type ≠ "Other"
   AND len(evidence_bullets) ≥ 2
→ review_status = "Approved"
ELSE → review_status = "Pending"
```

---

### Page 02 — Review & Approve (`pages/02_Review_Approve.py`)

**UI:** Filterable queue (priority / status / source / text search). Queue summary: brief-eligible count (Approved + `is_duplicate=False`), pending, excluded. Record detail panel with evidence, insights, source link, editable raw JSON. Quick Approve / Quick Disapprove / Save buttons. "Iteration / Quality Fix" expander to delete record, delete stored PDF only, or re-run full extraction from the stored PDF with a fresh LLM call.

**Modules:** `src.storage`, `src.postprocess`, `src.model_router`, `src.pdf_extract`, `src.text_clean_chunk`, `src.schema_validate`, `src.render_brief`, `src.ui_helpers`

**Key fields managed:** `review_status`, `is_duplicate` (checkbox labeled "Exclude from brief"), `reviewed_by`, `notes`, `source_pdf_path`

---

### Page 03 — Weekly Executive Brief (`pages/03_Weekly_Executive_Brief.py`)

**UI:** Time-window selector (days back; date basis: `publish_date` or `created_at`). Candidate table annotated with already-shared history. Multiselect for record inclusion (pre-selected: Approved + `is_duplicate=False`). Generates AI brief via LLM. Three output formats: rendered Markdown, plain-text copy, executive email draft. Save / download `.md` / open in email client. Diff view against previous saved brief.

**Candidate filtering logic:**
```
Base pool    : select_weekly_candidates (Approved; optionally include is_duplicate=True)
Time window  : record date ≥ today − N days (by publish_date or created_at)
Brief history: records already in a saved brief flagged "already_shared",
               hidden by default (hide_already_shared toggle)
```

**Modules:** `src.briefing` (`select_weekly_candidates`, `synthesize_weekly_brief_llm`, `render_weekly_brief_md`, `render_exec_email`), `src.storage`, `src.ui_helpers`

**Files written:** `data/briefs/brief_<ts>.md`, `data/briefs/brief_<ts>.meta.json`, `data/briefs/index.jsonl`

---

### Page 04 — Insights (`pages/04_Insights.py`)

**UI:** Exploratory analytics. Filters: date range, review status, source type, topics, "Exclude suppressed/duplicate records" toggle.

| # | Section | What it shows |
|---|---|---|
| 1 | **KPI row** | Records / Approved / Pending / Disapproved / Duplicates (`is_duplicate=True`) / High Priority |
| 2 | **Weekly histogram** | Record volume by week, stacked by source type (Altair) |
| 3 | **Region × Topic heatmap** | Cross-tab of `regions_relevant_to_kiekert` × `topics` (matplotlib) |
| 4 | **Topic Momentum** | Weighted frequency change prior half vs recent half of date range; classified Emerging / Expanding / Fading / Stable (Altair horizontal bar + detail table) |
| 5 | **Top Company Mentions** | Top 10 canonicalized companies, unique per record (matplotlib) |
| 6 | **Quality Score Trend** | KPI metrics row (Overall Score, Evidence Grounding, Canonicalization, Geo Determinism with run-over-run deltas) + Altair line chart of Overall / Record / Brief scores over time, threshold lines at 80 (good) and 60 (warning) |
| 7 | **Drilldown table** | Filterable record list: title, source, priority, confidence, review_status, publish_date, `is_duplicate` + CSV download |

**Modules:** `src.storage`, `src.dedupe` (canonical mode toggle in sidebar), `src.quality` (`QUALITY_RUNS_LOG`, `_read_jsonl`), `src.ui_helpers`, `altair`, `matplotlib`

---

### Page 08 — Admin (`pages/08_Admin.py`)

**UI:** Canonical vs all records toggle with deduplication metrics. CSV export (flat, approved-only option). Bulk JSONL export to `data/canonical.jsonl` + `data/duplicates.jsonl`. "Danger Zone" — wipe all records (demo reset, requires confirmation checkbox).

**Modules:** `src.storage` (`load_records`, `overwrite_records`, `RECORDS_PATH`), `src.dedupe` (`dedupe_records`)

---

## Shared `src/` module reference

| Module | Role |
|---|---|
| `src.storage` | Append-only JSONL record persistence (`load_records`, `overwrite_records`, `save_pdf_bytes`) |
| `src.dedupe` | Same-story detection, canonical selection, `is_duplicate` flag, publisher scoring |
| `src.postprocess` | Deterministic normalization — company, region, priority, confidence, macro themes. **Architecture boundary:** only module that sets computed fields |
| `src.model_router` | LLM routing — Gemini primary, schema-enforced JSON output, 2-stage repair, chunked mode |
| `src.text_clean_chunk` | PDF text cleaning (14 drop rules) + chunking (9k chars, 800-char overlap) |
| `src.briefing` | Brief generation — deterministic Markdown + LLM synthesis + email render |
| `src.quality` | Post-hoc QC KPIs (R1–R5, B1–B5), trend tracking, feedback loop, JSONL run log |
| `src.schema_validate` | Hard validation gate against canonical schema constraints |
| `src.render_brief` | Per-record intelligence brief renderer |
| `src.pdf_extract` | PDF → text (PyMuPDF → pdfplumber fallback, no OCR) + publish date hint |
| `src.context_pack` | Context window selection / truncation for LLM prompt |
| `src.quota_tracker` | Daily API call tracking per model, reset at midnight PT |
| `src.ui_helpers` | Shared widgets (`workflow_ribbon`, `normalize_review_status`, `safe_list`, `join_list`, `best_record_link`) |
| `src.constants` | Canonical lists: `CANON_TOPICS`, `FOOTPRINT_REGIONS`, `DISPLAY_REGIONS`, `PREMIUM_OEMS`, `MACRO_THEME_RULES`, `REQUIRED_KEYS` |
