---
name: Monthly improvement loop using index.jsonl
description: Codex prompt to measure quality trend + identify recurring defect types (geo leakage, canonicalization gaps, uncertainty section issues).

---

Validate the latest brief:
- brief_YYYYMMDD_HHMMSS.md
- brief_YYYYMMDD_HHMMSS.meta.json
against the source-of-truth records in records.jsonl.

Use BRIEF_GENERATION_STANDARD.md + QUALITY_CHECKLIST.md Section B.

Output:
- Any HIGH issues (ungrounded claims, wrong certainty, REC mismatch, geo distortion)
- Medium/Low improvements
- Concrete rewrite suggestions for the brief sections, preserving REC citations.
