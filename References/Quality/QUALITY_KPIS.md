# Cognitra Quality KPIs

This scorecard tracks quality at two levels:
1) Record extraction quality
2) Executive brief quality

## 1. Record Extraction KPIs (weekly)

### KPI-R1: High-severity defects per record (target: 0)
High severity includes:
- hallucination
- wrong numeric value
- wrong company / OEM / platform
- wrong geo signal (country or derived footprint)
- wrong publisher/source_type

Metric:
- HighDefectsPerRecord = (#High issues) / (#records)

Target:
- 0.00

### KPI-R2: Medium-severity defects per record (target: ≤ 1.0)
Medium severity includes:
- duplicates
- missing secondary signals
- incomplete companies list (when it impacts themes/brief)
- weaker phrasing that slightly alters meaning

### KPI-R3: Evidence grounding coverage (target: ≥ 90%)
- % of records where all evidence bullets are source-verifiable

### KPI-R4: Canonicalization stability (target: ≥ 95%)
- % of records where canonical forms match reference tables (companies, countries, regions)

### KPI-R5: Geo determinism pass rate (target: ≥ 98%)
- % of records where:
  - regions_relevant_to_apex_mobility == f(country_mentions) (country-first rule)
  - no display buckets leak into footprint fields

## 2. Executive Brief KPIs (weekly)

### KPI-B1: Ungrounded claims count (target: 0)
- # of claims where GroundedToRecord = No

### KPI-B2: Overreach count (target: ≤ 2)
Overreach = correct direction but stronger certainty than source supports, or Apex Mobility implication asserted as fact without explicit support.

### KPI-B3: Uncertainty compliance (target: 100%)
- If any record contains uncertainty language, brief must include ≥ 1 uncertainty item.

### KPI-B4: Synthesis density (target: ≥ 2 cross-record themes)
- # of themes supported by ≥ 2 REC IDs

### KPI-B5: Action specificity score (target: ≥ 4/5)
Score 1–5:
1 = generic advice
3 = owner + timeframe but vague task
5 = owner + timeframe + concrete task + trigger + artifact output (e.g., forecast update, cost-down playbook, risk memo)

## 3. Weighted Quality Score (optional)

### Record Score (0–100)
Start at 100, subtract:
- High issue: -25 each
- Medium issue: -10 each
- Low issue: -2 each

### Brief Score (0–100)
Start at 100, subtract:
- Ungrounded claim: -25 each
- Wrong signal / wrong certainty: -20 each
- Overreach: -10 each
- Missing uncertainty when required: -20
- Missing cross-record synthesis (fewer than 2 themes): -15

## 4. Reporting cadence
- Weekly: KPI-R1..R5 and KPI-B1..B5
- Monthly: trendline + top recurring defect types + rules to adjust
