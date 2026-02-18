# Cognitra Weekly Executive Brief Generation Standard

This standard defines what “executive-grade” means for Cognitra output.

## 1) Inputs
- Only include records where:
  - review_status == Approved
  - is_duplicate != true
- Each record must include:
  - evidence_bullets (verifiable)
  - priority + confidence
  - geography fields (policy-compliant)
  - topics + macro themes (if available)

## 2) Grounding Rules (non-negotiable)
- Every major claim must cite ≥ 1 REC ID that contains supporting evidence.
- Never upgrade certainty:
  - “weighing / sources said / expected / could” must stay probabilistic.
- If a claim is an implication for Kiekert, label it as:
  - “Implication” (inference) and keep it tied to the evidence.

## 3) Required Sections + Quality Bar

### A. Executive Summary
- 3 bullets max
- Each bullet must:
  - synthesize across ≥ 2 RECs OR explicitly state it is single-REC
  - include “so what for Kiekert”
  - cite RECs

### B. High Priority Developments
- 1–3 items (one per top OEM if applicable)
- Format per item:
  - What happened (facts) + evidence tie
  - Why it matters (short)
  - Kiekert implication (inference)
  - Watch-for trigger (next signal)

### C. Footprint Signals
- Show two layers if available:
  1) Footprint primitives (country-derived, deterministic)
  2) Region groups (filter buckets like Asia/Europe/MEA) if implemented
- Always note: “Based on approved records.”

### D. Key Developments by Topic
- For each canonical topic: 1–3 bullets
- Each bullet includes REC IDs

### E. Emerging Trends
- 2–3 trends
- Each trend must cite ≥ 2 RECs (cross-record requirement)

### F. Conflicts & Uncertainty (mandatory)
Include when any source contains uncertainty language:
- forecast / could / weighing / expected / sources said / speculation
Each bullet must cite REC IDs and explain:
- what is uncertain
- what would confirm/disconfirm

### G. Recommended Actions
- 3 actions max
- Each action must include:
  - Owner role
  - Concrete output artifact (forecast update, risk memo, pricing playbook, supplier list, etc.)
  - Time horizon
  - Trigger to revisit

## 4) Style + Executive Credibility
- No boilerplate statements that contradict uncertainty.
- Avoid buzzwords. Prefer plain language.
- If confidence is Medium/Low, be explicit about limits.
- Keep it scannable: tight bullets, no long paragraphs.

## 5) Post-generation validation (fast)
- Spot-check 5 claims:
  - Verify REC IDs truly support them
- Ensure at least one uncertainty bullet exists when applicable
- Ensure “Footprint signals” align with record geo policy
