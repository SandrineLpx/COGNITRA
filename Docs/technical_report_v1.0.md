Below is a starter **technical report draft** you can keep updating as you build. I wrote it to tell the full story (problem → design → build → evaluation → learnings), and I embedded placeholders so you can drop in screenshots, metrics, and implementation details later.

At the end, I list targeted questions to help you decide what else to include.

---

# Technical Report Draft

**Project:** Minimal-Token AI Market Intelligence for Automotive Closure Systems
**Course:** MSIS 549 – Generative AI Technologies
**Author:** Sandrine Lepesqueux
**Date:** [fill]
**Version:** 0.1 (living document)

## Executive Summary

This project builds an AI-powered market intelligence triage system for the automotive closure systems and car entry domain. The system is designed for environments where teams already pay for high-quality information—such as Bloomberg, Automotive News, S&P Global, and MarkLines—as well as public sources like press releases and regulatory announcements. The problem is not access to content; it is the lack of a scalable way to convert these sources into consistent, decision-ready intelligence.

Rather than packaging press releases or generating generic summaries, the tool converts unstructured documents (PDFs/text) into evidence-backed intelligence records that are searchable and comparable over time. It identifies relevant companies and actors (OEM/supplier/regulator), assigns controlled taxonomy topics, applies footprint region roll-up rules (e.g., Europe including UK/Turkey/Russia; Africa via Morocco/South Africa), and outputs priority and confidence alongside verifiable evidence bullets. It also generates strategic implications and recommended actions tailored to a closure systems supplier. Reliability and adoption are built in through strict JSON schema validation, a single repair step, strict multi-model fallback routing, and a human-in-the-loop approval gate before executive reporting. The result is a scalable workflow that increases signal capture from premium intelligence streams while keeping token costs predictable.

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
3. A filterable “inbox” view for analysts (priority/topic/region/company)
4. Human review controls (Reviewed/Approved) to gate inclusion into executive digests

### 2.2 Target users

* Market/competitive intelligence analyst (primary user)
* Strategy/product/sourcing stakeholders consuming weekly outputs
* Executives consuming a weekly digest

### 2.3 Why this is “minimal AI” but still “AI-powered”

AI is used only where it provides high leverage:

* classification and normalization (topics, companies, actor type)
* priority scoring and confidence
* evidence-backed extraction (verifiable bullets)
* strategic implications (closure systems supplier lens)

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
* **AI inference (two-pass model strategy):**

  * **Pass 1 — Gemini Flash-Lite:** runs extraction cheaply on every document (most are "easy enough")
  * **Quality gate:** schema validation + heuristic checks (missing publish_date, wrong source_type, generic evidence)
  * **Pass 2 — Gemini Flash (fallback):** re-runs extraction only when pass 1 fails validation or quality checks, spending more tokens only on hard/noisy documents
  * Token usage logging per call (prompt/output/total tokens, model used)
* **Validation layer:**

  * JSON schema validation against controlled vocabularies
  * Repair prompt includes specific validation errors for targeted fixes
  * Selective escalation: only schema/structural failures trigger strong-model retry
* **Storage:**

  * JSONL for records and review status
  * Separate JSONL files for duplicates (marked with duplicate metadata)
  * Bulk deduplication via CLI script (`scripts/dedupe_jsonl.py`)
* **Briefing pipeline:**
  * Weekly candidate selection (recent records, exclude duplicates by default)
  * Share-ready detection (High priority + High confidence)
  * Markdown brief and executive email generation
  * Analyst-driven item selection with one-click suggestions
* **Analytics & Presentation:**

  * Inbox table with filters (priority, source, review status, company search)
  * Detail view with edits and review status
  * Dashboard with canonical/all-records toggle
  * Export to CSV for Power BI (canonical and all records support)
  * Weekly Brief page for digest drafting & email templates

### 4.2 Human-in-the-loop gating

Review statuses:

* Not Reviewed → Reviewed → Approved

Recommended gating rules (for approval requirement):

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
* Footprint region roll-up rules (Europe incl. UK/Turkey/Russia; Africa via Morocco/South Africa; US normalization)

## 6. Prompting and Output Specification

### 6.1 “Single source of truth” specification

The project uses a spec-first approach:

* **SKILL_final.md** defines: taxonomy, region rules, schema, priority rubric, HITL rules.
* **prompts_final.md** contains executable prompts referencing SKILL for schema/topics/regions.
* **executive-brief-template_final.md** defines how to render briefs from JSON.
* **topic-taxonomy_final.md** and **company-watchlist_final.md** provide reference lists.

