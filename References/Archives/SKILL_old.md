---
name: automotive-market-intel
description: >
  Minimal-token AI workflow that converts automotive news, press releases, and market notes into structured,
  evidence-backed intelligence records for closure systems and car entry markets, plus optional executive-ready
  briefs (rendered from JSON without extra model calls).
version: 2.0
---

# Automotive Market Intelligence Skill (Final Spec)

## 1) Problem and why it matters
Teams pay for premium information (news, market notes, press releases) but still miss key signals because:
- content is unstructured (PDFs, links, long articles),
- analysis time does not scale,
- insights are hard to search, compare, or reuse,
- stakeholders want consistent, executive-friendly outputs.

This skill defines a minimal-AI approach that prioritizes:
- structured metadata over long summaries,
- evidence-backed claims,
- consistent taxonomy and region relevance,
- human review before executive reporting.

## 2) Target users
Primary users:
- Market/competitive intelligence analysts
- Strategy, product, and sourcing teams who need triage and traceability

Secondary users:
- Executives who consume weekly/monthly digests

## 3) Scope and positioning
This skill focuses on **closure systems and car entry markets**, including:
- latches, cinching, handles, power closures
- door modules and related mechatronics
- smart entry and access technologies (e.g., UWB, digital key)
- safety and regulatory impacts relevant to closures/access

Out of scope for the MVP:
- deep technical patent analysis beyond extraction/tagging
- long-form article summaries (avoid unless strictly needed)

## 4) Minimal-token design principles (core of the approach)
To control cost/tokens and improve reliability:
1) **Do local extraction first** (no AI): convert PDF to text, split into paragraphs.
2) **Select a short context pack** (no AI):
   - title + first ~800–1200 words
   - plus the top “hit paragraphs” (watchlist/keyword/country matches)
3) **One model call per document** to produce **strict JSON**.
4) **Validate JSON**. If invalid, run a single “fix JSON only” repair call.
5) **Render the Intelligence Brief from JSON** (no second model call).
6) Require **human review** for high-impact items before they appear in executive reports.

This is “AI enough” because the model performs non-trivial reasoning:
- entity extraction, topic classification, priority scoring,
- evidence-grounded key facts,
- strategic implications for a closure systems supplier.

## 5) Canonical topics (controlled vocabulary)
Use these labels exactly. Multi-label: 1–3 topics per item.

- OEM Strategy & Powertrain Shifts
- Closure Technology & Innovation
- OEM Programs & Vehicle Platforms
- Regulatory & Safety
- Supply Chain & Manufacturing
- Technology Partnerships & Components
- Market & Competition
- Financial & Business Performance
- Executive & Organizational

## 6) Footprint regions and roll-up rules (relevance signal)
Footprint regions (Kiekert relevance):
- India
- China
- Europe (including Russia)
- Africa
- US
- Mexico
- Thailand

Roll-up rules:
- **Europe (including Russia)** includes UK and Turkey and Russia; broad mentions like Europe, EU, European, EMEA map here.
- **Africa** roll-up is primarily driven by production footprint: Morocco and South Africa (also tag Africa on broad mentions).
- Always populate `country_mentions` with **any** countries explicitly mentioned.
- For the US: normalize country mentions to **United States**, but use region label **US** for region roll-ups.

## 7) Human-in-the-loop (HITL) operating model
HITL is built into the workflow to improve trust and prevent “AI-only” decisions.

### Review statuses
- Not Reviewed: AI-generated record exists but not validated.
- Reviewed: a human checked the content and corrected tags if needed.
- Approved: safe to include in executive reporting/distribution.

### Recommended gating rules
Require human approval when any of the following is true:
- `priority = High`
- `confidence = Low`
- `mentions_our_company = true`
- `actor_type` is government/regulator AND `region_signal_type` is trade_policy/regulation/geopolitics

## 8) Data inputs and sources
Accepted inputs:
- PDF articles or market notes (clean text extraction preferred)
- Press releases (PDF or text)
- Copy/pasted article text or URL-derived text (optional)

Typical source types:
- Bloomberg, Reuters, Automotive News, Press Release, Patent, Other

