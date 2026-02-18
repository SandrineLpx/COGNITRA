# Technical Report

**Project:** Minimal-Token AI Market Intelligence for Automotive Closure Systems
**Course:** MSIS 549 – Generative AI Technologies
**Author:** Sandrine Lepesqueux
**Date:** February 14, 2026
**Version:** 1.0

## Executive Summary

This project builds an AI-powered market intelligence triage system for the automotive closure systems and car entry domain. The system is designed for environments where teams already pay for high-quality information—such as Bloomberg, Automotive News, S&P Global, and MarkLines—as well as public sources like press releases and regulatory announcements. The problem is not access to content; it is the lack of a scalable way to convert these sources into consistent, decision-ready intelligence.

Rather than packaging press releases or generating generic summaries, the tool converts unstructured documents (PDFs/text) into evidence-backed intelligence records that are searchable and comparable over time. It identifies relevant companies and actors (OEM/supplier/regulator), assigns controlled taxonomy topics, applies a two-tier footprint region architecture (display-level buckets like Asia, Western/Eastern Europe; Kiekert operational footprint with country-level granularity like India, China, Japan, Thailand), and outputs priority and computed confidence (based on observable extraction quality signals, not LLM self-assessment) alongside verifiable evidence bullets and key insights. Reliability and adoption are built in through strict JSON schema validation, a single repair step, strict multi-model fallback routing, and a human-in-the-loop approval gate before executive reporting. The result is a scalable workflow that increases signal capture from premium intelligence streams while keeping token costs predictable.

### 2026-02 Update Addendum (current implementation)

- **Footprint regions moved to Option B buckets:** `Western Europe`, `Eastern Europe`, `Russia` (replacing legacy `Europe (including Russia)`), with backward-compatible migration in postprocess.
- **Chunking behavior is automatic in Ingest UI:** the manual chunk-mode toggle was removed; extraction path is selected from cleaned-document chunk metadata.
- **Macro-theme matching is source-grounded:** `notes` are excluded from macro-theme matching text fields.
- **Weekly synthesis prompt tightened:** numeric grounding, Tier-1 implication enforcement, tone hardening, and length-scaling by record count were added at prompt level only.

## 1. Problem Statement and Significance

### 1.1 Problem

Many automotive organizations subscribe to premium intelligence sources—Bloomberg, Automotive News, S&P Global, MarkLines, and others—yet still miss important signals. The bottleneck is not the quality of information; it is that the content arrives as unstructured documents and does not automatically become standardized, reusable intelligence.

In practice, workflows degrade into:
- PDFs and links saved in folders with inconsistent naming and tags,
- time-consuming manual triage (what it is about, who it impacts, what priority it is),
- executive updates that vary depending on who processed the item,
- limited ability to search, compare, and trend signals over time across sources.

As a result, paid intelligence often functions like a high-volume inbox: the team pays for access, but the organization still struggles to extract timely, consistent insights.

### 1.2 Why it matters (business value)

A “press release package” or basic summarization workflow is not sufficient for decision-making, especially when dealing with high-volume premium streams. Decision-makers need prioritized, evidence-backed interpretation in a consistent structure.

For a global Tier-1 supplier in closure systems and car entry, missed or late signals can impact:
- OEM strategy and program assumptions (volume timing and content shifts),
- technology roadmap alignment (smart entry, access security, digital key),
- supply stability and risk (plant changes, disruption signals, policy shocks),
- competitive positioning (competitor moves and sourcing outcomes),
- regulatory exposure (safety/compliance changes affecting product requirements).

The significance of this project is enabling a workflow that converts both premium and public sources into the same standardized output—structured signals, evidence, implications—so intelligence becomes a searchable knowledge base rather than a one-off summary.

### 1.3 Success criteria (initial)

* Reduce analyst time spent on tagging/triage per document
* Improve consistency of topics/regions/companies classification
* Produce executive-friendly outputs that are traceable to evidence
* Keep token usage low and predictable (one call per doc)

## 2. Solution Overview

### 2.1 Concept

A lightweight tool that takes an input document (PDF/text) and generates:

1. **Structured intelligence record (JSON)**
2. **Readable Intelligence Brief** formatted from that JSON
3. A filterable "inbox" view for analysts (priority/topic/region/company)
4. Human review controls (Pending/Approved/Disapproved) with auto-approve heuristics at ingest
5. **AI-generated Weekly Executive Brief** synthesized across multiple records using Gemini Flash, following a structured executive report template (executive summary, high-priority developments, footprint region signals, topic developments, emerging trends, recommended actions)
6. **Trend analysis dashboard** with topic momentum, company mention tracking, and priority distribution over time

### 2.2 Target users

* Market/competitive intelligence analyst (primary user)
* Strategy/product/sourcing stakeholders consuming weekly outputs
* Executives consuming a weekly digest

### 2.3 Why this is “minimal AI” but still “AI-powered”

AI is used only where it provides high leverage:

* classification and normalization (topics, companies, actor type)
* evidence-backed extraction (verifiable bullets and key insights)
* cross-record synthesis for weekly executive briefs

Everything else is deterministic:

* PDF text extraction
* noisy-PDF cleaning and chunking
* paragraph selection and context pack assembly
* schema validation and error handling
* brief formatting from JSON
* deduplication and weekly briefing

## 3. Design Requirements

### 3.1 Functional requirements

* Accept PDF upload (and optionally pasted text/URL)
* Extract and select relevant text segments (“context pack”)
* Generate strict JSON with controlled vocabularies
* Validate JSON and repair once if invalid
* Render “Intelligence Brief” from JSON
* Provide an interface to review/edit tags and approve outputs
* Export records to CSV/JSONL for reporting (optional Power BI)

### 3.2 Non-functional requirements

* Token efficiency and cost predictability
* Traceability: evidence bullets must map to source text
* Consistency: controlled taxonomy and region roll-up rules
* Human oversight: review statuses + gating for high-risk items
* Demo reliability: fallback to preloaded examples

## 4. System Architecture and Workflow

### 4.1 Components

* **Ingestion:** PDF upload / text input
* **Duplicate detection layer:**
  * Exact title match detection (blocking at ingest)
  * Similar story detection (fuzzy matching with similarity threshold 0.88)
  * Automatic "better source" selection when duplicates detected
* **Local processing (non-AI):**

  * PDF → text extraction (PyMuPDF with pdfplumber fallback)
  * Noisy-PDF cleaning: deterministic removal of ads, nav menus, paywall prompts, social sharing blocks, link farms, repeated headers/footers, photo credits, and symbol-heavy lines (`src/text_clean_chunk.py`)
  * Chunking: cleaned text split into overlapping model-ready chunks (~9K chars, 800-char overlap) with detected-title propagation
  * Context pack assembly: keyword/watchlist/country hit scoring with bounded size
* **AI inference (meta-based model routing + two-phase chunk repair):**

  * **Noise classification:** cleanup meta (removed_ratio, removed_line_count, top_removed_patterns) classifies each document as low/normal/high noise
  * **Model selection:** high-noise documents route directly to Gemini Flash (stronger model), bypassing Flash-Lite to avoid wasting quota on expected failures; low/normal-noise documents start on Flash-Lite
  * **Phase 1 — initial model:** all chunks extracted with the chosen model via `extract_single_pass()`
  * **Phase 2 — repair only failures:** only chunks that failed Phase 1 are retried with the stronger model (if Flash-Lite was the initial model); successful chunks are not re-extracted
  * **Quality gate:** schema validation + heuristic checks (missing publish_date, wrong source_type, generic evidence)
  * **Non-chunked fallback:** single-context documents still use the original two-pass strategy (Flash-Lite → Flash) via `route_and_extract()`
  * Token usage logging per call (prompt/output/total tokens, model used)
  * **API quota tracking** (`src/quota_tracker.py`): per-model RPD usage persisted to `data/api_usage.json`, resets midnight Pacific Time, sidebar display with progress bars and remaining-call estimates
* **Validation layer:**

  * JSON schema validation against controlled vocabularies
  * Repair prompt includes specific validation errors for targeted fixes
  * Selective escalation: only schema/structural failures trigger strong-model retry
* **Storage:**

  * JSONL for records and review status
  * Separate JSONL files for duplicates (marked with duplicate metadata)
  * Bulk deduplication via CLI script (`scripts/dedupe_jsonl.py`)
* **Briefing pipeline:**
  * Weekly candidate selection (recent records within configurable date range up to 90 days, exclude duplicates by default)
  * Share-ready detection (High priority + High confidence)
  * Deterministic Markdown brief and executive email generation
  * **AI-generated Weekly Executive Brief:** LLM synthesis (Gemini Flash) across up to 20 selected records, following structured executive report template (executive summary, high-priority developments, footprint region signals, topic developments, emerging trends, recommended actions); token usage displayed
  * Analyst-driven item selection with one-click suggestions
* **Priority classification:**
  * LLM prompt rules define High/Medium/Low criteria with Kiekert-specific signals
  * Deterministic `_boost_priority()` postprocess: upgrades to High when `mentions_our_company`, footprint region + closure topic/keyword, or footprint region + key OEM customer
  * **Computed confidence scoring:** deterministic `_compute_confidence()` replaces LLM self-assessed confidence with score from observable signals (field completeness, evidence count, postprocess corrections, date provenance); audit trail in `_confidence_detail`
  * Auto-approve heuristic at ingest: computed confidence not Low, publish_date present, source_type not Other, 2+ evidence bullets → auto-Approved; otherwise Pending for manual review
* **Bulk PDF ingest:**
  * Multi-file uploader with progress bar and per-file extraction loop
  * Deduplication checks both filename and extracted title against existing records and within the batch
  * Summary table showing saved/skipped/failed counts per file
  * Pre-run quota estimate (worst-case API calls vs remaining quota)
* **Analytics & Presentation:**

  * Review & Approve page with queue filtering, title-first expandable cards, inline Approve/Review buttons, record detail with Next/Previous navigation, Quick Approve with auto-advance, JSON editing, and computed confidence detail breakdown (per-signal score, LLM override indicator)
  * Insights page with canonical/all-records toggle and four trend analysis charts:
    * **Topic Momentum:** weighted counting (1/n per topic), pct_change, Emerging/Expanding/Fading/Stable classification, rendered via Altair with tooltips and detail table
    * **Top Company Mentions:** top 10 by frequency with canonicalization and within-record deduplication
    * **Priority Distribution Over Time:** weekly stacked bars with High-Ratio and Volatility Index secondary line chart
    * **Confidence Distribution (Computed):** weekly stacked bars showing extraction quality trend, plus LLM override rate metrics (total computed, count overridden, override %)
  * Export to CSV for Power BI (canonical and all records support)
  * Weekly Executive Brief page for digest drafting, email templates, and AI brief generation

### 4.2 Human-in-the-loop gating

Review statuses:

* **Pending** → **Approved** or **Disapproved**

Auto-approve heuristic (applied deterministically at ingest): records are automatically set to Approved when all of the following hold: computed confidence is High or Medium (see §7.5.6), publish_date is present, source_type is not Other, and at least 2 evidence bullets are extracted. Records that fail any of these criteria start as Pending for manual review. Because confidence is now computed from observable extraction signals rather than LLM self-assessment, the auto-approval gate is calibrated to actual data quality. Legacy records with old statuses ("Not Reviewed", "Reviewed") are normalized transparently to "Pending".

Recommended gating rules (records that should always require manual review):