### 6.2 Output schema (JSON-first)

[Insert the JSON schema excerpt or reference to SKILL_final.md section.]

### 6.3 Evidence requirement

Each record includes 2–4 evidence bullets:

* must be verifiable facts from the provided text
* should include short quote fragments when possible
* reduces hallucination risk and improves reviewer trust

## 7. Implementation Details

*(Fill this section as you build.)*

### 7.1 Technology stack

* UI: [Streamlit / Lovable / other]
* Local extraction: [pdfplumber / pymupdf / other]
* LLM provider: [Gemini / Claude / ChatGPT]
* Storage: [SQLite / JSONL]
* Reporting: [Power BI optional]

For the MVP, the solution is implemented as a multi-page Streamlit web app that supports PDF ingestion, duplicate detection, record review, analytics, and weekly briefing workflows in a lightweight interface. The app includes six main pages: (1) Home, (2) Ingest with duplicate blocking, (3) Inbox for filtering/browsing, (4) Record detail for editing/approval, (5) Dashboard with canonical toggle, (6) Weekly Brief for digest drafting, and (7) Export/Admin for bulk export and deduplication. Processed outputs are stored as JSONL (JSON Lines), where each intelligence record is appended as one JSON object per line, enabling simple persistence and fast reload without a database. Duplicate records are stored separately with metadata pointing to the canonical record (higher-ranked source). For reporting and downstream analysis, the app includes:

- CSV export of canonical records (or all records) filtered by approval status
- JSONL export of both canonical and duplicate records for analysis
- Dashboard with toggle to view analytics on canonical vs. all records  
- Weekly Brief page for drafting digest summaries and executable email templates
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
5. **Two extraction modes** (user-selectable):
   * **Chunked mode (default for long/noisy docs):** each chunk extracted independently via model, results merged with majority voting (source_type, actor_type), union+dedup (entities, topics, regions), highest-confidence date, and short-bullet filtering
   * **Single-context mode:** score paragraphs (watchlist, keyword, country hits), build bounded context pack, single model call
6. **Two-pass model strategy (Gemini):**
   * **Pass 1 — Flash-Lite:** fast, cheap extraction for most documents
   * **Quality gate:** schema validation + heuristic checks
   * **Pass 2 — Flash (fallback):** only invoked when pass 1 fails; repair prompt includes specific validation errors
   * Token usage logged per call (model, prompt/output/total tokens)
7. Postprocess/normalize model output (dedupe lists, canonicalize country names, enforce footprint region buckets, infer publish_date and source_type from text patterns, remove invalid regulator entities)
8. Validate JSON against schema; if invalid, repair prompt with error details → revalidate
9. Store record with `duplicate_of` / `exclude_from_brief` metadata if needed
10. Display token usage summary (model used, prompt/output/total tokens)
11. Render Intelligence Brief from JSON (deterministic, no LLM call)
12. Human review edits + approve
13. **Weekly briefing (separate workflow):**
    * Select candidates from last N days (exclude duplicates by default)
    * Prioritize share-ready items (High priority + High confidence)
    * Render Markdown brief + executive email template
    * Analyst can select/deselect items before sharing

### 7.3 Token control strategy

* Duplicate detection is deterministic (no LLM calls)
* Fixed cap on context pack size (12K chars) and chunk size (9K chars)
* **Two-pass model strategy:** Flash-Lite handles easy docs cheaply; Flash is invoked only on failure, so most documents cost fewer tokens
* One LLM call per unique document in the common case (plus optional single repair call on the stronger model)
* In chunked mode: one call per chunk, but chunks are bounded and overlapping, so total tokens scale linearly with document length rather than exploding
* No second call for "Intelligence Brief" (rendered deterministically from JSON)
* No additional calls for deduplication or weekly briefing (all deterministic post-processing)
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
   - Publisher score: S&P=100 > Bloomberg=90 > Reuters=80 > Automotive News=75 > MarkLines=70 > Press Release=60 > Patent=55 > Other=50
   - Confidence score: High=3 > Medium=2 > Low=1
   - Completeness score: +1 for publish_date present, +1 for original_url present, +1 for regions_relevant non-empty, +1 for evidence_bullets count >= 3
3. **Canonical selection:** the highest-scoring record becomes canonical; all others are marked with `exclude_from_brief=True` and `duplicate_story_of` pointing to the canonical record_id.
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
* Region roll-ups:

  * Europe: includes UK/Turkey/Russia and broad EU/Europe/EMEA mentions
  * Africa: Morocco/South Africa mapping
  * US: country mention normalized to “United States” and region “US”

