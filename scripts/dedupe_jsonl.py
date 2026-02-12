#!/usr/bin/env python
"""
CLI script to deduplicate JSONL records and export canonical/duplicate sets.

Usage:
    python scripts/dedupe_jsonl.py data/records.jsonl \\
        --out data/canonical.jsonl \\
        --dups data/duplicates.jsonl \\
        --csv data/canonical.csv

Options:
    --out: output path for canonical records (default: canonical.jsonl)
    --dups: output path for duplicate records (default: duplicates.jsonl)
    --csv: optional CSV export path (flattens lists)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.dedupe import dedupe_records


def load_jsonl(path: Path) -> list[dict]:
    """Load records from JSONL file."""
    records = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    records.append(rec)
                except json.JSONDecodeError as e:
                    print(f"Warning: skipping line {line_num}: {e}", file=sys.stderr)
        print(f"Loaded {len(records)} records from {path}", file=sys.stderr)
        return records
    except FileNotFoundError:
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)


def save_jsonl(records: list[dict], path: Path) -> None:
    """Save records to JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"Saved {len(records)} records to {path}", file=sys.stderr)


def flatten_list(val, sep="; ") -> str:
    """Flatten a list or return string as-is."""
    if isinstance(val, list):
        return sep.join(str(x) for x in val if x)
    if val is None:
        return ""
    return str(val)


def save_csv(records: list[dict], path: Path) -> None:
    """Save records as CSV with flattened lists."""
    if not records:
        return
    
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Get all unique keys from all records
    all_keys = set()
    for rec in records:
        all_keys.update(rec.keys())
    
    headers = sorted(all_keys)
    
    with path.open("w", encoding="utf-8", newline="") as f:
        # Write CSV header
        f.write(",".join(f'"{h}"' for h in headers) + "\n")
        
        # Write rows
        for rec in records:
            row = []
            for header in headers:
                val = rec.get(header, "")
                flattened = flatten_list(val)
                escaped = flattened.replace('"', '""')
                row.append(f'"{escaped}"')
            f.write(",".join(row) + "\n")
    
    print(f"Saved {len(records)} records to CSV: {path}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Deduplicate JSONL records and export canonical/duplicate sets."
    )
    parser.add_argument("input", help="Input JSONL file path")
    parser.add_argument("--out", default="canonical.jsonl", help="Output canonical JSONL (default: canonical.jsonl)")
    parser.add_argument("--dups", default="duplicates.jsonl", help="Output duplicates JSONL (default: duplicates.jsonl)")
    parser.add_argument("--csv", help="Optional output CSV path for canonical records (flattens lists)")
    parser.add_argument("--stats", action="store_true", help="Print deduplication statistics")
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    out_path = Path(args.out)
    dups_path = Path(args.dups)
    csv_path = Path(args.csv) if args.csv else None
    
    # Load and dedupe
    records = load_jsonl(input_path)
    canonical, dups = dedupe_records(records)
    
    # Save
    save_jsonl(canonical, out_path)
    if dups:
        save_jsonl(dups, dups_path)
    if csv_path:
        save_csv(canonical, csv_path)
    
    # Print stats
    if args.stats or True:  # Always print stats for clarity
        print("\n=== Deduplication Statistics ===", file=sys.stderr)
        print(f"Input records: {len(records)}", file=sys.stderr)
        print(f"Canonical records: {len(canonical)}", file=sys.stderr)
        print(f"Duplicates found: {len(dups)}", file=sys.stderr)
        if len(records) > 0:
            dup_pct = 100 * len(dups) / len(records)
            print(f"Duplicate rate: {dup_pct:.1f}%", file=sys.stderr)
        print(file=sys.stderr)


if __name__ == "__main__":
    main()