## 9) Output: structured record schema (JSON-first)
The model returns **valid JSON only** following the schema below (keys required unless marked optional).

```json
{
  "title": "string",
  "source_type": "Bloomberg | Automotive News | Reuters | Patent | Press Release | Other",
  "publish_date": "YYYY-MM-DD | null",
  "publish_date_confidence": "High | Medium | Low",
  "original_url": "string | null",

  "actor_type": "oem | supplier | tech_partner | government | regulator | industry_group | media | other",
  "government_entities": ["string"],

  "companies_mentioned": ["string"],
  "mentions_our_company": true,
  "topics": ["OEM Strategy & Powertrain Shifts", "Closure Technology & Innovation"],
  "keywords": ["string"],

  "country_mentions": ["string"],
  "regions_mentioned": ["string"],
  "regions_relevant_to_kiekert": ["India", "Europe (including Russia)"],
  "region_signal_type": "trade_policy | geopolitics | regulation | oem_activity | supplier_activity | demand | logistics | fx_financing",
  "supply_flow_hint": "string | null",

  "priority": "High | Medium | Low",
  "confidence": "High | Medium | Low",

  "evidence_bullets": ["string"],
  "key_insights": ["string"],
  "strategic_implications": ["string"],
  "recommended_actions": ["string"],

  "review_status": "Not Reviewed | Reviewed | Approved",
  "notes": "string | null"
}
```

Constraints:
- `topics`: 1–3 canonical topics.
- `keywords`: 5–12 short keywords/phrases.
- `evidence_bullets`: 2–4 bullets. Each bullet must be verifiable from the input text (prefer dates, numbers, named entities, policy actions). If possible, include a short quote fragment in double quotes.
- `key_insights`: 2–4 bullets (interpretation).
- `strategic_implications`: 2–4 bullets written for a closure systems supplier.
- `recommended_actions`: 1–3 bullets, optional but preferred for High priority.
- Never invent facts. If uncertain, lower `confidence` and keep claims conservative.

## 10) Priority scoring (simple, defensible)
Use these heuristics consistently:

### High priority
- Major OEM strategy shifts affecting platform/powertrain mix or sourcing strategy
- Major competitor moves affecting closures/access content or capacity
- Regulatory or safety changes with compliance impact
- Supply disruptions (plant shutdowns, sanctions, border constraints) affecting footprint regions
- M&A, insolvency, major restructurings affecting supply stability
- Awards/wins or major sourcing decisions tied to closures/car entry

### Medium priority
- Market demand/mix changes in footprint regions
- Partnerships or component sourcing with plausible impact on closures/access
- Program updates with meaningful timing/volume implications

### Low priority
- Generic commentary with limited operational detail
- Weak signals without concrete facts (unless footprint impact is explicit)

## 11) Templates and prompts (implementation artifacts)
This skill is designed to work with:
- `prompts_final.md` for model prompts (single-doc JSON extraction + JSON repair + optional weekly synthesis)
- `executive-brief-template_final.md` for formatting Intelligence Briefs and weekly digests
- `topic-taxonomy_final.md` for topic definitions
- `company-watchlist_final.md` for company normalization and cheap pre-filters

## 12) How to generate an Intelligence Brief without extra tokens
To keep token usage low:
- Do **not** call the model again for the brief.
- Render the Intelligence Brief by mapping JSON fields into the Intelligence Brief template:
  - Title, Source, Dates
  - Companies, Actor Type, Geography (countries/regions)
  - Topics, Priority/Confidence
  - Evidence → Key Insights → Strategic Implications → Recommended Actions
  - Review status and reviewer fields

## 13) Demo concept (GenAI & Agentic Fair)
A strong, reliable demo should show:
1) Upload a PDF (or paste text).
2) Tool outputs a structured record (JSON) and a readable Intelligence Brief.
3) User edits tags (HITL) and marks the item Reviewed/Approved.
4) Inbox view filters by Priority/Region/Topic/Company.
5) Optional: export CSV for Power BI to show trends (scalability story).

Backup plan:
- Preload 2–3 sample documents and precomputed JSON outputs.

---

End of skill.