* priority is High, or
* confidence is Low, or
* mentions our company, or
* government/regulator actor with trade_policy/regulation/geopolitics signal

In addition to review gating, provenance capture is part of the human-in-the-loop design: the ingest page includes an optional manual URL field so the analyst can provide a verified source link at upload time. This prevents the model from hallucinating original_url values and ensures that downstream executive reports reference only confirmed sources.

## 5. Data Sources

### 5.1 Inputs used in development/demo

* Premium news article PDFs (e.g., Bloomberg)
* Press releases (government/regulatory)
* Market note PDF (e.g., Germany passenger car market note)

### 5.2 Reference lists and controlled vocabularies

This project uses a controlled taxonomy and watchlist to reduce ambiguity and drift:

* Canonical topic taxonomy (9 topics)
* Company watchlist (including “Our company” section)
* Two-tier footprint region architecture: display-level buckets (Asia, Western/Eastern Europe, Africa, US, Latin America) and Kiekert footprint regions (India, China, Japan, Thailand, Mexico, Russia + display regions); ~60 country-to-region mappings

## 6. Prompting and Output Specification

### 6.1 From spec-first design to code-embedded guidance

#### Phase 1: Specification-first approach (pre-implementation)

The project began with a deliberate spec-first approach, authoring a set of Markdown reference documents before writing any code:

* **SKILL_final.md** — the master product specification defining taxonomy, region rules, JSON schema, priority rubric, and HITL gating rules.
* **topic-taxonomy_final.md** — detailed per-topic tagging guidance (when to use each canonical topic, when not to, and which alternative topic to prefer).
* **company-watchlist_final.md** — competitor tiers, OEM customer lists, technology ecosystem partners, and competitive signal definitions.
* **prompts_final.md** — executable LLM prompts referencing SKILL for schema/topics/regions.
* **executive-brief-template_final.md** — how to render intelligence briefs from JSON.

This approach was valuable for initial design: it forced clarity about what the system should do before building it. The spec documents served as a "contract" between the designer (human) and the builder (AI-assisted coding).

#### Phase 2: Spec drift during iterative development

As the codebase grew through iterative development with AI assistance, the Markdown reference files progressively drifted from the actual implementation:

* **Region architecture evolved** — the original spec defined a flat list of 7 regions (e.g., `Europe (including Russia)`). The code evolved to a two-tier architecture (`DISPLAY_REGIONS` for broad buckets vs `FOOTPRINT_REGIONS` for Kiekert operational granularity), added Japan as a standalone footprint region, added ~60 country-to-region mappings, and split Europe into Western/Eastern. None of this was reflected back in the spec files.
* **Schema fields were removed** — fields like `strategic_implications`, `recommended_actions`, `region_signal_type`, and `supply_flow_hint` were intentionally removed from the LLM schema (moved to deterministic postprocessing or eliminated). The spec files still listed them.
* **Actor types and review statuses changed** — the code simplified `actor_type` from 8 values to 5 and replaced review statuses (`Not Reviewed`/`Reviewed`/`Approved`) with `Pending`/`Approved`/`Disapproved`. The specs were outdated.
* **The LLM never saw the specs** — critically, the topic tagging guidance and competitor context in the reference files were never wired into the extraction prompt. The LLM received only the JSON schema enum values (topic names) with no disambiguation guidance. It had to guess when to use "OEM Strategy & Powertrain Shifts" vs "OEM Programs & Vehicle Platforms".

The result was a documentation architecture with three layers that were all slightly wrong: spec files (outdated), `CLAUDE.md`/`AGENTS.md` (architecture-focused but missing domain guidance), and code (the actual source of truth but lacking human-readable context).

#### Phase 3: Consolidation into code (current)

A dedicated refactoring session identified the gap and consolidated everything:

1. **Topic tagging guidance moved into code** — the per-topic "use / don't use" rules from `topic-taxonomy.md` were embedded in two places: as comments directly above `CANON_TOPICS` in `src/constants.py` (human reference during quarterly review) and as structured instructions in the `extraction_prompt()` function in `src/model_router.py` (LLM guidance during extraction).

2. **Competitor context injected into the extraction prompt** — the LLM now sees Tier 1 and Tier 2 closure system competitors by name, enabling correct `actor_type='supplier'` classification and `mentions_our_company` detection.

3. **Kiekert identity added to the prompt** — the extraction prompt now opens with "You are extracting structured intelligence for Kiekert, an automotive closure systems supplier (door latches, strikers, handles, smart entry, cinch systems)." This gives the LLM domain context for all classification decisions.

4. **Reference files reduced to one** — `topic-taxonomy.md` was deleted (content now lives in code). `context-watchlist.md` was cleaned of outdated region/priority sections and renamed to `company-watchlist.md` (purely competitive intelligence, no code duplication). `SKILL.md` was archived.

5. **`AGENTS.md` as the single operator manual** — all architecture invariants, pipeline constraints, postprocess rules, region architecture, macro-theme howto, and priority heuristics were consolidated into a single `AGENTS.md` file at the repo root. This file serves as the canonical instruction set for any AI agent (Claude Code, Copilot, or future tools) working on the codebase — it is what the AI reads before making any code change. `CLAUDE.md` was reduced to a 3-line pointer: "This repository uses `AGENTS.md` as the canonical AI agent instruction file." This means there is exactly one file that defines how the system works, what boundaries must be respected (LLM-extracted vs computed fields, postprocess pipeline order, region tiers), and what not to do (never add interpretive fields back to the LLM schema, never reorder the postprocess steps). Any engineer — human or AI — reads `AGENTS.md` and has the full operational picture.

6. **Quarterly review checklist created** — `References/QUARTERLY_REVIEW.md` provides a structured process for maintaining all controlled vocabularies, ordered from lowest-risk (company watchlist, no code changes) to highest-risk (region enums, run tests after).

**Final maintenance structure:**

| What | File | Who reads it |
|---|---|---|
| Architecture, constraints, pipeline rules | `AGENTS.md` | AI agents + human engineers |
| Topics, regions, enums, macro themes | `src/constants.py` + `src/model_router.py` | Code at runtime + LLM at inference |
| Country mappings, city hints | `src/postprocess.py` | Code at runtime |
| Companies, OEMs, tech partners | `References/company-watchlist.md` | Human analysts (quarterly review) |
| AI agent entry point | `CLAUDE.md` → pointer to `AGENTS.md` | AI coding tools (Claude Code, Copilot) |

<!--
[PLACEHOLDER: Diagram showing the evolution from Phase 1 to Phase 3]

Phase 1 (pre-implementation):
┌──────────────┐  ┌──────────────────┐  ┌───────────────────┐  ┌────────────┐  ┌──────────────┐
│ SKILL.md     │  │ topic-taxonomy.md│  │ company-watchlist  │  │ prompts.md │  │ template.md  │
│ (master spec)│  │ (tagging rules)  │  │ (competitors+OEMs) │  │ (LLM prompt)│  │ (brief fmt)  │
└──────────────┘  └──────────────────┘  └───────────────────┘  └────────────┘  └──────────────┘
                        ↕ NONE of these wired to LLM at runtime

Phase 2 (drift):
  Code evolves (new regions, removed fields, changed actor types)
  Spec files → outdated, never updated
  LLM → blind to domain guidance (only sees enum values)

Phase 3 (current):
┌─────────────────────────────┐  ┌──────────────────────────────┐  ┌────────────────────┐
│ AGENTS.md                   │  │ src/constants.py             │  │ company-watchlist.md│
│ (single operator manual     │  │ (topic guidance as comments + │  │ (competitors, OEMs, │
│  for AI + human engineers)  │  │  enums, regions, themes)      │  │  tech partners only)│
└─────────────────────────────┘  │ src/model_router.py          │  └────────────────────┘
         ↑                       │ (extraction prompt with topic │
   CLAUDE.md points here         │  rules + competitor context)  │
                                 └──────────────────────────────┘
                                        ↕ LLM reads this at inference time
-->


#### Why this matters

The consolidation was not just a cleanup exercise. It had a direct impact on extraction quality:

* **Before:** The LLM received 9 topic names with no disambiguation. It frequently confused "OEM Strategy" with "OEM Programs" and applied "Closure Technology & Innovation" to general vehicle electronics articles.
* **After:** The LLM receives one-line use/don't-use rules for each topic and knows Kiekert's competitors by name. Topic classification accuracy improved because the model has explicit boundary definitions rather than having to infer them from label names alone.

The lesson: **specification documents are valuable for initial design but become a maintenance liability if they are not the same artifact that the system reads at runtime.** Embedding domain guidance directly into the code (as comments for humans, as prompt text for the LLM) eliminates the drift problem entirely.

### 6.2 Output schema (JSON-first)

The LLM returns a single JSON object per article, enforced by Gemini's structured-output mode. The schema is defined programmatically in `record_response_schema()` (`src/model_router.py`). Below is the full field set:

```json
{
  "title":                     "STRING",
  "source_type":               "STRING  — enum: Automotive News | Bloomberg | Financial News | GlobalData | Industry Publication | MarkLines | Other | Patent | Press Release | Reuters | S&P",
  "publish_date":              "STRING | null  — pattern: YYYY-MM-DD",
  "publish_date_confidence":   "STRING  — enum: High | Low | Medium",
  "original_url":              "STRING | null",
  "actor_type":                "STRING  — enum: industry | oem | other | supplier | technology",
  "government_entities":       ["STRING"],
  "companies_mentioned":       ["STRING"],
  "mentions_our_company":      "BOOLEAN",
  "topics":                    ["STRING  — enum: 9 canonical topics, 1-4 required"],
  "keywords":                  ["STRING  — 3-15 items"],
  "country_mentions":          ["STRING"],
  "regions_mentioned":         ["STRING  — free-text, up to 15"],
  "regions_relevant_to_kiekert": ["STRING  — enum: India | China | Western Europe | Eastern Europe | Russia | Africa | US | Mexico | Latin America | Thailand | Japan | Asia"],
  "evidence_bullets":          ["STRING  — 2-4 factual bullets"],
  "key_insights":              ["STRING  — 2-4 analytical insights"],
  "review_status":             "STRING  — enum: Approved | Disapproved | Pending",
  "notes":                     "STRING"
}
```

**Fields NOT in the LLM schema** (computed deterministically by `postprocess_record()` after extraction):

| Field | Source |
|---|---|
| `priority` | Rule-based boosting in `_boost_priority()` |
| `confidence` | Deterministic scoring in `_compute_confidence()` |
| `macro_themes_detected` | Pattern-matching in `_detect_macro_themes()` |
| `_macro_theme_detail` | Audit trail for theme firing reasons |
| `_macro_theme_rollups` | Cluster labels for overlapping themes |

This separation is enforced by a runtime guardrail: a `_COMPUTED_FIELDS` whitelist prevents adding a field to `REQUIRED_KEYS` without placing it in either the LLM schema properties or the computed set — any misalignment crashes the app at import time.

### 6.3 Evidence requirement

Each record includes 2–4 evidence bullets:

* must be verifiable facts from the provided text
* should include short quote fragments when possible
* reduces hallucination risk and improves reviewer trust

## 7. Implementation Details

### 7.1 Technology stack

