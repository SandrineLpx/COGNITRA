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
* paragraph selection
* schema validation and error handling
* brief formatting from JSON

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
* **Local processing (non-AI):**

  * PDF → text extraction
  * paragraph segmentation
  * keyword/watchlist/country hit scoring
  * creation of a short “context pack”
* **AI inference (single call per doc):**

  * strict JSON extraction (schema-defined)
  * evidence bullets + insights + implications
* **Validation layer:**

  * JSON schema validation
  * “fix JSON only” repair prompt (single retry)
* **Storage:**

  * SQLite (or JSONL) for records and review status
* **Presentation:**

  * Inbox table with filters
  * Detail view with edits and review status
  * Export to CSV for Power BI

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

For the MVP, the solution is implemented as a multi-page Streamlit web app that supports PDF ingestion, record review, and analytics in a lightweight interface. Processed outputs are stored as JSONL (JSON Lines), where each intelligence record is appended as one JSON object per line, enabling simple persistence and fast reload without a database. For reporting and downstream analysis, the app includes an optional CSV export (e.g., exporting “Approved” records only) to support tools like Power BI and other spreadsheet-based workflows.

### 7.2 Processing pipeline (step-by-step)

1. User uploads PDF (with optional manual URL field for provenance)
2. Extract text locally
3. Split into paragraphs
4. Score paragraphs:

   * company watchlist matches
   * closure keyword hits
   * country mentions
5. Build context pack (cap length)
6. Call LLM to output strict JSON (using Gemini-compatible schema)
7. Postprocess/normalize model output (dedupe lists, canonicalize country names, enforce footprint region buckets, remove invalid regulator entities)
8. Validate JSON against schema and retry once if needed
9. Store record
10. Render Intelligence Brief from JSON
11. Human review edits + approve

### 7.3 Token control strategy

* Fixed cap on context pack size
* One LLM call per document (plus optional single repair call)
* No second call for “Intelligence Brief” (rendered deterministically)

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

### 10.2 What was challenging

* PDFs vary widely in extractability and formatting.
* Publish date extraction may be inconsistent depending on source format.
* Company alias handling requires careful tuning (avoid overcomplication).
* Some articles have weak signal-to-noise; prioritization must remain conservative.
* Provider-specific schema constraints required explicit compatibility work: the google-genai SDK enforces a Gemini-specific type system (single uppercase enum values like STRING, OBJECT, NULL) that differs from standard JSON Schema conventions (e.g., type: ["string","null"]). This gap was not surfaced until runtime and required rewriting the schema definition and reordering the postprocessing/validation pipeline.
* URL hallucination risk emerged when the model was asked to extract original_url from PDFs that did not contain one; mitigating this required moving URL capture to a human-in-the-loop input rather than relying on model extraction.

### 10.2 Iterations and scope control (recommended addition)
Early in development, the project included prototype scripts that generated narrative summaries and weekly briefs directly from raw text. During implementation, these were intentionally replaced with a JSON-first, schema-validated pipeline aligned with the project specification. This change improved reliability (consistent fields and controlled vocabularies), reduced hallucination risk (evidence bullets + validation), and made token usage more predictable (bounded context pack + one-call extraction in the common case). The final system therefore prioritizes structured intelligence records as the primary artifact, and renders human-readable briefs deterministically from those records rather than relying on additional model calls.

Optional sentence if you want to be explicit:
This iteration also reduced repository complexity by removing scripts that were no longer aligned with the final architecture.

### 10.3 Future improvements

* Add retrieval/chunking to improve evidence precision
* Expand watchlist and synonyms gradually based on real overrides
* Add a lightweight “weekly digest builder” that compiles only Approved items
* Integrate with enterprise tools (SharePoint/Teams) as Phase 2
* Add earnings analysis

## 11. Conclusion

This project demonstrates that a minimal-token GenAI workflow can deliver real business value by converting unstructured automotive content into structured, evidence-backed intelligence. The solution is designed to scale through consistency (controlled vocabularies), reliability (validation + evidence), and adoption (human-in-the-loop review), while keeping cost predictable (one model call per document).

---

# Questions for you (to shape the final technical report)

## A) Product and scope

1. What is the exact MVP you will demo: PDF upload only, or PDF + pasted text/URL too?
2. Do you want the report to frame this as a “closure systems intelligence tool” only, or “industry-agnostic with a closure-focused demo”?

## B) Technical choices (important for the report)

3. Which model will you use in the final build (Gemini vs Claude vs ChatGPT), and why (structured JSON reliability vs writing quality vs ease of use)?
4. Which UI will you use: Streamlit, Lovable, or something else?

## C) Evaluation (what’s realistic)

5. How many documents do you think you can realistically process for evaluation (5, 10, 20)?
6. Do you want to track “override rate” (how often you changed AI tags), or keep evaluation simpler?

## D) Evidence and trust

7. Do you want evidence bullets to include paragraph indices (e.g., “P7: …”) or just quote fragments?
8. Should the report include a short section on hallucination risk and mitigation (schema validation + evidence + HITL)?

## E) Reporting

9. Will you include Power BI in the demo/report as the “scalability story,” or keep everything inside the app?

If you answer these, I can update this draft into a tighter version 0.2 with your decisions baked in and add a 2–3 page “Implementation + Evaluation” core that reads like a polished final report.