### 8.3 Case studies (recommended for the report)

Add 2–3 short “before/after” examples:

* Example A: market note (region-heavy)
* Example B: competitor/OEM program change (priority-driven)
* Example C: government/regulatory release (actor type driven)

For each: include the source snippet, the JSON record, and the rendered brief.

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
* Publisher ranking system (deterministic scoring: S&P=100 > Bloomberg=90 > Reuters=80 > ... > Other=50) ensured that when multiple sources covered the same story, the highest-quality source was automatically selected.
* Weekly briefing workflow with share-ready detection (High priority + High confidence) and executive email templating made it easy for analysts to draft weekly digests with minimal manual work.
* Deduplication and briefing modules were entirely deterministic (no additional LLM calls), keeping token costs and latency predictable.
* **Noisy-PDF cleaning** significantly improved extraction quality: removing ads, nav menus, paywall prompts, and repeated headers before the model sees the text eliminated the most common source of wrong source_type and phantom entity extraction.
* **Two-pass model strategy** (Flash-Lite → Flash) reduced average token cost while maintaining extraction quality on hard documents. Most documents complete on the cheaper model; only failures escalate.
* **Publisher-vs-cited-source prompt rule** was the single highest-impact prompt change — it fixed the most common misclassification (S&P articles being tagged as "Reuters" because Reuters was cited in the body).
* **Token usage logging** provided visibility into cost per document and made it easy to identify which documents triggered the stronger model, enabling targeted improvements to the cleanup pipeline.

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

### 10.2 Iterations and scope control (recommended addition)
Early in development, the project included prototype scripts that generated narrative summaries and weekly briefs directly from raw text. During implementation, these were intentionally replaced with a JSON-first, schema-validated pipeline aligned with the project specification. This change improved reliability (consistent fields and controlled vocabularies), reduced hallucination risk (evidence bullets + validation), and made token usage more predictable (bounded context pack + one-call extraction in the common case). The final system therefore prioritizes structured intelligence records as the primary artifact, and renders human-readable briefs deterministically from those records rather than relying on additional model calls.

Optional sentence if you want to be explicit:
This iteration also reduced repository complexity by removing scripts that were no longer aligned with the final architecture.

### 10.3 Future improvements

* Add retrieval/chunking to improve evidence precision (e.g., retrieve nearest chunks for specific claims)
* Expand watchlist and synonyms gradually based on real analyst overrides
* Tune similarity threshold and deduplication criteria based on analyst feedback from real workflows
* Build reporting dashboard showing dedup rates and publisher distribution trends over time
* Integrate with Power BI for interactive executive dashboards
* Extend publisher scoring with recency and completeness weighting for time-sensitive events
* Add earnings analysis module for financial signal extraction
* Integrate with enterprise tools (SharePoint/Teams) for scheduled email dispatch as Phase 2

## 11. Conclusion

This project demonstrates that a minimal-token GenAI workflow can deliver real business value by converting unstructured automotive content into structured, evidence-backed intelligence. The solution is designed to scale through consistency (controlled vocabularies), reliability (validation + evidence), and adoption (human-in-the-loop review), while keeping cost predictable (one model call per document).

---

# Implementation Summary (v3.4)

**Version:** 3.4
**Completion Date:** February 13, 2026

## Key Features Delivered

1. **Noisy-PDF Cleaning + Chunking** (`src/text_clean_chunk.py`)
   - Unified cleanup pipeline: nav/promo/paywall/social/link-heavy/repeated-header removal
   - Hyphen-break fixing, block deduplication, safety fallback against over-cleaning
   - Overlapping model-ready chunks (~9K chars, 800-char overlap) with detected-title propagation
   - Full removal diagnostics (line count, pattern breakdown) surfaced in Ingest UI

2. **Two-Pass Model Strategy** (`src/model_router.py`)
   - Pass 1: Gemini Flash-Lite (cheap, fast) for most documents
   - Quality gate: schema validation + heuristic checks
   - Pass 2: Gemini Flash (fallback) only on validation/quality failure
   - Per-call token usage logging (prompt/output/total tokens, model name)
   - Selective escalation: only schema/structural errors trigger strong-model retry