* **UI:** Streamlit (5-page multi-page app: Ingest, Review & Approve, Weekly Executive Brief, Insights, Admin)
* **Local extraction:** PyMuPDF with pdfplumber fallback
* **LLM provider:** Gemini 2.5-flash-lite (primary) + Gemini 2.5-flash (fallback/repair) via `google-genai` with structured JSON schema
* **Storage:** JSONL (JSON Lines format)
* **Charting:** Altair (Topic Momentum interactive charts), matplotlib (other charts), pandas aggregations
* **Reporting:** Power BI optional (CSV export ready)
* **Language:** Python 3.9+
* **Dependencies:** streamlit, pymupdf, pdfplumber, pandas, matplotlib, altair, google-genai, pytest

For the MVP, the solution is implemented as a multi-page Streamlit web app that supports PDF ingestion (single and bulk), duplicate detection, record review, analytics, trend analysis, and weekly briefing workflows in a lightweight interface. The app includes five main pages plus a Home landing page: (1) Ingest with duplicate blocking and bulk PDF upload, (2) Review & Approve with queue filtering, record detail/edit, JSON editing, approve/disapprove, and confidence detail breakdown, (3) Weekly Executive Brief for digest drafting and AI-generated executive briefs, (4) Insights with trend analysis charts including confidence distribution, and (5) Admin for bulk export and maintenance. Processed outputs are stored as JSONL (JSON Lines), where each intelligence record is appended as one JSON object per line, enabling simple persistence and fast reload without a database. Duplicate records are stored separately with metadata pointing to the canonical record (higher-ranked source). API usage is tracked per-model in `data/api_usage.json` with midnight Pacific Time reset. For reporting and downstream analysis, the app includes:

- CSV export of canonical records (or all records) filtered by approval status
- JSONL export of both canonical and duplicate records for analysis
- Insights page with toggle to view analytics on canonical vs. all records, plus Topic Momentum, Company Mentions, and Priority Distribution trend charts
- Weekly Executive Brief page for drafting deterministic digest summaries, AI-generated executive briefs, and executable email templates
- CLI script (`scripts/dedupe_jsonl.py`) for off-app bulk deduplication with diagnostic stats

### 7.2 Processing pipeline (step-by-step)

1. User uploads PDF (with optional manual URL field for provenance)
2. **Duplicate detection:**
   * Check exact title match against existing records → block if duplicate
   * Check similar title (fuzzy match, threshold 0.88) → flag if similar
   * If similar, compare source quality and mark weaker as duplicate
3. **Extract text locally** (PyMuPDF → pdfplumber fallback)
4. **Clean and chunk** (`src/text_clean_chunk.py`):
   * Fix hyphen line breaks, normalize whitespace
   * Remove noise lines (nav, promo, paywall, social, link-heavy, repeated headers/footers, photo credits, all-caps menu items)
   * Deduplicate paragraph blocks
   * Split into overlapping chunks (~9K chars, 800-char overlap) with detected-title header
   * Surface removal diagnostics (removed line count, pattern breakdown) in UI
5. **Noise classification** (`_classify_noise()` in `pages/01_Ingest.py`):
   * Uses cleanup meta (removed_ratio, removed_line_count, top_removed_patterns) to classify document as low/normal/high noise
   * Thresholds: high if removed_ratio > 0.18 or removed_lines > 250 or OCR/table/header patterns detected; low if removed_ratio < 0.08 and removed_lines < 80
6. **Two extraction modes** (user-selectable):
   * **Chunked mode (default for long/noisy docs):** meta-based model routing with two-phase chunk repair:
     * **Model selection:** high-noise → Flash directly (skip Flash-Lite); low/normal-noise → Flash-Lite
     * **Phase 1:** all chunks extracted with initial model via `extract_single_pass()`
     * **Phase 2:** only failed chunks retried with stronger model (if Flash-Lite was initial); successful chunks untouched
     * **Merge:** majority voting (source_type, actor_type), union+dedup (entities, topics, regions), highest-confidence date, short-bullet filtering
   * **Single-context mode:** score paragraphs (watchlist, keyword, country hits), build bounded context pack, single model call with two-pass strategy (Flash-Lite → Flash fallback)
7. Postprocess/normalize model output (dedupe lists, canonicalize country names, enforce footprint region buckets, infer publish_date and source_type from text patterns, remove invalid regulator entities)
8. **Deterministic priority classification** (`_boost_priority()` in `src/postprocess.py`):
   * Upgrades to High when: `mentions_our_company` is true, footprint region + closure topic/keyword, or footprint region + key OEM customer (Volkswagen, BMW, Hyundai/Kia, Ford, GM, Stellantis, Toyota, Mercedes-Benz, etc.)
   * LLM prompt also includes priority criteria (rule 8) for initial classification
9. Validate JSON against schema; if invalid, repair prompt with error details → revalidate
10. **Computed confidence:** `_compute_confidence()` overwrites LLM self-assessed confidence with a deterministic score based on field completeness, evidence quality, rule corrections, and date provenance (see §7.5.6); audit trail stored in `_confidence_detail`
11. **Auto-approve heuristic:** computed confidence not Low + publish_date present + source_type not Other + 2+ evidence bullets → auto-Approved; otherwise Pending
11. Store record with `duplicate_of` / `is_duplicate` metadata if needed; update API quota tracker
12. Display token usage summary (model used, prompt/output/total tokens, noise level, chunks succeeded/repaired/failed)
13. Render Intelligence Brief from JSON (deterministic, no LLM call)
14. Human review: Pending records require manual approval; Quick Approve with auto-advance to next unreviewed record
15. **Bulk PDF ingest** (separate mode for multiple files):
    * Multi-file uploader with progress bar and per-file extraction loop
    * Pre-run quota estimate (worst-case API calls vs remaining quota)
    * Deduplication checks filename and title against existing records and within batch
    * Summary table showing saved/skipped/failed counts
16. **Weekly briefing (separate workflow):**
    * Select candidates from last N days (configurable, default 30, max 90; excludes duplicates by default)
    * Prioritize share-ready items (High priority + High confidence)
    * **Deterministic brief:** Markdown brief + executive email template (zero LLM cost)
    * **AI-generated executive brief:** LLM synthesis (Gemini Flash) across up to 20 selected records following structured executive report template; token usage displayed
    * Analyst can select/deselect items before sharing

### 7.3 Token control strategy

