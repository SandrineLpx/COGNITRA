"""
Fix the Renault Group record with incorrect publish_date (2025-12-31 should be 2026-02-19).
"""
import json
from pathlib import Path


def fix_renault_date():
    records_path = Path("data/records.jsonl")
    if not records_path.exists():
        print(f"Error: {records_path} not found")
        return

    # Read all records
    records = []
    with open(records_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    # Find and fix the Renault record
    fixed = False
    for rec in records:
        if rec.get("title") == "Renault Group reports net loss of €10.9B during 2025":
            if rec.get("publish_date") == "2025-12-31":
                print(f"Found Renault record with incorrect date: {rec['record_id']}")
                print(f"  Before: publish_date={rec.get('publish_date')}, event_date={rec.get('event_date')}")

                # Fix the dates
                rec["publish_date"] = "2026-02-19"
                rec["event_date"] = None  # Clear the event_date since 2026-02-19 was incorrectly moved there
                rec["publish_date_confidence"] = "High"

                # Update provenance to reflect manual correction
                if "_mutations" not in rec:
                    rec["_mutations"] = []
                rec["_mutations"].append(
                    {
                        "field": "publish_date",
                        "before": "2025-12-31",
                        "after": "2026-02-19",
                        "source": "script:fix_renault_date",
                        "reason": "corrected_fiscal_year_end_misidentification",
                    }
                )
                rec["_mutations"].append(
                    {
                        "field": "event_date",
                        "before": "2026-02-19",
                        "after": None,
                        "source": "script:fix_renault_date",
                        "reason": "removed_incorrectly_reclassified_publish_date",
                    }
                )

                print(f"  After: publish_date={rec['publish_date']}, event_date={rec.get('event_date')}")
                fixed = True
                break

    if not fixed:
        print("Renault record not found or already has correct date")
        return

    # Write back all records
    with open(records_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"Fixed Renault record and saved to {records_path}")


if __name__ == "__main__":
    fix_renault_date()