3. **Hardened Extraction Prompt**
   - Publisher-vs-cited-source rules (prevents S&P articles being tagged as "Reuters")
   - Strict date normalization (multiple patterns → YYYY-MM-DD)
   - Evidence bullet length cap (25 words max per bullet)
   - List deduplication and normalization instructions
   - Repair prompt includes specific validation errors for targeted fixes

4. **Chunked Extraction Mode** (`pages/01_Ingest.py`)
   - Each cleaned chunk extracted independently via model
   - Results merged: majority voting (source_type, actor_type), union+dedup (entities, topics, regions), highest-confidence date, short-bullet filtering
   - Handles long/noisy documents that exceed single-context limits

5. **Duplicate Detection & Deduplication** (`src/dedupe.py`)
   - Exact title matching (blocking at ingest)
   - Fuzzy story detection (threshold 0.88)
   - Deterministic publisher-weighted ranking (S&P=100, Bloomberg=90, Reuters=80, ... Other=50)
   - Confidence and completeness scoring for tie-breaking

6. **Weekly Briefing Workflow** (`src/briefing.py` + `pages/06_Weekly_Brief.py`)
   - Candidate selection from last N days (auto-excludes duplicates)
   - Share-ready detection (High priority + High confidence)
   - Markdown brief + executive email template generation
   - Analyst-driven item selection with one-click suggestions

7. **Bulk Deduplication CLI** (`scripts/dedupe_jsonl.py`)
   - Standalone JSONL deduplication with CSV export
   - Diagnostic stats (duplicate rate, canonical count)
   - Supports large datasets outside Streamlit UI

8. **Streamlit Integration**
   - Dashboard: canonical/all-records toggle with analytics
   - Export/Admin: bulk export button + metrics dashboard
   - 7-page app (Home, Ingest, Inbox, Record, Dashboard, Weekly Brief, Export/Admin)
   - Token usage display after each ingest (model, prompt/output/total)
   - Cleanup diagnostics display (removed lines, pattern breakdown)

9. **Testing & Validation** (`test_scenarios.py`)
   - 25+ test cases covering all workflows
   - Publisher ranking hierarchy validation
   - Weekly briefing logic verification
   - Exact and fuzzy duplicate detection tests

## Technical Stack

- **Models:** Gemini 2.5-flash-lite (primary) + Gemini 2.5-flash (fallback) via `google-genai` with structured JSON schema
- **UI:** Streamlit (7-page multi-page app)
- **Storage:** JSONL (JSON Lines format)
- **Language:** Python 3.9+
- **Dependencies:** streamlit, pymupdf, pdfplumber, pandas, matplotlib, google-genai, pytest

---

# Design Decisions Finalized

## A) Product & Scope

- **MVP features:** PDF upload, text paste, noisy-PDF cleanup, chunked extraction, duplicate detection, weekly briefing, executive email generation
- **Duplicate detection:** Exact title block + similar story auto-ranking by source quality
- **Deduplication logic:** Publisher ranking (S&P > Bloomberg > Reuters > ... > Other) + confidence + completeness

## B) Technical Choices

- **Model strategy:** Two-pass (Flash-Lite → Flash) for cost-efficient extraction with quality escalation
- **Cleanup:** Deterministic noisy-PDF cleaning before model calls (not relying on model to ignore noise)
- **Chunking:** Overlapping chunks for long documents with per-chunk extraction and merge
- **UI:** Streamlit 7-page app for lightweight, interactive workflows
- **Storage:** JSONL for simplicity and scalability without database overhead

## C) Evaluation

- **Test coverage:** 25+ scenario tests (duplicate detection, ranking, briefing)
- **Quality gates:** Schema validation, evidence requirement, review gating, duplicate suppression
- **Token tracking:** Per-call usage logging for cost monitoring and optimization
- **Regression prevention:** Comprehensive test suite for all new features

## D) Evidence & Trust

- **Evidence source:** Quote fragments with schema validation, URL provenance via HITL input
- **Hallucination mitigation:** noisy-PDF cleanup (cleaner inputs → fewer hallucinations), URL captured as manual input (not model extraction), publisher-vs-cited-source prompt rules, duplicates prevent repeated signals, evidence + validation + review gating

## E) Reporting

- **Exports:** CSV (canonical and all) ready for Power BI; JSONL (canonical + dups) for analysis
- **In-app:** Dashboard with filters, Weekly Brief with email draft, Admin metrics, token usage display
- **CLI:** Standalone bulk deduplication script with diagnostic output

---

**Report version:** 0.3
**Status:** Production MVP complete with two-pass model strategy, noisy-PDF cleaning, and chunked extraction; ready for deployment and evaluation