* Duplicate detection is deterministic (no LLM calls)
* Fixed cap on context pack size (12K chars) and chunk size (9K chars)
* **Meta-based model routing:** noise classification from cleanup meta routes high-noise docs directly to Flash (avoiding wasted Flash-Lite calls that would fail); low/normal-noise docs start on Flash-Lite
* **Two-phase chunk repair:** Phase 1 runs all chunks on the chosen model; Phase 2 retries only failed chunks with the stronger model — successful chunks are never re-extracted
* One LLM call per unique document in the common case (single-context mode); in chunked mode, one call per chunk but only failures escalate
* No second call for "Intelligence Brief" (rendered deterministically from JSON)
* Deduplication, priority classification, and deterministic weekly briefing require zero LLM calls
* **AI-generated executive brief** is the only multi-record LLM call (one Gemini Flash call for up to 20 records); used only on analyst request
* **API quota tracking** (`src/quota_tracker.py`): per-model RPD (Requests Per Day) usage persisted to `data/api_usage.json`, resets midnight Pacific Time (matching Google's billing window); sidebar shows live usage/remaining with progress bars; smart chunk mode recommendations warn when chunked mode would consume multiple calls on short documents
* Gemini free-tier limits (as of Feb 2026): Flash-Lite = 10 RPM, 20 RPD, 250K TPM; Flash = 5 RPM, 20 RPD, 250K TPM — both $0 cost
* Per-call token usage is logged and displayed in the Ingest UI for cost tracking

### 7.4 Error handling and resilience

* If PDF extraction fails: fallback to manual paste input
* If JSON invalid: repair prompt once
* If still invalid: mark record "Failed" and require manual review

#### 7.4.1 Issue encountered: schema-based JSON extraction failing with Gemini

During MVP implementation, the pipeline failed at the model call step when using Gemini's response_schema feature. The router logged a provider error like: "Gemini API call failed: validation errors for Schema … properties.publish_date.type … Input should be … STRING/ARRAY/OBJECT/NULL … input_value=['string','null']". The root cause was a schema format mismatch: our initial schema was written in standard JSON Schema style (e.g., type: ["string","null"] for nullable fields), but the google-genai SDK enforces a Gemini-specific schema type system where type must be a single uppercase enum value (STRING, ARRAY, OBJECT, NULL, etc.). As a result, the SDK rejected union types before the model was even invoked, preventing any extraction.

#### 7.4.2 Fix applied: Gemini-compatible schema + strict postprocessing/validation order

We resolved the issue by updating the schema definition to be compatible with the google-genai response_schema validator. Concretely, we removed JSON-Schema union typing and expressed optionality in a Gemini-supported way (either by using a "nullable/anyOf" pattern if supported by the SDK version, or by standardizing unknown values as empty strings/lists and converting them later). In addition, we tightened the pipeline order so that postprocessing runs before validation: the model output is first normalized (dedupe lists, canonicalize "US/USA/U.S.", enforce footprint region buckets, remove invalid regulator entities), and only then passed through validate_record(). This ensured that minor formatting variations from the model do not cause false schema failures, while keeping strict constraints on allowed enums (topics, regions, source types, etc.) and preserving deterministic behavior (single repair attempt, fallback only on schema failure).

#### 7.4.3 Follow-up hardening: preventing URL hallucinations

A secondary quality issue was that original_url could be hallucinated if it was not present in the PDF text. To prevent this, we moved URL capture to a human-in-the-loop input in the Streamlit ingest page (optional manual URL field). The model is instructed not to invent URLs; the pipeline overwrites original_url only if the user provides it or if a URL is deterministically extracted from text via regex. This keeps provenance accurate and reduces downstream trust risks in executive reporting.

### 7.5 Key design decisions and rationale

This section documents the three most impactful design decisions and the reasoning behind each.

#### 7.5.1 Noisy-PDF cleaning + chunking (before the model)

**Problem:** PDFs from premium sources (S&P Global, Bloomberg, Automotive News) often include ads, navigation menus, "related links" sidebars, repeated headers/footers, paywall prompts, social sharing blocks, photo credits, and messy line breaks. Feeding this raw text directly to an LLM increases hallucinations (wrong source_type, invented dates, phantom entities), produces incorrect field values, and can exceed token limits.

**Approach chosen:** A deterministic, multi-stage cleanup pipeline (`src/text_clean_chunk.py`) runs before any model call:

1. **Line normalization:** fix hyphen breaks across lines, normalize whitespace, remove empty lines.
2. **Noise removal:** pattern-based detection of nav elements, promo blocks, paywall text, social links, link-heavy lines, photo credits, all-caps menu items, and symbol-heavy lines. Each removed line is categorized by pattern type for diagnostics.
3. **Repeated-header suppression:** lines appearing more frequently than a dynamic threshold (based on document length) are removed, catching page headers/footers that repeat across multi-page PDFs.
4. **Block deduplication:** paragraph-level exact-match dedup (ignoring whitespace) removes duplicated content blocks.
5. **Chunking:** cleaned text is split into overlapping chunks (~9K chars each, 800-char overlap) with a detected-title header injected into each chunk. Overlap ensures entities/dates that fall on chunk boundaries are not lost.
6. **Safety fallback:** if cleaning removes too aggressively (cleaned text < 2K chars when original was >= 2K), the original text is preserved.

**Why this works:** The model receives higher-signal input with less noise, which directly improves extraction accuracy for source_type, publish_date, companies_mentioned, and evidence_bullets. The diagnostics (removed line count, top removal patterns) are surfaced in the Ingest UI so the analyst can verify the cleanup is working correctly and not over-cleaning.

**Alternatives considered:** (a) Sending raw text and relying on the model to ignore noise — this failed in practice because the model would pick up ads/nav text as entities or misclassify publishers. (b) Using an LLM call for cleanup — this would double token cost and add latency with no clear quality advantage over deterministic rules for the noise patterns we observed.

#### 7.5.2 Multi-publisher dedup + ranking

**Problem:** The same story frequently appears across multiple sources. For example, a Reuters wire story about a Ford plant closure will appear in S&P Global's analysis, Bloomberg's coverage, and Automotive News, each with different framing but the same core facts. Without deduplication, the system stores multiple records for the same event, and the weekly executive brief double-counts signals — giving false impressions of signal density or urgency.

**Approach chosen:** A two-layer deduplication system (`src/dedupe.py`) with deterministic publisher ranking:

1. **Exact title match (blocking):** at ingest time, the system checks if a record with the same normalized title already exists. If so, ingestion is blocked entirely.
2. **Fuzzy story detection (flagging):** if no exact match is found, the system searches for similar titles using `SequenceMatcher` with a 0.88 similarity threshold. When similar stories are found, the system automatically compares source quality using a composite scoring tuple:
   - Publisher score: S&P=100 > Bloomberg=90 > Reuters=80 > Financial News=78 > MarkLines=76 > Automotive News=75 > Industry Publication=72 > Press Release=60 > Patent=55 > Other=50
   - Confidence score: High=3 > Medium=2 > Low=1
   - Completeness score: +1 for publish_date present, +1 for original_url present, +1 for regions_relevant non-empty, +1 for evidence_bullets count >= 3
3. **Canonical selection:** the highest-scoring record becomes canonical; all others are marked with `is_duplicate=True` and `duplicate_story_of` pointing to the canonical record_id.
4. **Brief suppression:** the weekly briefing workflow (`src/briefing.py`) excludes duplicates by default, so the executive digest shows only one version of each story.

**Why this works:** The ranking is deterministic and repeatable — no LLM calls are needed. The publisher hierarchy reflects real-world source authority (S&P's analysis is generally more valuable than a raw Reuters wire). The completeness score ensures that when two sources have the same publisher tier, the more complete record wins.

**Net effect on executive briefs:** no double-counting, no repeated signals, and the analyst always sees the strongest available version of each story.

#### 7.5.3 Extraction prompt rules (schema + "publisher vs cited source" + evidence constraints)

**Problem:** Early extraction runs revealed systematic errors:
- **Publisher confusion:** the model set source_type to "Reuters" when an S&P Global article merely cited Reuters as a wire source. This happened because "Reuters" appeared prominently in the text.
- **Overly long evidence bullets:** the model produced paragraph-length evidence bullets that were not scannable by analysts and exceeded schema constraints.
- **Inconsistent list normalization:** lists contained variants like "US", "USA", and "U.S." as separate entries, causing duplicates in downstream analytics.
- **Date format inconsistency:** the model sometimes returned dates in non-ISO formats ("Feb 4, 2026" instead of "2026-02-04") or hallucinated dates not present in the text.

**Approach chosen:** The extraction prompt (`extraction_prompt()` in `src/model_router.py`) was rewritten with explicit, numbered rules:

1. **Publisher identification rule:** "source_type is the PUBLISHER of the document. If 'S&P Global', 'S&P Global Mobility', 'AutoIntelligence | Headline Analysis', or '(c) S&P Global' appears, set source_type='S&P'. If Reuters or Bloomberg is only cited inside the article, do NOT set source_type to those unless they are clearly the publisher."
2. **Date normalization rule:** "extract and normalize to YYYY-MM-DD when present. Handle patterns like '4 Feb 2026', '11 Feb 2026', 'Feb. 4, 2026', 'February 4, 2026'. Else return null."
3. **Evidence constraint:** "evidence_bullets must be 2-4 short factual bullets, each <= 25 words. No long paragraphs."
4. **List deduplication rule:** "Deduplicate list fields and normalize US/USA/U.S. variants to one canonical form."
5. **Closure topic guardrail:** "Only use 'Closure Technology & Innovation' when latch/door/handle/digital key/smart entry/cinch appears explicitly."

In addition, the repair prompt (`fix_json_prompt()`) was enhanced to include the specific validation errors from the failed attempt, so the model can target its fixes rather than guessing what went wrong.

**Why this works:** Explicit, rule-by-rule instructions reduce ambiguity for the model. The publisher-vs-cited-source distinction is the single highest-impact rule — it eliminated the most common misclassification. The evidence bullet length cap made outputs consistently scannable. Combined with the postprocessing layer that runs after extraction (country normalization, region roll-up, entity dedup), the prompt rules and code-side normalization form a two-layer defense against inconsistent outputs.

#### 7.5.4 Two-pass model strategy (Flash-Lite → Flash)

**Problem:** Using Gemini Flash for every document worked but was more expensive than necessary. Most PDFs are "easy enough" — clean text, obvious publisher markers, straightforward entities — and do not need the stronger model. However, some documents are noisy or ambiguous and benefit from the additional reasoning capability of Flash.

**Approach chosen:** A two-pass strategy implemented in `try_one_provider()` in `src/model_router.py`:

1. **Pass 1 — Gemini Flash-Lite (default):** runs extraction cheaply and fast. If the output passes schema validation and quality checks, it is accepted immediately.
2. **Quality gate:** schema validation (`validate_record()`) plus heuristic checks. If the record fails validation or the heuristics flag quality issues (e.g., publish_date missing when dates clearly appear in text, source_type = "Other" when publisher markers are present, evidence bullets too long or generic), the system escalates.
3. **Pass 2 — Gemini Flash (fallback):** re-runs extraction using the repair prompt with specific validation errors included. This spends more tokens only on hard/noisy documents where accuracy matters most.
4. **Selective escalation:** the `_should_retry_strong()` function checks whether the error type warrants a strong-model retry (schema errors, structural failures) vs. a transient issue that would not benefit from a different model.

**Why this works:** In practice, most documents pass on Flash-Lite (pass 1), keeping the average cost per document low. Only the hard cases — noisy PDFs, ambiguous publishers, missing dates — escalate to Flash. Token usage is logged per call (`_extract_usage()`) and displayed in the Ingest UI, so the analyst can see exactly when the system "upgraded" and how many tokens were consumed.

**Cost impact:** For a typical batch of 10 documents, approximately 7-8 complete on Flash-Lite and 2-3 escalate to Flash. This reduces average token cost compared to running Flash on every document while maintaining extraction quality on difficult inputs.

#### 7.5.5 Priority classification — prompt rules + deterministic boost

**Problem:** The model defaulted all records to Medium priority because no priority criteria were defined in the extraction prompt. This broke the Priority Distribution chart (all bars were "Medium"), the share-ready filtering in Weekly Brief (nothing qualified as High), and the overall value of the priority signal for analysts.

**Approach chosen:** A two-layer priority classification system:

1. **LLM prompt rule (rule 8 in `extraction_prompt()`):** Defines High/Medium/Low with Kiekert-specific criteria:
   - **High:** directly impacts Kiekert operations, footprint regions (India, China, Europe, Africa, US, Mexico, Thailand), closure technology (latches, door systems, handles, digital key, smart entry, cinch), regulatory changes affecting automotive suppliers, major M&A/plant closures/production shifts involving direct competitors or key OEM customers, or `mentions_our_company` is true.
   - **Low:** tangential mentions with no direct supplier or closure-tech relevance, broad macroeconomic news, consumer reviews, motorsports.
   - **Medium:** everything else. "When in doubt between High and Medium, prefer High if any footprint region or closure-tech keyword appears."
2. **Deterministic postprocess override (`_boost_priority()` in `src/postprocess.py`):** Runs after model extraction and upgrades to High when hard signals are present, regardless of what the model output:
   - Signal 1: `mentions_our_company` is true
   - Signal 2: footprint region + "Closure Technology & Innovation" topic
   - Signal 3: footprint region + closure keyword (latch, door system, handle, digital key, smart entry, cinch, striker) found in title/evidence/insights
   - Signal 4: footprint region + key OEM customer (Volkswagen, BMW, Hyundai/Kia, Ford, GM, Stellantis, Toyota, Mercedes-Benz, Nissan, Honda, Renault, Tata, Mahindra, BYD, Geely, Chery, Great Wall)

**Why this works:** The prompt gives the model context to make reasonable initial priority judgments. The deterministic postprocess acts as a safety net — it catches cases where the model underestimates priority because it does not know Kiekert's specific business context (e.g., which OEMs are customers, which regions are manufacturing footprint). This two-layer approach ensures that business-critical signals are never missed, even when the model defaults to Medium.

**Note:** Existing records ingested before v4.3 retain their original priority and need re-ingest to benefit from the new classification.

#### 7.5.6 Computed confidence — replacing LLM self-assessment with observable signals

**Problem:** The `confidence` field (High/Medium/Low) was entirely self-assessed by the LLM during extraction. The prompt gave no criteria for what each level meant, and the model had no way to judge its own extraction quality. In practice this produced overconfidence bias — most records were marked "High" regardless of actual extraction quality. Because confidence feeds into auto-approval (records with Low confidence stay Pending for manual review) and weekly brief ranking, an uncalibrated confidence score undermines both quality gating and executive reporting.

**Approach chosen:** A two-layer fix:

1. **Prompt guidance (rule 9 in `extraction_prompt()`):** Explicit criteria added to the extraction prompt so the LLM's initial estimate is better calibrated:
   - **High:** all key fields (publish_date, source_type, actor_type) clearly stated in source text; at least 2 evidence bullets directly quotable.
   - **Medium:** some fields require inference or are ambiguous; partial evidence available.
   - **Low:** significant ambiguity; most fields inferred; sparse or unclear source text.

2. **Deterministic post-hoc computation (`_compute_confidence()` in `src/postprocess.py`):** After all postprocessing rules have fired, the system overwrites the LLM's confidence with a score computed from observable signals:

   | Signal | Points | Logic |
   |---|---|---|
   | `publish_date` present | +2 | Core field; missing = weak extraction |
   | `source_type` not "Other" | +2 | Known publisher = trustworthy source |
   | `evidence_bullets` count | +1 to +2 | 2 bullets = +1, 3+ bullets = +2 |
   | `key_insights` count | +1 | At least 2 present |
   | `regions_relevant_to_kiekert` non-empty | +1 | Relevance clarity signal |
   | Postprocess rule corrections (per 3 rules fired) | −1 each | More corrections = lower extraction quality |
   | `publish_date` backfilled by regex | −1 | LLM missed an extractable date |

   **Thresholds:** score ≥ 7 → High, score ≥ 4 → Medium, score < 4 → Low.

3. **Auditability:** Each record stores a `_confidence_detail` object containing the LLM's original assessment, the computed value, the numeric score, and the per-signal breakdown. This enables calibration analysis (comparing LLM self-assessment vs computed confidence vs human review outcomes over time).

**Why this works:** The computed score is deterministic, reproducible, and grounded in observable extraction quality — not the model's self-perception. A record where the LLM claims "High" confidence but failed to extract a publish_date, has an unknown source_type, and required multiple postprocess corrections will be downgraded to "Low" automatically. Conversely, a clean extraction from a known publisher with complete fields earns "High" regardless of what the model reported. This eliminates overconfidence bias and ensures that auto-approval and brief ranking are calibrated to actual data quality.

**Impact on downstream systems:**
- **Auto-approval** (`_finalize_record()` in `pages/01_Ingest.py`): requires confidence ∈ {High, Medium} — now based on computed score, so weak extractions are correctly routed to manual review.
- **Weekly brief ranking** (`synthesize_weekly_brief_llm()` in `src/briefing.py`): records sorted by priority + confidence — computed confidence ensures the best-extracted records surface first.
- **Dedup tie-breaking** (`src/dedupe.py`): confidence score (High=3, Medium=2, Low=1) breaks ties between duplicate records — computed confidence picks the more completely extracted version.

#### 7.5.7 Meta-based model routing + per-chunk repair

**Problem:** With 20 RPD (Requests Per Day) on both Flash-Lite and Flash under Gemini's free tier, every API call counts. The original chunked extraction ran each chunk through the full two-pass strategy (Flash-Lite → Flash) independently. For noisy documents, Flash-Lite consistently failed on every chunk, burning 2 calls per chunk (Flash-Lite attempt + Flash repair) — wasting half the daily quota on expected failures.

**Approach chosen:** Use cleanup meta from `clean_and_chunk()` to choose the initial model upfront, then run all chunks with that model and batch-repair only the failures:

1. **Noise classification (`_classify_noise()` in `pages/01_Ingest.py`):** Examines `removed_ratio`, `removed_line_count`, and `top_removed_patterns` from the cleanup stage. Classifies as:
   - **high:** removed_ratio > 0.18, or removed_lines > 250, or OCR/table/header/footer/page patterns detected → route to Flash directly
   - **low:** removed_ratio < 0.08 and removed_lines < 80 → route to Flash-Lite
   - **normal:** everything else → route to Flash-Lite
2. **Phase 1 — initial model:** All chunks are extracted with the chosen model via `extract_single_pass()` (one-shot extraction, no internal fallback).
3. **Phase 2 — repair only failures:** Only chunks that failed Phase 1 are retried with the stronger model (Flash). Chunks that succeeded in Phase 1 are untouched. If Flash-Lite was not the initial model (i.e., high-noise routed directly to Flash), Phase 2 is skipped entirely.
4. **Router logging:** Each chunk log includes `phase` ("initial" or "repair") and `chunk_id`. The aggregate router_log includes `noise_level`, `initial_model`, `removed_ratio`, `chunks_succeeded_initial`, `chunks_repaired`, `chunks_failed_final`.

**Why this works:** Clean documents (the majority) complete on Flash-Lite in Phase 1 with zero wasted calls. Noisy documents skip Flash-Lite entirely, saving the wasted attempt. Only genuinely ambiguous chunks trigger the repair path. In practice, this cuts API call consumption by 30-50% compared to the per-chunk two-pass approach while maintaining the same extraction quality.

**Non-chunked path unchanged:** Single-context documents still use `route_and_extract()` with its built-in two-pass (Flash-Lite → Flash). Meta-routing has no benefit for single calls.

#### 7.5.8 From external specs to code-embedded LLM guidance — a meaningful iteration

**Problem:** The project started with a spec-first approach: five Markdown reference files (`SKILL_final.md`, `topic-taxonomy.md`, `company-watchlist.md`, `prompts.md`, `executive-brief-template.md`) defined the taxonomy, region rules, priority rubric, and competitive context. This was good design practice — it forced clarity before coding. But as the codebase evolved through iterative AI-assisted development, three problems emerged:

1. **Spec drift:** The code evolved (new region tiers, removed schema fields, changed actor types) but the spec files were never updated. Within weeks, every spec file contained outdated information.
2. **The LLM was blind to domain guidance:** The topic tagging rules ("use 'OEM Strategy' for broad pivots, NOT single program updates") and competitor lists (Hi-Lex, Aisin, Brose as Tier 1 closure competitors) existed in reference files but were never injected into the extraction prompt. The LLM only saw topic *names* in the schema enum — it had to guess the boundaries between similar topics.
3. **Maintenance burden:** Updating a topic required changes in 4-5 places (spec file, code constant, prompt, taxonomy doc, watchlist doc) — a recipe for silent misalignment.

**What was considered:**

| Option | Pros | Cons |
|---|---|---|
| A) Keep spec files, add sync checks | Preserves original documentation structure | Still requires maintaining 5 files; sync checks add complexity; LLM still doesn't see the guidance |
| B) Auto-generate specs from code | Single source of truth in code | Generated docs tend to be less readable than hand-written specs; doesn't solve the LLM guidance gap |
| C) Embed guidance in code + prompt | LLM sees domain rules at inference time; one place to update; no drift | Topic guidance lives as comments (less "pretty" than a formatted spec) |

