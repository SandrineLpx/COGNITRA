---
name: Record QC right after ingest (records.jsonl)
description: workflow for codex to follow to catch High-severity defects before they become “Approved”.

---

Scan records.jsonl (one JSON per line). For each record with review_status == "Pending" or recently created, apply QUALITY_CHECKLIST.md Section A.

Output:
1) A list of HIGH severity blockers per record_id (must be zero to approve)
2) Medium/Low issues
3) Suggested fixes (which file to change: postprocess.py/constants.py/model_router.py)

Files:
- records.jsonl
- QUALITY_CHECKLIST.md
