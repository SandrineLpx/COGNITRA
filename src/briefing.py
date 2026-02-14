from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.dedupe import score_source_quality
from src.dedup_rank import dedup_and_rank
from src.constants import CANON_TOPICS, FOOTPRINT_REGIONS


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception:
        return None


def _parse_iso_datetime(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except Exception:
        return None


def record_date(rec: Dict) -> Optional[date]:
    pd = _parse_date(rec.get("publish_date"))
    if pd:
        return pd
    return _parse_iso_datetime(rec.get("created_at"))


def within_last_days(rec: Dict, days: int) -> bool:
    rd = record_date(rec)
    if not rd:
        return False
    cutoff = date.today() - timedelta(days=days)
    return rd >= cutoff


def is_share_ready(rec: Dict) -> bool:
    return rec.get("priority") == "High" and rec.get("confidence") == "High"


def select_weekly_candidates(
    records: List[Dict],
    days: int = 7,
    include_excluded: bool = False,
) -> List[Dict]:
    kept, excluded = dedup_and_rank(records)
    merged = kept + excluded
    items = []
    for r in merged:
        if str(r.get("review_status") or "") == "Disapproved":
            continue
        if not include_excluded and r.get("exclude_from_brief"):
            continue
        if within_last_days(r, days):
            items.append(r)
    items.sort(key=lambda r: (is_share_ready(r), score_source_quality(r)), reverse=True)
    return items


def render_weekly_brief_md(records: List[Dict], week_range: str) -> str:
    if not records:
        return "No items selected for this week."

    share_ready = [r for r in records if is_share_ready(r)]
    other = [r for r in records if not is_share_ready(r)]

    lines: List[str] = []
    lines.append("WEEKLY INTELLIGENCE BRIEF\n")
    lines.append(f"Week: {week_range}\n\n")

    if share_ready:
        lines.append("High-Importance (Share-Ready)\n")
        for r in share_ready:
            title = r.get("title", "Untitled")
            insight = (r.get("key_insights") or [""])[0]
            lines.append(f"- {title} :: {insight}\n")
        lines.append("\n")

    if other:
        lines.append("Other Notable Items\n")
        for r in other:
            title = r.get("title", "Untitled")
            insight = (r.get("key_insights") or [""])[0]
            lines.append(f"- {title} :: {insight}\n")
        lines.append("\n")

    lines.append("Selection Notes\n")
    lines.append("- Duplicates are suppressed when a better source is available.\n")
    return "".join(lines)


def render_exec_email(records: List[Dict], week_range: str) -> Tuple[str, str]:
    if not records:
        subject = f"Weekly Intelligence Brief ({week_range})"
        body = "No items selected for this week."
        return subject, body

    share_ready = [r for r in records if is_share_ready(r)]
    other = [r for r in records if not is_share_ready(r)]

    subject = f"Weekly Intelligence Brief ({week_range})"
    lines: List[str] = []
    lines.append("Hello team,\n\n")
    if share_ready:
        lines.append("High-importance items (share-ready):\n")
        for r in share_ready:
            title = r.get("title", "Untitled")
            insight = (r.get("key_insights") or [""])[0]
            lines.append(f"- {title} — {insight}\n")
        lines.append("\n")

    if other:
        lines.append("Other notable items:\n")
        for r in other:
            title = r.get("title", "Untitled")
            insight = (r.get("key_insights") or [""])[0]
            lines.append(f"- {title} — {insight}\n")
        lines.append("\n")

    lines.append("Regards,\n")
    lines.append("[Your Name]\n")

    return subject, "".join(lines)


# ---------------------------------------------------------------------------
# LLM-synthesized weekly executive brief
# ---------------------------------------------------------------------------

_STRIP_FIELDS = {
    "_router_log", "source_pdf_path", "record_id", "created_at",
    "review_status", "notes", "story_primary", "duplicate_story_of",
    "exclude_from_brief",
}

_MAX_RECORDS_FOR_SYNTHESIS = 20


def _slim_record(rec: Dict) -> Dict:
    """Return a copy with internal/noisy fields removed to save tokens."""
    return {k: v for k, v in rec.items() if k not in _STRIP_FIELDS}


def _build_synthesis_prompt(records: List[Dict], week_range: str) -> str:
    topic_list = "\n".join(f"  - {t}" for t in CANON_TOPICS)
    region_list = "\n".join(f"  - {r}" for r in FOOTPRINT_REGIONS)
    slim = [_slim_record(r) for r in records]
    records_json = json.dumps(slim, indent=1, default=str)

    return (
        "You are drafting a weekly automotive competitive intelligence brief "
        "focused on closure systems and car entry (door modules, window regulators, "
        "latches, smart entry, cinching, handles, access technologies).\n\n"
        f"Period: {week_range}\n\n"
        "Input: a list of approved JSON records (already extracted from sources). "
        "Do not introduce any new facts beyond the records.\n\n"
        "Write the brief using EXACTLY this structure:\n\n"
        "AUTOMOTIVE COMPETITIVE INTELLIGENCE BRIEF\n"
        f"Period: {week_range}\n"
        "Prepared by: Cognitra AI\n\n"
        "============================================================\n\n"
        "EXECUTIVE SUMMARY\n"
        "[2-3 sentences highlighting the most significant developments and why they matter.]\n\n"
        "HIGH PRIORITY DEVELOPMENTS\n"
        "[3-6 bullets max; each bullet should mention company/OEM + what happened + why it matters.]\n\n"
        "FOOTPRINT REGION SIGNALS\n"
        "[For each of the 7 footprint regions below, include 1-3 bullets if the region appears "
        "in the records. If a region has no signal this period, write 'No significant signals this period.' "
        "Regions:\n"
        f"{region_list}\n"
        "]\n\n"
        "KEY DEVELOPMENTS BY TOPIC\n"
        "[Include only topics present this period. Use these canonical topic labels exactly:\n"
        f"{topic_list}\n"
        "For each topic with content, write 1-3 bullets.]\n\n"
        "EMERGING TRENDS\n"
        "[1-3 bullets. Trends should be based on multiple items or clear signal strength.]\n\n"
        "RECOMMENDED ACTIONS\n"
        "[3-6 bullets; who should do what next.]\n\n"
        "APPENDIX\n"
        f"Items Covered: {len(records)}\n"
        "Method: Structured extraction from source documents; human review and approval; "
        "LLM synthesis by Cognitra.\n\n"
        "Rules:\n"
        "- Reference sources briefly by source_type and title (no URLs required).\n"
        "- Keep it short and executive-friendly.\n"
        "- If evidence is weak, state uncertainty and lower emphasis.\n"
        "- Do not invent facts. Only use information from the provided records.\n"
        "- No emojis.\n\n"
        "APPROVED RECORDS (JSON list):\n"
        + records_json
    )


def synthesize_weekly_brief_llm(
    records: List[Dict],
    week_range: str,
) -> Tuple[str, Dict[str, Any]]:
    """Generate an LLM-synthesized weekly executive brief from approved records.

    Returns (brief_text, usage_dict).
    """
    from src.model_router import _call_gemini_text

    if not records:
        return "No records provided for synthesis.", {}

    # Cap to top records by priority+confidence to stay within context limits.
    if len(records) > _MAX_RECORDS_FOR_SYNTHESIS:
        prio_rank = {"High": 3, "Medium": 2, "Low": 1}
        records = sorted(
            records,
            key=lambda r: (
                prio_rank.get(r.get("priority", ""), 0),
                prio_rank.get(r.get("confidence", ""), 0),
            ),
            reverse=True,
        )[:_MAX_RECORDS_FOR_SYNTHESIS]

    prompt = _build_synthesis_prompt(records, week_range)
    model = os.getenv("GEMINI_MODEL_STRONG", "gemini-2.5-flash")
    brief_text, usage = _call_gemini_text(prompt, model=model)
    return brief_text, usage