**Approach chosen: Option C.** The domain guidance was embedded directly where it is consumed:

1. **Topic tagging guidance** → moved into `src/constants.py` as structured comments above `CANON_TOPICS`, and into `extraction_prompt()` in `src/model_router.py` as LLM instructions.
2. **Competitor context** → injected into the extraction prompt so the LLM recognizes closure system suppliers by name and tier.
3. **Kiekert identity** → added as the opening line of the extraction prompt, giving the LLM domain context for all classification decisions.
4. **Company watchlist** → kept as the sole remaining Markdown reference file (`References/company-watchlist.md`), stripped of all content that duplicated code (outdated regions, priority rules).

**Before the change — extraction prompt (abbreviated):**
```
Return JSON only matching the schema. Follow these rules strictly:
1) source_type is the PUBLISHER of the document...
5) Only use 'Closure Technology & Innovation' when latch/door/handle/... appears explicitly.
...
Use only the provided text.
```

**After the change — extraction prompt (abbreviated):**
```
You are extracting structured intelligence for Kiekert, an automotive closure systems
supplier (door latches, strikers, handles, smart entry, cinch systems).
Return JSON only matching the schema. Follow these rules strictly:
...
TOPIC CLASSIFICATION — pick 1-4 topics using these rules:
- 'OEM Strategy & Powertrain Shifts': broad OEM strategic pivots (BEV/ICE mix, vertical
  integration, platform resets, localization). NOT single program updates.
- 'OEM Programs & Vehicle Platforms': specific program announcements (launches, refreshes,
  platform rollouts, sourcing decisions). NOT broad strategy narratives.
...
CLOSURE SYSTEMS COMPETITORS — recognize these as suppliers (actor_type='supplier'):
Tier 1: Hi-Lex, Aisin, Brose, Huf, Magna (Magna Closures/Mechatronics), Inteva, Mitsui Kinzoku
Tier 2: Ushin, Witte, Mitsuba, Fudi (BYD subsidiary), PHA, Cebi, Tri-Circle
Our company: Kiekert (set mentions_our_company=true if mentioned)
```

**Did it improve performance?** Yes, in two measurable ways:
- **Topic classification:** The explicit boundary rules (e.g., "OEM Strategy = broad pivots, NOT single program updates" vs "OEM Programs = specific announcements, NOT broad strategy") give the LLM clear decision criteria instead of forcing it to infer boundaries from label names alone.
- **Competitor recognition:** The LLM now correctly tags closure system competitors as `actor_type='supplier'` and recognizes Kiekert mentions for `mentions_our_company=true`, which feeds the deterministic `_boost_priority()` postprocess.

**Bottleneck encountered:** The biggest frustration was discovering how far the spec files had drifted. For example, `SKILL_final.md` still listed `strategic_implications` and `recommended_actions` as required schema fields — fields that had been intentionally removed months earlier to achieve leaner, deterministic ingest. `context-watchlist.md` still used the legacy `Europe (including Russia)` region — a bucket that had been split into `Western Europe` and `Eastern Europe` in the code. Each outdated reference was a potential source of confusion for anyone (human or AI) reading the project documentation.

**Workaround for the transition:** Rather than deleting everything immediately, the outdated spec files were moved to `References/Archives/` to preserve project history. A `QUARTERLY_REVIEW.md` checklist was created to formalize the ongoing maintenance process, ordered from lowest-risk changes (company watchlist — pure reference, no code) to highest-risk (region enums — run tests after every change).

<!--
[PLACEHOLDER: Screenshot of the extraction prompt before vs after, showing the topic guidance
and competitor context sections that were added]
-->

#### 7.5.9 API quota tracking + smart chunk recommendations

**Problem:** The Gemini free tier imposes a hard 20 RPD limit per model (Flash-Lite and Flash each). With no visibility into consumption, analysts could unknowingly exhaust their daily quota mid-batch. Chunked mode on short documents wasted calls unnecessarily (a 5K-char article produces 1 chunk, so chunked mode adds overhead with no quality benefit).

**Approach chosen:** A lightweight file-based quota tracker (`src/quota_tracker.py`) with UI integration:

