# Cognitra Weekly Quality Checklist (Pre-Publish)

Use this checklist before marking records Approved and before publishing the Weekly Executive Brief.

## A. JSON Extraction QC (per record)

### A1. High-severity blockers (must be ZERO)
- [ ] No hallucinations: every evidence_bullet is present in source
- [ ] No wrong values: numbers (€, %, volumes, dates) match the source
- [ ] No wrong entities: key company / OEM / product / platform names correct
- [ ] No wrong geo signals:
  - [ ] country_mentions contains only explicit operational countries (per policy)
  - [ ] regions_relevant_to_apex_mobility derived deterministically (no “display buckets” leakage)
- [ ] No wrong publisher/source_type

### A2. Medium issues (allowed but tracked)
- [ ] No duplicates (companies, countries, regions)
- [ ] Missing secondary but relevant signals captured (e.g., guidance changes, major org moves)
- [ ] Canonicalization consistent (Toyota Motor Corp → Toyota, VW → Volkswagen Group, etc.)

### A3. Evidence quality
- [ ] Evidence bullets are atomic and verifiable (1 fact per bullet)
- [ ] Evidence covers:
  - [ ] 1–2 core facts (what happened)
  - [ ] quantified impact (if present)
  - [ ] timing (publish date + event date if relevant)
- [ ] Key insights do not exceed evidence (no “decision made” when source says “considering”)

### A4. Confidence / priority sanity
- [ ] confidence aligns with evidence density and source_type
- [ ] priority_reason is explainable (one sentence)
- [ ] macros/themes make sense (no “Tariff” theme from region-only presence)

## B. Executive Brief QC (per brief)

### B1. High-severity blockers (must be ZERO)
- [ ] No brief claim without REC support
- [ ] No wrong certainty: “reviewing/weighing” is not written as “scrapping/decided”
- [ ] No geo distortion in “Footprint signals”
- [ ] No REC mismatch (REC IDs map to correct records)

### B2. Uncertainty handling (must exist when applicable)
- [ ] "Conflicts & Uncertainty" is non-empty if any record contains:
  forecast / could / weighing / sources said / expected / may / might /
  uncertain / preliminary / unconfirmed / estimated / projected / reportedly /
  reconsider / reviewing / speculation
  (canonical list: `UNCERTAINTY_WORDS` in `src/constants.py`)
- [ ] Each uncertainty item cites the REC that contains it

### B3. Synthesis quality
- [ ] At least 2 cross-record themes (not per-record summaries)
- [ ] Clear “so what for Apex Mobility” per theme:
  cost pressure / platform timing / footprint risk / sourcing risk / tech content shifts
- [ ] Actions have:
  owner + concrete next step + time horizon + trigger to watch

## C. Output packaging
- [ ] Brief includes appendix: “Items Covered” count and REC list
- [ ] All sections present and consistent with template
- [ ] Final quick scan: reads like a human wrote it (no boilerplate contradictions)
