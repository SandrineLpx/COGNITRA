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
        "You are a competitive intelligence analyst for Kiekert, a global automotive "
        "closure systems supplier (door latches, strikers, handles, smart entry, cinch "
        "systems, window regulators). Draft a weekly executive brief.\n\n"
        f"Period: {week_range}\n"
        f"Records provided: {len(records)}\n\n"
        "═══════════════════════════════════════════════════════════════\n"
        "SYNTHESIS PROCEDURE (follow in order, do not skip)\n"
        "═══════════════════════════════════════════════════════════════\n"
        "1. CLUSTER: group records by theme (not one-record-per-bullet).\n"
        "2. VALIDATE: for every claim, confirm it appears in at least one record's "
        "evidence_bullets or key_insights. Cite the record_id inline as (REC:<id>). "
        "If a claim draws from multiple records, cite all.\n"
        "3. NUMBERS: reproduce figures exactly as they appear in evidence_bullets. "
        "Do not round, extrapolate, or invent numbers. If two records conflict on a "
        "figure, flag it in CONFLICTS & UNCERTAINTY.\n"
        "4. WRITE: produce the brief in the structure below.\n\n"
        "═══════════════════════════════════════════════════════════════\n"
        "OUTPUT STRUCTURE (use these exact headings)\n"
        "═══════════════════════════════════════════════════════════════\n\n"
        "AUTOMOTIVE COMPETITIVE INTELLIGENCE BRIEF\n"
        f"Period: {week_range}\n"
        "Prepared by: Cognitra AI\n\n"
        "EXECUTIVE SUMMARY\n"
        "- 4-6 bullets maximum. Each bullet synthesizes a cross-record theme, not a "
        "single article. Interpret through the Kiekert lens:\n"
        "  * Closure systems demand / technology shifts\n"
        "  * OEM program timing and platform decisions\n"
        "  * Footprint / sourcing risk (China, US, Mexico, Europe tariffs)\n"
        "  * Pricing pressure and supplier margin impact\n"
        "  * Supply chain disruptions affecting door-module BOM\n"
        "- End each bullet with (REC:<id>, REC:<id>).\n\n"
        "HIGH PRIORITY DEVELOPMENTS\n"
        "- 3-6 bullets. Each: Company/OEM + what happened + why it matters to Kiekert.\n"
        "- Only include items where priority=High in the records.\n"
        "- Cite (REC:<id>).\n\n"
        "FOOTPRINT REGION SIGNALS\n"
        "For each region below, write 1-3 bullets if the region appears in the records. "
        "If a region has no signal, write 'No significant signals this period.'\n"
        f"{region_list}\n\n"
        "KEY DEVELOPMENTS BY TOPIC\n"
        "Use these canonical topic labels exactly (include only topics with records):\n"
        f"{topic_list}\n"
        "For each topic, 1-3 bullets synthesizing across records. Cite (REC:<id>).\n\n"
        "EMERGING TRENDS\n"
        "- 1-3 bullets. Each trend MUST reference >=2 distinct records.\n"
        "- If fewer than 2 records support a trend, do not include it.\n\n"
        "CONFLICTS & UNCERTAINTY\n"
        "- Flag any contradictory figures, dates, or claims between records.\n"
        "- Flag any claim where confidence=Low or evidence is single-sourced.\n"
        "- If none, write: 'None observed this period.'\n\n"
        "RECOMMENDED ACTIONS\n"
        "- 3-6 bullets. Each must specify:\n"
        "  * Owner role (e.g., VP Sales, Engineering, Procurement, Strategy)\n"
        "  * Concrete action\n"
        "  * Time horizon (immediate / this quarter / next 6 months)\n"
        "- Ground each in a specific development above.\n\n"
        "APPENDIX\n"
        f"Items Covered: {len(records)}\n"
        "Method: Structured extraction from source documents; human review and "
        "approval; LLM synthesis by Cognitra.\n\n"
        "═══════════════════════════════════════════════════════════════\n"
        "RULES (hard constraints)\n"
        "═══════════════════════════════════════════════════════════════\n"
        "- GROUNDING: every factual claim must cite at least one (REC:<record_id>). "
        "Uncited claims will be rejected.\n"
        "- NO INVENTION: use only facts from the provided records. If a record lacks "
        "detail, say so rather than filling gaps.\n"
        "- NO FLUFF: avoid vague phrases ('dynamic environment', 'strategic pivot', "
        "'rapidly evolving landscape'). Be specific or omit.\n"
        "- CROSS-SYNTHESIS: do not summarize records one by one. Group by theme. "
        "A bullet that restates a single record without connecting it to others is "
        "acceptable only if the event is uniquely significant.\n"
        "- NUMERIC FIDELITY: reproduce numbers exactly. '$4.2B' stays '$4.2B', "
        "not 'approximately $4 billion'.\n"
        "- No emojis. Executive tone.\n\n"
        "APPROVED RECORDS (JSON list):\n"
        + records_json
    )


def synthesize_weekly_brief_llm(
    records: List[Dict],
    week_range: str,
    provider: str = "gemini",
    web_check: bool = False,
    model_override: Optional[str] = None,
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
    if provider == "gemini":
        model = model_override or os.getenv("GEMINI_MODEL_STRONG", "gemini-2.5-flash")
        if web_check:
            prompt += (
                "\n\nCOHERENCE CHECK:\n"
                "- Verify major claims against current public web sources.\n"
                "- If a claim cannot be corroborated, mark it as unverified.\n"
                "- Keep output in the same report structure.\n"
            )
        brief_text, usage = _call_gemini_text(prompt, model=model, use_google_search=web_check)
        usage["provider"] = "gemini"
        return brief_text, usage

    if provider == "claude":
        raise RuntimeError("Claude weekly synthesis is not wired yet. Add SDK/API integration and ANTHROPIC_API_KEY.")
    if provider == "chatgpt":
        raise RuntimeError("ChatGPT weekly synthesis is not wired yet. Add SDK/API integration and OPENAI_API_KEY.")
    raise RuntimeError(f"Unsupported provider for weekly synthesis: {provider}")