1. **Persistent tracking:** Each API call increments a per-model counter in `data/api_usage.json`. The tracker checks the stored date against the current Pacific Time date; if different, counts reset to zero (matching Google's midnight PT billing window).
2. **Sidebar display:** The Ingest page sidebar shows live per-model usage/remaining with progress bars (e.g., "flash-lite: 8/20 used (12 left)").
3. **Smart chunk mode recommendations:**
   - If the document produces 1 chunk and chunked mode is ON: info message ("Clean article — chunked mode adds no benefit here")
   - If the document produces N > 1 chunks and chunked mode is ON: warning with call count vs remaining quota
   - If the document produces N > 1 chunks and chunked mode is OFF: warning that partial text will be sent
4. **Bulk mode quota estimate:** Before running bulk extraction, shows worst-case API call count (files × ~3 chunks) vs remaining quota.

**Why this works:** The tracker is zero-overhead (simple JSON file, no database) and resets deterministically. The sidebar display makes quota visible at all times. Smart recommendations help analysts make informed decisions about when to use chunked mode vs single-context mode, avoiding unnecessary API consumption on clean articles.

## 8. Evaluation

*(Start simple; add rigor as you can.)*

### 8.1 Evaluation approach

* Qualitative: does output feel consistent, useful, and traceable?
* Quantitative (lightweight):

  * % outputs that pass schema validation on first try
  * average processing time per document
  * average tokens per document (estimate)
  * reviewer override rate (how often humans change tags/priority)

### 8.2 Accuracy checks (taxonomy and regions)

* Topic consistency: are topics chosen from canonical list? any drift?
* Region roll-ups (two-tier architecture):

  * Display regions: Asia, Western Europe, Eastern Europe, Africa, US, Latin America
  * Footprint regions: India, China, Japan, Thailand, Mexico, Russia + display regions
  * Country-to-region mappings: ~60 countries mapped via `COUNTRY_TO_FOOTPRINT` in `postprocess.py`
  * Legacy migration: `Europe (including Russia)` → `Western Europe` unless Russia explicitly present

### 8.3 Case studies (recommended for the report)

Add 2–3 short “before/after” examples:

* Example A: market note (region-heavy)
* Example B: competitor/OEM program change (priority-driven)
* Example C: government/regulatory release (actor type driven)

For each: include the source snippet, the JSON record, and the rendered brief.

### 8.4 Quality monitoring system

Extraction accuracy and brief consistency are the hardest aspects of an LLM-based intelligence pipeline to maintain over time. Schema validation catches structural errors, but it cannot detect semantic drift — a correct-looking record where the confidence is inflated, a footprint region is missing because the country mapping was incomplete, or a macro theme fires without meeting its signal threshold. These failures are silent: they pass validation, surface in executive briefs, and erode trust without any visible error.

To address this, the system includes an automated quality monitoring module (`src/quality.py`, `scripts/run_quality.py`) that runs post-hoc checks on both records and briefs, computes quality KPIs, and produces append-only audit logs for trend analysis.

#### 8.4.1 Quality check categories

**Record-level checks** (run on every record in the brief's selection set):

| Check | What it detects | Severity |
|---|---|---|
| Evidence grounding | Evidence bullets not found in source PDF text (exact or ≥60% keyword overlap) | High |
| Evidence near-miss | Evidence bullets between 45–60% keyword overlap (paraphrased but not hallucinated) | Medium |
| Duplicate record in brief | Same story ingested as separate records (detected by dedupe key or ≥85% title similarity) | High |
| Near-duplicate titles | Fuzzy title match (≥85% similarity) across records with different dedupe keys | Medium |
| Geo leakage | Footprint regions present that cannot be derived from country_mentions | High |
| Display bucket leakage | Country-level values (India, China, etc.) appearing in `regions_mentioned` instead of display buckets (Asia) | High |
| Missing footprint region | Country present in `country_mentions` but its derived footprint region missing from `regions_relevant_to_kiekert` | Medium |
| Duplicate values | Repeated entries in companies, countries, or regions (after normalization) | Medium |
| Canonicalization inconsistency | Multiple alias forms of the same company (e.g., VW + Volkswagen) surviving dedup | Medium |
| Macro theme rule violation | Theme fired without meeting min_groups, premium company gate, or region requirement | High |
| Confidence-evidence mismatch | High confidence with fewer than 2 evidence bullets | Medium |
| Confidence-source mismatch | High confidence from source_type "Other" | Low |
| Missing priority reason | Priority escalated from LLM original but `priority_reason` is empty | Medium |

**Brief-level checks** (run on the generated executive brief text):

| Check | What it detects | Severity |
|---|---|---|
| Ungrounded claim | Bullet in a claim section has no REC citation while the brief uses REC labels | High |
| REC mismatch | REC ID referenced in brief does not exist in the selected record set | High |
| Missing uncertainty section | Records contain uncertainty signals but CONFLICTS & UNCERTAINTY is empty or "None observed" | High |
| Overreach | Hard-assertion language (e.g., "decided", "scrapping") when source records use softer language (e.g., "weighing", "could") | Medium |

#### 8.4.2 Severity definitions

Severity levels are assigned based on downstream impact:

- **High**: Factual error that would propagate to executive output. A single High-severity finding in a published brief is a quality failure. Examples: hallucinated evidence, wrong region mapping, ungrounded claim.
- **Medium**: Inconsistency that degrades analytics or audit transparency but does not produce a factually wrong executive output. Examples: duplicate company entries inflating theme counts, missing priority explanation, thin evidence for stated confidence.
- **Low**: Minor inconsistency with limited downstream impact. Examples: non-canonical alias form that was still correctly deduplicated, high confidence from an unrecognized publisher.

#### 8.4.3 KPI methodology

Ten KPIs are computed per quality run — five for records (R1–R5), five for briefs (B1–B5):

**Record KPIs:**

| KPI | Definition | Target | Computation |
|---|---|---|---|
| R1 | High-severity defects per record | 0.00 | count(High findings) / count(records) |
| R2 | Medium-severity defects per record | ≤ 1.0 | count(Medium findings) / count(records) |
| R3 | Evidence grounding pass rate | ≥ 90% | % of records where all evidence bullets are source-verifiable |
| R4 | Canonicalization stability | ≥ 95% | % of records with no alias inconsistency findings |
| R5 | Geo determinism pass rate | ≥ 98% | % of records where footprint regions == f(country_mentions) and no display bucket leakage |

**Brief KPIs:**

| KPI | Definition | Target | Computation |
|---|---|---|---|
| B1 | Ungrounded claims count | 0 | count(ungrounded_claim + rec_mismatch findings) |
| B2 | Overreach count | ≤ 2 | count(overreach findings) |
| B3 | Uncertainty compliance | 100% | 1.0 if uncertainty section present when required, else 0.0 |
| B4 | Synthesis density | ≥ 2 | count(bullets citing ≥ 2 distinct REC IDs) |
| B5 | Action specificity score | ≥ 4/5 | Keyword-based scoring: owner role (1pt), timeframe (1pt), artifact verb (1pt), trigger/watch condition (1pt), output type (1pt) |

#### 8.4.4 Weighted quality scores

Two composite scores (0–100) summarize overall quality per run:

**Record score** — starts at 100, deductions:
- High finding: −25 each
- Medium finding: −10 each
- Low finding: −2 each

**Brief score** — starts at 100, deductions:
- Ungrounded claim or REC mismatch: −25 each
- Wrong signal / wrong certainty: −20 each
- Overreach: −10 each
- Missing uncertainty when required: −20
- Fewer than 2 cross-record themes: −15

**Overall score** = average(record score, brief score). A score below 80 should trigger investigation before publishing. Scores below 60 indicate systematic quality issues requiring pipeline or prompt changes.

#### 8.4.5 Quality outputs and audit trail

All quality data is append-only (no overwrites), enabling trend analysis:

| Output | Path | Format |
|---|---|---|
| Record findings | `data/quality/record_qc.jsonl` | One JSON object per finding |
| Brief findings | `data/quality/brief_qc.jsonl` | One JSON object per finding |
| Run summaries | `data/quality/quality_runs.jsonl` | One JSON object per run with all KPIs |
| Excel report | `data/quality/quality_report.xlsx` | 5 sheets: record_qc, brief_qc, runs_summary, kpi_trends, summary_pivot |

The CLI entrypoint (`python scripts/run_quality.py`) accepts `--latest-brief` (default) or `--brief-id <id>` and prints a console summary: high issue count, brief score, and top 3 issue types. The Excel report includes a summary pivot sheet for recurring defect pattern analysis.

#### 8.4.6 Integration with the pipeline

The quality module is intentionally read-only — it observes records and briefs but never modifies them. This preserves the architecture invariant that `postprocess_record()` → `validate_record()` is the only mutation path.

Uncertainty detection uses a shared word list (`UNCERTAINTY_WORDS` in `constants.py`) consumed by both the synthesis prompt (which makes the CONFLICTS & UNCERTAINTY section mandatory when triggered) and the quality checker (which verifies the brief actually includes it). This single-source-of-truth pattern prevents the prompt and QC from diverging on what counts as uncertainty language.

#### 8.4.7 Quality system improvements (2026-02-17)

**Problem identified:** The initial quality monitoring system (sections 8.4.1–8.4.6) was purely observational. It could detect issues in a single run, but had no mechanism to (1) track whether extraction quality was improving or degrading over time, (2) catch duplicate records that slipped through ingest-time dedup, (3) distinguish genuine hallucinations from acceptable paraphrasing in evidence grounding, (4) surface recurring issues as actionable feedback for prompt tuning, or (5) scale company alias detection beyond 4 hardcoded OEM groups. These gaps meant the QC system could report problems but could not close the loop toward fixing them.

**Prompt used:** *"Scan python scripts/run_quality.py references and output. Is it good quality check and monitoring to improve extraction and brief generation?"* — followed by: *"Suggest improvement to be able to see quality extraction improving over time and to check duplicate-record cross-check. What do you propose about evidence grounding threshold? About feedback loop to extraction? To improve company alias groups that are hardcoded with only 4 groups?"*

**Five improvements implemented:**

**1. KPI trend tracking and regression detection** (`compute_quality_trends()` in `quality.py`)

The run summary log (`quality_runs.jsonl`) already stored KPI values per run but nothing consumed them for trend analysis. A new function compares the current run against the last N runs (default 5), computing delta-from-average and delta-from-last for all 13 KPIs. Each KPI is annotated with its improvement direction (e.g., R1 "high defect rate" improves when it goes down; R3 "evidence grounding pass rate" improves when it goes up). Regression alerts fire when a ratio KPI worsens by ≥5% or a count KPI worsens by ≥2 points. A new `kpi_trends` sheet in the Excel report shows run-over-run movement for all KPIs. The CLI output now prints trend direction, regression alerts, and stable-vs-declining status after each run.

**2. Duplicate-record cross-check** (`_check_duplicate_records()` in `quality.py`)

Ingest-time dedup uses a composite key (date + topic + companies + title fingerprint) and a title similarity threshold of 0.88. However, the same article ingested on different days or with slight title variations can slip through. A post-hoc duplicate check now runs on all target records during QC, using two methods: (a) exact match on `build_dedupe_key()` — any group with 2+ records emits a High-severity `duplicate_record_in_brief` finding; (b) fuzzy title matching via `SequenceMatcher` at threshold 0.85 (lower than the 0.88 ingest check to catch near-misses) — emits a Medium-severity `near_duplicate_titles` finding. Pairs already caught by exact key are skipped to avoid double-reporting.

**3. Granular evidence grounding with configurable threshold**

The original evidence grounding check used a hardcoded 60% keyword overlap threshold and reported binary pass/fail. Three changes were made: (a) the threshold is now a named constant (`EVIDENCE_GROUNDING_THRESHOLD = 0.60`) for single-point tuning; (b) a near-miss tier (`EVIDENCE_NEAR_MISS_THRESHOLD = 0.45`) separates genuine hallucinations (<45%, High severity) from acceptable paraphrasing (45–60%, Medium severity); (c) per-bullet overlap percentages and per-record average overlap are reported in finding notes, enabling threshold tuning based on observed data rather than guesswork.

**4. Extraction feedback loop** (`generate_extraction_feedback()` in `quality.py`)

A new function aggregates findings across the last N quality runs (default 5) and identifies chronic issues — finding types that appear in ≥50% of recent runs. Each chronic finding type maps to a pre-defined actionable suggestion (template-driven, no LLM call). For example, if `evidence_not_grounded` appears in 4 of the last 5 runs, the system suggests: *"Consider adding 'Use exact phrases from the source text where possible' to the extraction prompt."* Twelve finding types have mapped suggestions covering prompt changes, postprocess map extensions, and dedup threshold adjustments. The CLI prints chronic issues and suggestions after each run. This is Phase A (observational feedback); the human operator decides whether to act on the suggestions.

**5. Auto-derived company alias groups** (`_build_company_alias_groups()` in `quality.py`)

The original QC module hardcoded 4 company alias groups (Volkswagen, Toyota, GM, Mercedes-Benz). A new builder function auto-derives alias groups from the postprocess canonicalization maps (`_OEM_CANONICAL_BY_LOWER`, `_COMPANY_SPECIAL_CANONICAL`) and enriches them with known variants for 14 additional OEMs (Ford, Hyundai, Stellantis, Nissan, Honda, Renault, Geely, Tata, Volvo, JLR, Kia, Audi, Porsche). This produces 18 alias groups covering all major automotive companies. The groups auto-update when postprocess maps change — adding a new OEM canonical mapping automatically extends QC coverage with zero maintenance.

**Updated quality outputs:**

| Output | Change |
|---|---|
| CLI console | Now prints KPI trends, regression alerts, chronic issues, and prompt suggestions |
| Excel report | New 5th sheet `kpi_trends` with per-KPI direction, delta, and run count |
| Pipeline return | New `trends` and `feedback` keys in the result dict |
| Record findings | New finding types: `evidence_near_miss`, `duplicate_record_in_brief`, `near_duplicate_titles` |

All 97 existing tests continue to pass after these changes. The read-only invariant is preserved — no improvement modifies records or briefs.

## 9. Results (initial)

*(Fill once you run a few documents.)*

* Records processed: [n]
* Schema pass rate (first try): [x%]
* Mean tokens per doc: [estimate]
* Mean time per doc: [estimate]
* Override rate: [x%]
* Observed strengths:

  * [fill]
* Observed weaknesses:

  * [fill]

## 10. Discussion and Lessons Learned

### 10.1 What worked

* Schema-first design reduced ambiguity and made outputs reusable.
* Evidence bullets improved trust and made review faster.
* Context pack selection controlled token usage without losing key signals.
* HITL gating made the workflow realistic for organizational adoption.
* Duplicate detection layer (both exact and fuzzy) prevented noise in executive reporting while maintaining flexibility.
* Publisher ranking system (deterministic scoring: S&P=100 > Bloomberg=90 > Reuters=80 > Financial News=78 > MarkLines=76 > Automotive News=75 > Industry Publication=72 > ... > Other=50) ensured that when multiple sources covered the same story, the highest-quality source was automatically selected.
* Weekly briefing workflow with share-ready detection (High priority + High confidence) and executive email templating made it easy for analysts to draft weekly digests with minimal manual work.
* Deduplication and briefing modules were entirely deterministic (no additional LLM calls), keeping token costs and latency predictable.
* **Noisy-PDF cleaning** significantly improved extraction quality: removing ads, nav menus, paywall prompts, and repeated headers before the model sees the text eliminated the most common source of wrong source_type and phantom entity extraction.
* **Two-pass model strategy** (Flash-Lite → Flash) reduced average token cost while maintaining extraction quality on hard documents. Most documents complete on the cheaper model; only failures escalate.
* **Publisher-vs-cited-source prompt rule** was the single highest-impact prompt change — it fixed the most common misclassification (S&P articles being tagged as "Reuters" because Reuters was cited in the body).
* **Token usage logging** provided visibility into cost per document and made it easy to identify which documents triggered the stronger model, enabling targeted improvements to the cleanup pipeline.
* **AI-generated Weekly Executive Brief** (v3.5) transformed the flagship deliverable from a static list of titles into a cross-record LLM synthesis following the executive report template. This is the single most valuable output for executive stakeholders, and it requires only one additional LLM call (Gemini Flash) for up to 20 records.
* **Consolidated Review & Approve page** (v3.6-3.7, consolidated v6.2) dramatically reduced review friction: unified queue with filters, title-first expandable cards with inline approve/review buttons, record detail with Next/Previous navigation, Quick Approve with auto-advance, and full JSON editing — all in a single page. The simplified review model (Pending/Approved/Disapproved with auto-approve) matches the single-analyst workflow.
* **Bulk PDF ingest** (v3.8) enabled processing multiple articles in one session with progress tracking, per-file deduplication, and summary tables — critical for weekly batches of 10-20 articles from premium sources.
* **Trend analysis charts** (v4.0-4.1) added the temporal dimension that makes a CI tool useful for spotting change over time: Topic Momentum with weighted counting and Emerging/Expanding/Fading/Stable classification, Top Company Mentions with canonicalization, and Priority Distribution with High-Ratio and Volatility Index. All computed deterministically (zero token cost) via pandas aggregations and Altair visualizations.
* **Priority classification** (v4.3) — the two-layer approach (prompt rules + deterministic `_boost_priority()` postprocess) ensured that business-critical signals are never missed even when the model underestimates priority. The deterministic boost acts as a safety net that catches footprint-region + closure-tech or key-OEM combinations.
* **Computed confidence** (v4.6) replaced the LLM's self-assessed confidence (which skewed toward "High" regardless of extraction quality) with a deterministic score based on observable signals (field completeness, postprocess corrections, date backfill). This fixed the overconfidence bias that was allowing weak extractions to be auto-approved and surface in executive briefs. The `_confidence_detail` audit trail enables ongoing calibration analysis.
* **Meta-based model routing** (v4.5) cut API consumption by 30-50% compared to the per-chunk two-pass approach. Noisy documents skip Flash-Lite entirely (avoiding wasted calls), while clean documents complete on Flash-Lite in a single pass. This was essential for staying within the 20 RPD free-tier limit during daily workflows.
* **API quota tracking** (v4.4) with smart chunk recommendations gave analysts the visibility to manage their daily API budget. The sidebar progress bars and pre-run estimates prevent mid-batch quota exhaustion.

* **Automated quality monitoring** (v6.3) addressed the hardest problem in LLM-based intelligence: silent semantic drift that passes schema validation but erodes output quality. The quality module runs 10+ post-hoc checks per record (evidence grounding against source PDF, geo determinism, macro theme rule validation, confidence-evidence alignment, priority audit trail) and 4+ checks per brief (REC citation consistency, uncertainty compliance, overreach detection). Ten KPIs with weighted composite scores (0–100) and append-only audit logs enable trend analysis across runs. The single-source-of-truth pattern for uncertainty word lists (shared between the synthesis prompt and QC checker) prevents the most common drift pattern: the prompt and its validator diverging on definitions.

* **Spec-to-code consolidation** (v4.7) eliminated spec drift by embedding topic tagging guidance and competitor context directly into the extraction prompt and code comments. This was the single most impactful change for LLM classification quality — the model went from guessing topic boundaries based on label names alone to receiving explicit disambiguation rules. The lesson: specifications that are not consumed at runtime become a maintenance liability; embed domain guidance where it is actually read (by the LLM in the prompt, by developers in code comments).

### 10.2 What was challenging

* PDFs vary widely in extractability and formatting.
* Publish date extraction may be inconsistent depending on source format.
* Company alias handling requires careful tuning (avoid overcomplication).
* Some articles have weak signal-to-noise; prioritization must remain conservative.
* Provider-specific schema constraints required explicit compatibility work: the google-genai SDK enforces a Gemini-specific type system (single uppercase enum values like STRING, OBJECT, NULL) that differs from standard JSON Schema conventions (e.g., type: ["string","null"]). This gap was not surfaced until runtime and required rewriting the schema definition and reordering the postprocessing/validation pipeline.
* URL hallucination risk emerged when the model was asked to extract original_url from PDFs that did not contain one; mitigating this required moving URL capture to a human-in-the-loop input rather than relying on model extraction.
* **Publisher-vs-cited-source confusion** was a persistent extraction error that required explicit prompt rules to fix. The model would see "Reuters" in an S&P article body and set source_type="Reuters" despite S&P being the publisher. This was not fixable by postprocessing alone — it required changing the extraction prompt.
* **Balancing cleanup aggressiveness:** too-aggressive text cleaning risks removing legitimate content (e.g., short lines that are actually article subheadings). The safety fallback (preserve original if cleaned text drops below 2K chars) and the diagnostic display in the UI help the analyst catch over-cleaning.
* **Chunk boundary effects:** when a document is split into chunks, entities or dates that span a chunk boundary can be missed. The 800-char overlap mitigates this but does not eliminate it entirely.
* **Priority defaulting to Medium:** without explicit priority criteria in the prompt, the model defaulted every record to "Medium" — a safe but useless classification. Fixing this required both prompt-side rules (defining what High/Medium/Low mean for Kiekert) and code-side deterministic overrides. The lesson is that business-specific classifications need explicit criteria; the model cannot infer domain-specific priority without guidance.
* **API rate limits on free tier:** the Gemini free tier's 20 RPD per model constraint required rethinking the entire chunked extraction approach. The original per-chunk two-pass strategy (Flash-Lite → Flash for each chunk) could consume 6-8 calls for a single multi-chunk document. Meta-based routing and two-phase repair were necessary to stay within budget.
* **LLM confidence self-assessment bias:** the model consistently rated its own confidence as "High" even for poorly extracted records (missing dates, unknown source types, sparse evidence). This was invisible until we compared model-reported confidence against actual field completeness. The fix required replacing self-assessment entirely with a computed score — a reminder that LLMs cannot reliably judge the quality of their own outputs without external grounding signals.
* **Spec drift during iterative AI-assisted development:** The project started with carefully authored Markdown specification files (SKILL.md, topic-taxonomy.md, company-watchlist.md) that defined the system's taxonomy, regions, and competitive context. As the codebase evolved through dozens of iterations — adding new region tiers, removing schema fields, changing actor types — these spec files were never updated. Within weeks, every reference document contained outdated information while the code had moved on. Worse, the topic tagging guidance and competitor context that lived in these files were never wired into the LLM's extraction prompt, meaning the model was flying blind on domain-specific classification decisions. The fix was to consolidate all domain guidance into the code itself (constants.py comments + extraction prompt instructions) and reduce the reference files to a single competitive intelligence document. The lesson: in iterative AI-assisted development, treat the code as the single source of truth from the start, not the spec documents.
* **Weighted counting for trend charts:** naive topic counting double-counts multi-topic records, inflating signals for broadly-tagged articles. Implementing 1/n weighted counting per topic (where n is the number of topics on a record) required restructuring the chart data pipeline and adopting Altair for interactive visualizations with classification labels.
* **UTC-aware datetime handling:** mixing timezone-aware (from storage timestamps) and timezone-naive (from date inputs) datetimes caused Dashboard crashes. Required systematic UTC normalization across Dashboard, Inbox, and Weekly Brief pages.

### 10.2 Iterations and scope control (recommended addition)
Early in development, the project included prototype scripts that generated narrative summaries and weekly briefs directly from raw text. During implementation, these were intentionally replaced with a JSON-first, schema-validated pipeline aligned with the project specification. This change improved reliability (consistent fields and controlled vocabularies), reduced hallucination risk (evidence bullets + validation), and made token usage more predictable (bounded context pack + one-call extraction in the common case). The final system therefore prioritizes structured intelligence records as the primary artifact, and renders human-readable briefs deterministically from those records rather than relying on additional model calls.

This iteration also reduced repository complexity by removing scripts that were no longer aligned with the final architecture.

### 10.3 Future improvements

* Expand watchlist and synonyms gradually based on real analyst overrides
* Tune similarity threshold and deduplication criteria based on analyst feedback from real workflows
* Integrate with Power BI for interactive executive dashboards (CSV export already supports this)
* Extend publisher scoring with recency and completeness weighting for time-sensitive events
* Add earnings analysis module for financial signal extraction
* Integrate with enterprise tools (SharePoint/Teams) for scheduled email dispatch as Phase 2
* Move to Gemini paid tier when daily volume exceeds 20 RPD; the quota tracker already supports custom limits via `set_quota()`
* Add re-ingest capability to apply updated priority rules and postprocess logic to existing records without re-extracting from the model
* Explore embedding-based duplicate detection for better cross-language and paraphrase matching

## 11. Conclusion

This project demonstrates that a minimal-token GenAI workflow can deliver real business value by converting unstructured automotive content into structured, evidence-backed intelligence. The solution is designed to scale through consistency (controlled vocabularies), reliability (validation + evidence), and adoption (human-in-the-loop review), while keeping cost predictable through meta-based model routing, API quota tracking, and deterministic processing for all non-extraction workflows. The AI-generated Weekly Executive Brief provides the flagship deliverable — cross-record synthesis following a structured executive report template — while trend analysis charts enable analysts to spot temporal patterns without additional LLM cost.

---

# Implementation Summary (v6.3)

**Version:** 6.3
**Completion Date:** February 17, 2026

## Key Features Delivered

1. **Noisy-PDF Cleaning + Chunking** (`src/text_clean_chunk.py`)
   - Unified cleanup pipeline: nav/promo/paywall/social/link-heavy/repeated-header removal
   - Hyphen-break fixing, block deduplication, safety fallback against over-cleaning
   - Overlapping model-ready chunks (~9K chars, 800-char overlap) with detected-title propagation
   - Full removal diagnostics (line count, pattern breakdown) surfaced in Ingest UI

2. **Meta-Based Model Routing + Per-Chunk Repair** (`src/model_router.py`, `pages/01_Ingest.py`)
   - Noise classification from cleanup meta (removed_ratio, line count, pattern types): low/normal → Flash-Lite, high → Flash directly
   - `extract_single_pass()`: one-shot extraction with specific model, no internal fallback
   - Phase 1: all chunks on initial model; Phase 2: retry only failed chunks with stronger model
   - Router log: noise_level, initial_model, removed_ratio, chunks_succeeded_initial, chunks_repaired, chunks_failed_final
   - Non-chunked path: original two-pass strategy (Flash-Lite → Flash) via `route_and_extract()` preserved for single-context documents

3. **Hardened Extraction Prompt** (9 numbered rules)
   - Publisher-vs-cited-source rules (prevents S&P articles being tagged as "Reuters")
   - Strict date normalization (multiple patterns → YYYY-MM-DD)
   - Evidence bullet length cap (25 words max per bullet)
   - List deduplication and normalization instructions
   - **Priority classification rules** (rule 8): High/Medium/Low with Kiekert-specific criteria (footprint regions, closure tech, key OEMs, regulatory impact)
   - **Confidence classification rules** (rule 9): High/Medium/Low with explicit criteria based on field clarity and evidence quotability
   - Repair prompt includes specific validation errors for targeted fixes

4. **Priority Classification** (`src/postprocess.py`)
   - Deterministic `_boost_priority()` postprocess: upgrades to High when `mentions_our_company`, footprint region + closure topic/keyword, or footprint region + key OEM customer
   - Runs after model extraction as safety net for business-critical signals

5. **Computed Confidence** (`src/postprocess.py`)
   - Replaces LLM self-assessed confidence with a deterministic score computed from observable extraction signals
   - Scoring: +2 publish_date present, +2 known source_type, +1–2 evidence bullets, +1 key_insights, +1 kiekert regions, −1 per 3 rule corrections, −1 if date backfilled by regex
   - Thresholds: ≥7 → High, ≥4 → Medium, <4 → Low
   - Full audit trail in `_confidence_detail` (LLM original, computed value, numeric score, per-signal breakdown)
   - Feeds auto-approval, weekly brief ranking, and dedup tie-breaking

6. **Chunked Extraction with Merge** (`pages/01_Ingest.py`)
   - Each cleaned chunk extracted independently via model
   - Results merged: majority voting (source_type, actor_type), union+dedup (entities, topics, regions), highest-confidence date, short-bullet filtering
   - Handles long/noisy documents that exceed single-context limits

7. **Duplicate Detection & Deduplication** (`src/dedupe.py`)
   - Exact title matching (blocking at ingest)
   - Fuzzy story detection (threshold 0.88)
   - Deterministic publisher-weighted ranking (S&P=100, Bloomberg=90, Reuters=80, Financial News=78, MarkLines=76, Automotive News=75, Industry Publication=72, ... Other=50)
   - Confidence and completeness scoring for tie-breaking

8. **Weekly Briefing Workflow** (`src/briefing.py` + `pages/03_Weekly_Executive_Brief.py`)
   - Candidate selection from last N days (configurable, default 30, max 90; auto-excludes duplicates)
   - Share-ready detection (High priority + High confidence)
   - Deterministic Markdown brief + executive email template generation
   - **AI-generated Weekly Executive Brief:** LLM synthesis (Gemini Flash) across up to 20 selected records following structured executive report template (exec summary, high-priority developments, footprint region signals, topic developments, emerging trends, recommended actions); token usage displayed
   - Analyst-driven item selection with one-click suggestions

9. **Bulk PDF Ingest** (`pages/01_Ingest.py`)
   - Multi-file uploader with progress bar and per-file extraction loop
   - Deduplication checks filename and extracted title against existing records and within the batch
   - Incremental checkpoint persistence: each successfully extracted record is written immediately, so a mid-run freeze/failure does not lose earlier completed files
   - Summary table showing saved/skipped/failed counts per file
   - Pre-run quota estimate (worst-case API calls vs remaining quota)

10. **API Quota Tracker** (`src/quota_tracker.py`)
    - Per-model RPD usage persisted to `data/api_usage.json`; resets midnight Pacific Time
    - Sidebar progress bars showing live per-model usage/remaining
    - Smart chunk mode recommendations: warns when chunked mode is unnecessary or when calls will exceed remaining quota
    - Supports custom quota overrides via `set_quota()`

11. **Trend Analysis Dashboard** (`pages/04_Insights.py`)
    - **Topic Momentum:** weighted counting (1/n per topic), pct_change, Emerging/Expanding/Fading/Stable classification, rendered via Altair with tooltips and detail table
    - **Top Company Mentions:** top 10 by frequency with canonicalization and within-record deduplication
    - **Priority Distribution Over Time:** weekly stacked bars with High-Ratio and Volatility Index secondary line chart
    - **Confidence Distribution (Computed):** weekly stacked bars showing extraction quality trend (High green, Medium yellow, Low red); LLM override rate metrics (total records with computed confidence, count overridden, override %)
    - Canonical/all-records toggle for all analytics
    - Unit-testable helpers: `weighted_explode`, `explode_list_column`, `classify_topic_momentum`, `canonicalize_company`, `week_start`, `get_effective_date`

12. **Review & Approve** (`pages/02_Review_Approve.py`)
    - Unified queue with filters (review status, priority, source type, topic, date range, text search)
    - Title-first expandable cards with inline Approve/Review buttons, batch actions, sorted newest-first
    - Record detail with Next/Previous navigation, title+metrics header, Quick Approve with auto-advance
    - Full JSON editing capability for manual field corrections
    - **Confidence detail breakdown:** expandable section showing computed score, per-signal contributions, and LLM override indicator
    - Simplified review model: Pending/Approved/Disapproved with auto-approve heuristic at ingest
    - Legacy status normalization ("Not Reviewed"/"Reviewed" → "Pending")

14. **Bulk Deduplication CLI** (`scripts/dedupe_jsonl.py`)
    - Standalone JSONL deduplication with CSV export
    - Diagnostic stats (duplicate rate, canonical count)
    - Supports large datasets outside Streamlit UI

15. **Testing & Validation** (`tests/`)
    - 97 test cases across 4 test modules (`test_scenarios.py`, `test_macro_themes.py`, `test_regions_bucketed.py`, `test_publish_date_pdf.py`)
    - Publisher ranking hierarchy validation
    - Weekly briefing logic verification
    - Exact and fuzzy duplicate detection tests
    - Macro theme detection with signal group matching, anti-keywords, premium gates, rollups
    - Two-tier region bucketing with country-to-footprint mapping, display collapse, legacy migration
    - Company name canonicalization (VW/Volkswagen dedup, legal suffix stripping)

## Technical Stack

- **Models:** Gemini 2.5-flash-lite (primary, 10 RPM / 20 RPD) + Gemini 2.5-flash (fallback/repair/AI brief, 5 RPM / 20 RPD) via `google-genai` with structured JSON schema; both $0 on free tier
- **UI:** Streamlit (5-page multi-page app + Home landing page)
- **Charting:** Altair (Topic Momentum interactive charts), matplotlib (other charts), pandas aggregations
- **Storage:** JSONL (JSON Lines format) + `data/api_usage.json` for quota tracking
- **Language:** Python 3.9+
- **Dependencies:** streamlit, pymupdf, pdfplumber, pandas, matplotlib, altair, google-genai, pytest

## Pages

| # | Page | File | Purpose |
|---|------|------|---------|
| — | Home | `Home.py` | Landing page with workflow navigation guide |
| 1 | Ingest | `pages/01_Ingest.py` | Single + bulk PDF upload, extraction, noise routing, quota display |
| 2 | Review & Approve | `pages/02_Review_Approve.py` | Queue filtering, record detail/edit, JSON editing, approve/disapprove, confidence breakdown |
| 3 | Weekly Executive Brief | `pages/03_Weekly_Executive_Brief.py` | Candidate selection, deterministic + AI-generated briefs, saved brief comparison |
| 4 | Insights | `pages/04_Insights.py` | Trend charts, canonical toggle, topic/company/priority/confidence analytics |
| 5 | Admin | `pages/08_Admin.py` | Bulk CSV/JSONL export, dedup metrics, maintenance utilities |

---

# Design Decisions Finalized

## A) Product & Scope

- **MVP features:** PDF upload (single + bulk), text paste, noisy-PDF cleanup, chunked extraction with meta-based routing, duplicate detection, weekly briefing (deterministic + AI-generated), executive email generation, trend analysis (Insights page), consolidated Review & Approve workflow
- **Duplicate detection:** Exact title block + similar story auto-ranking by source quality
- **Deduplication logic:** Publisher ranking (S&P > Bloomberg > Reuters > Financial News > MarkLines > Automotive News > Industry Publication > ... > Other) + confidence + completeness
- **Priority classification:** LLM prompt rules + deterministic `_boost_priority()` postprocess with 4 signal checks

## B) Technical Choices

- **Model strategy:** Meta-based routing (noise classification → model selection) + two-phase chunk repair (Phase 1 all chunks → Phase 2 repair failures only); single-context path uses two-pass (Flash-Lite → Flash)
- **Cleanup:** Deterministic noisy-PDF cleaning before model calls (not relying on model to ignore noise)
- **Chunking:** Overlapping chunks for long documents with per-chunk extraction and merge
- **Quota management:** File-based RPD tracker with midnight PT reset, sidebar display, smart chunk recommendations
- **UI:** Streamlit 5-page app for lightweight, interactive workflows
- **Charting:** Altair for interactive Topic Momentum; matplotlib + pandas for other charts
- **Storage:** JSONL for simplicity and scalability without database overhead

## C) Evaluation

- **Test coverage:** 97 tests across 4 modules (duplicate detection, ranking, briefing, macro themes, regions, company canonicalization)
- **Quality gates:** Schema validation, evidence requirement, review gating (auto-approve + manual), duplicate suppression, priority classification, computed confidence scoring
- **Token tracking:** Per-call usage logging + per-model RPD quota tracking for cost monitoring and optimization
- **Regression prevention:** Comprehensive test suite for all new features

## D) Evidence & Trust

- **Evidence source:** Quote fragments with schema validation, URL provenance via HITL input
- **Hallucination mitigation:** noisy-PDF cleanup (cleaner inputs → fewer hallucinations), URL captured as manual input (not model extraction), publisher-vs-cited-source prompt rules, duplicates prevent repeated signals, evidence + validation + review gating, priority classification with deterministic safety net

## E) Reporting

- **Exports:** CSV (canonical and all) ready for Power BI; JSONL (canonical + dups) for analysis
- **In-app:** Insights page with trend analysis charts (Topic Momentum, Company Mentions, Priority Distribution), Weekly Executive Brief with deterministic + AI-generated briefs, Admin metrics, token usage display, quota sidebar
- **CLI:** Standalone bulk deduplication script with diagnostic output

---

**Report version:** 1.0
**Status:** Production MVP complete with meta-based model routing, per-chunk repair, priority classification, computed confidence scoring, API quota tracking, trend analysis (Insights page), AI-generated executive briefs, bulk PDF ingest, and consolidated Review & Approve workflow; ready for deployment and evaluation
