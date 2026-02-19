"""
Migration script: apply region/country name overhaul to data/records.jsonl.

Run once after deploying the new_country_mapping.csv-based region architecture.
Rewrites old region values in-place using a dry-run mode by default.

Usage:
    python scripts/migrate_region_overhaul.py            # dry run (no changes)
    python scripts/migrate_region_overhaul.py --apply    # apply and overwrite records.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Old → new name mapping for region fields
# ---------------------------------------------------------------------------
REGION_MIGRATION_MAP: dict[str, str] = {
    "Western Europe": "West Europe",
    "Eastern Europe": "East Europe",
    "Latin America": "South America",
    "Asia": "South Asia",
    "US": "United States",
    "Africa": "Africa",           # no change, kept for completeness
    "India": "India",             # no change
    "China": "China",             # no change
    "Mexico": "Mexico",           # no change
    "Thailand": "Thailand",       # no change
    "Japan": "Japan",             # no change
    "Russia": "Russia",           # no change
    "Europe (including Russia)": "Europe",
}

# Region fields present in each record
REGION_FIELDS = ["regions_mentioned", "regions_relevant_to_apex_mobility"]


def migrate_record(rec: dict) -> tuple[dict, list[str]]:
    """Return (updated_record, list_of_change_descriptions)."""
    changes: list[str] = []
    for field in REGION_FIELDS:
        old_list = rec.get(field)
        if not isinstance(old_list, list):
            continue
        new_list = []
        for val in old_list:
            mapped = REGION_MIGRATION_MAP.get(val, val)
            if mapped != val:
                changes.append(f"  {field}: '{val}' → '{mapped}'")
            new_list.append(mapped)
        rec[field] = new_list
    return rec, changes


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate region names in records.jsonl")
    parser.add_argument("--apply", action="store_true",
                        help="Apply changes and overwrite records.jsonl (default: dry run)")
    parser.add_argument("--jsonl", default="data/records.jsonl",
                        help="Path to records JSONL file (default: data/records.jsonl)")
    args = parser.parse_args()

    jsonl_path = Path(args.jsonl)
    if not jsonl_path.exists():
        print(f"No records file found at {jsonl_path} — nothing to migrate.")
        return

    records: list[dict] = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    total_changed = 0
    updated_records: list[dict] = []
    for rec in records:
        updated, changes = migrate_record(rec)
        updated_records.append(updated)
        if changes:
            total_changed += 1
            title = rec.get("title", "<no title>")[:60]
            print(f"[CHANGE] {title}")
            for c in changes:
                print(c)

    print(f"\n{'=' * 60}")
    print(f"Total records: {len(records)}")
    print(f"Records with changes: {total_changed}")

    if not args.apply:
        print("\nDRY RUN — no changes written. Use --apply to apply.")
        return

    # Back up the original file
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = jsonl_path.with_suffix(f".pre_region_overhaul_{ts}.jsonl")
    shutil.copy2(jsonl_path, backup_path)
    print(f"\nBackup written to: {backup_path}")

    with open(jsonl_path, "w", encoding="utf-8") as f:
        for rec in updated_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"Records updated and written to: {jsonl_path}")


if __name__ == "__main__":
    main()
