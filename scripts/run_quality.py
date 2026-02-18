#!/usr/bin/env python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.quality import run_quality_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Cognitra automated QC logging and Excel reporting."
    )
    parser.add_argument(
        "--latest-brief",
        action="store_true",
        help="Use latest brief in data/briefs (default behavior).",
    )
    parser.add_argument(
        "--brief-id",
        type=str,
        help="Use a specific brief id or path (e.g., brief_YYYYMMDD_HHMMSS).",
    )
    args = parser.parse_args()

    use_latest = True
    if args.brief_id:
        use_latest = False
    elif args.latest_brief:
        use_latest = True

    result = run_quality_pipeline(
        brief_id=args.brief_id,
        use_latest_brief=use_latest,
    )

    record_high = int((result.get("record_counts") or {}).get("High", 0))
    brief_high = int((result.get("brief_counts") or {}).get("High", 0))
    high_total = record_high + brief_high

    print(f"Run: {result.get('run_id')}")
    print(f"Brief: {result.get('brief_id') or '(none)'}")
    print(f"Week range: {result.get('week_range')}")
    print(f"Target records: {result.get('target_record_count')}")
    print(f"High issues: {high_total} (record={record_high}, brief={brief_high})")
    print(f"Record score: {result.get('weighted_record_score')}")
    print(f"Brief score: {result.get('weighted_brief_score')}")
    top_issues = result.get("top_issue_types") or []
    print(f"Top issue types: {', '.join(top_issues[:3]) if top_issues else '(none)'}")

    # --- Trend alerts ---
    trend_result = result.get("trends") or {}
    regression_alerts = trend_result.get("regression_alerts") or []
    prior_count = trend_result.get("prior_run_count", 0)
    if prior_count > 0:
        print(f"\n--- KPI Trends (vs last {prior_count} runs) ---")
        trends = trend_result.get("trends") or {}
        for kpi, info in trends.items():
            direction = info.get("direction", "stable")
            if direction != "stable":
                print(f"  {kpi}: {info.get('direction')} ({info.get('avg_prior'):.4g} -> {info.get('current'):.4g}, delta={info.get('delta_from_avg'):+.4g})")
        if regression_alerts:
            print("\n  REGRESSION ALERTS:")
            for alert in regression_alerts:
                print(f"    ! {alert}")
        elif trends:
            print("  No regressions detected.")
    else:
        print("\nNo prior runs for trend comparison.")

    # --- Feedback suggestions ---
    feedback = result.get("feedback") or {}
    chronic = feedback.get("chronic_issues") or []
    suggestions = feedback.get("prompt_suggestions") or []
    if chronic:
        print(f"\n--- Chronic Issues ({feedback.get('runs_analyzed', 0)} runs analyzed) ---")
        for issue in chronic[:5]:
            print(f"  {issue['type']}: {issue['frequency']}")
    if suggestions:
        print("\n--- Prompt/Config Suggestions ---")
        for i, s in enumerate(suggestions[:5], 1):
            print(f"  {i}. {s}")

    print(f"\nExcel report: {result.get('report_path')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
