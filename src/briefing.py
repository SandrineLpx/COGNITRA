from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.dedupe import dedup_and_rank, score_source_quality
from src.constants import (
    CANON_TOPICS,
    FOOTPRINT_REGIONS,
    UNCERTAINTY_TOPICS,
    UNCERTAINTY_WORDS,
)


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
        if not include_excluded and r.get("is_duplicate"):
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
    "_router_log", "source_pdf_path", "created_at",
    "review_status", "notes", "story_primary", "duplicate_story_of",
    "is_duplicate",
}

_MAX_RECORDS_FOR_SYNTHESIS = 20

_UNCERTAINTY_WORDS = re.compile(UNCERTAINTY_WORDS, re.IGNORECASE)


def _has_uncertainty_signals(records: List[Dict]) -> bool:
    """Return True when records contain signals that warrant a mandatory
    CONFLICTS & UNCERTAINTY section (at least one item required)."""
    for rec in records:
        # Condition 1: confidence is Medium or Low
        if rec.get("confidence") in ("Medium", "Low"):
            return True
        # Condition 2: topics include strategy/guidance change
        topics = rec.get("topics") or []
        if any(t in UNCERTAINTY_TOPICS for t in topics):
            return True
        # Condition 3: uncertainty language in evidence or insights
        text_fields = (
            (rec.get("evidence_bullets") or [])
            + (rec.get("key_insights") or [])
        )
        for txt in text_fields:
            if _UNCERTAINTY_WORDS.search(txt):
                return True
    return False


def _slim_record(rec: Dict) -> Dict:
    """Return a copy with internal/noisy fields removed to save tokens."""
    return {k: v for k, v in rec.items() if k not in _STRIP_FIELDS}


def _choose_brief_mode(n: int) -> Dict[str, Any]:
    if n <= 1:
        return {
            "name": "single",
            "max_words": "350-450",
            "exec_bullets": "2",
            "priority_bullets": "1",
            "actions_bullets": "2",
            "allow_trends": False,
            "include_empty_regions": False,
        }
    if n <= 4:
        return {
            "name": "compact",
            "max_words": "600-850",
            "exec_bullets": "3",
            "priority_bullets": "3",
            "actions_bullets": "3",
            "allow_trends": True,
            "include_empty_regions": False,
        }
    return {
        "name": "standard",
        "max_words": "900-1300",
        "exec_bullets": "4-5",
        "priority_bullets": "3-6",
        "actions_bullets": "3-6",
        "allow_trends": True,
        "include_empty_regions": True,
    }


def build_prompt(records, week_range, record_ids_text, records_json, mode, intro, region_list, output_mode="operational"):
    """
    output_mode: "executive" | "operational"

    EXECUTIVE version:
      - Executive Summary (implications only, 3 bullets max)
      - High Priority Developments (facts + inline uncertainty caveat + Supplier Implications)
      - No Footprint, no Trends, no standalone Conflicts, no Actions

    OPERATIONAL version:
      - Full brief (all sections)
      - Intended for VP Sales, Engineering, Procurement, Strategy
    """
    is_single = len(records) == 1
    is_executive = output_mode == "executive"
    title_heading = (
        "AUTOMOTIVE COMPETITIVE INTELLIGENCE BRIEF — EXECUTIVE VERSION"
        if is_executive
        else "AUTOMOTIVE COMPETITIVE INTELLIGENCE BRIEF"
    )
    # ── SHARED: EXECUTIVE SUMMARY ────────────────────────────────────────────
    exec_section = (
        "SECTION JOB: State Apex Mobility strategic implications only. "
        "Do NOT restate OEM event descriptions — the reader gets those from High Priority Developments. "
        "Lead every bullet with the business consequence for Apex Mobility, not the triggering event.\n"
        "- Exactly 2 bullets. Each bullet: maximum 3 sentences structured as:\n"
        "  * Sentence 1: the Apex Mobility implication (name the specific risk or opportunity).\n"
        "  * Sentence 2: supporting evidence — you MAY name the OEM, but frame it as evidence "
        "for the implication, not as a description of what the OEM did.\n"
        "    CORRECT: 'Apex Mobility faces pricing pressure on Stellantis ICE programs given the "
        "OEM's 25% U.S. retail growth target built on Ram 1500 Hemi volume.'\n"
        "    WRONG: 'Stellantis is targeting 25% retail sales growth with its Ram 1500.'\n"
        "  * Sentence 3 (optional): Tier-1 so-what — only include if it adds information not "
        "already implied by sentences 1-2.\n"
        "- Each bullet must name one Tier-1 implication category: pricing pressure, volume volatility, "
        "premium content risk/opportunity, regional sourcing shift, or technology value migration.\n"
        "- If numeric financial deltas exist in the records (margin %, profit change, sales %, "
        "deliveries %, mix %, pricing), include at least one exact figure.\n"
        "- End each bullet with (REC:<id>).\n\n"
        if is_single
        else (
            "SECTION JOB: State Apex Mobility strategic implications only. "
            "Do NOT restate OEM event descriptions — the reader gets those from High Priority Developments. "
            "Lead every bullet with the business consequence for Apex Mobility, not the triggering event.\n"
            f"- {mode['exec_bullets']} bullets maximum. Each bullet synthesizes a cross-record theme "
            "through the Apex Mobility lens:\n"
            "  * Closure systems demand / technology shifts\n"
            "  * OEM program timing and platform decisions\n"
            "  * Footprint / sourcing risk (China, US, Mexico, Europe tariffs)\n"
            "  * Pricing pressure and supplier margin impact\n"
            "  * Supply chain disruptions affecting door-module BOM\n"
            "- Each bullet: maximum 3 sentences structured as:\n"
            "  * Sentence 1: the Apex Mobility implication (lead with consequence, not event).\n"
            "  * Sentence 2: supporting evidence — you MAY name the OEM, but frame it as evidence "
            "for the implication, not as a description of what the OEM did.\n"
            "    CORRECT: 'Apex Mobility faces pricing pressure on Stellantis ICE programs given the "
            "OEM's 25% U.S. retail growth target built on Ram 1500 Hemi volume.'\n"
            "    WRONG: 'Stellantis is targeting 25% retail sales growth with its Ram 1500.'\n"
            "  * Sentence 3 (optional): Tier-1 so-what — only if it adds new information.\n"
            "- If numeric financial deltas exist in the records (margin %, profit change, sales %, "
            "deliveries %, mix %, pricing), include at least one exact figure.\n"
            "- End each bullet with (REC:<id>, REC:<id>).\n\n"
        )
    )
    # ── SHARED: HIGH PRIORITY DEVELOPMENTS ──────────────────────────────────
    # Executive version: adds inline uncertainty caveat per item instead of a separate section
    uncertainty_caveat_instruction = (
        "  Uncertainty Caveat (REQUIRED per item for executive version): after the Supplier "
        "Implications line, add one sentence flagging any forward-looking projection, "
        "single-sourced claim, or unconfirmed commitment in this item. "
        "If there is none, state: 'No material uncertainty identified for this item.'\n"
        "  Format: Uncertainty: [1 sentence, cite (REC:<id>)]\n"
        if is_executive
        else ""
    )
    priority_item_format = (
        "  Format each item as:\n"
        "  * [OEM/Company] — [What happened, 1-2 sentences, include exact numbers if available]. (REC:<id>)\n"
        "    Supplier Implications: [1 sentence: what this means specifically for Apex Mobility — "
        "closure systems volume, pricing, program timing, footprint, or technology content.]\n"
        + uncertainty_caveat_instruction
        + "  NOTE: All Apex Mobility supplier implications belong ONLY in the 'Supplier Implications' "
        "sub-field. Do NOT repeat supplier implications in the Executive Summary.\n"
        "  Medium-priority records: include only as a sub-bullet under the most relevant High Priority "
        "item if they add unique detail. Do not create standalone bullets for medium-priority items.\n"
    )
    priority_instruction = (
        "- Exactly 1 item. OEM/Company + what happened + exact figures if available.\n"
        + priority_item_format
        + "- Only include items where priority=High in the records.\n"
        + "- Cite (REC:<id>).\n\n"
        if mode["priority_bullets"] == "1"
        else (
            f"- Up to {mode['priority_bullets']} items. Each: OEM/Company + what happened + exact figures if available.\n"
            + priority_item_format
            + "- Only include items where priority=High in the records.\n"
            + "- Medium-priority records: surface only as sub-bullets under the most relevant High "
            "Priority item, or in Emerging Trends (operational version only) if they contribute "
            "to a cross-theme synthesis. Do not create standalone High Priority bullets for "
            "medium-priority records.\n"
            + "- Cite (REC:<id>).\n\n"
        )
    )
    # ── OPERATIONAL ONLY: FOOTPRINT REGION SIGNALS ───────────────────────────
    region_section = (
        ""
        if is_executive
        else (
            "FOOTPRINT REGION SIGNALS\n"
            "SECTION JOB: Regional specifics that are NOT already the main point of a High Priority item.\n"
            "Include ONLY regions from the allowed list below, and only if they have explicit evidence.\n"
            "QUALITY FLOOR: a valid region signal must state (1) what happened, (2) which specific "
            "facility, city, or market, and (3) why it matters for Apex Mobility closure systems. "
            "A region name + company name alone is NOT a valid signal and must be omitted entirely.\n"
            "Example INVALID: 'India: Renault Group's regions relevant to Apex Mobility include India.'\n"
            "Example VALID: 'Germany (Dingolfing): BMW deployed EUR 10M deflectometry inspection on "
            "unpainted bodies — sets a new quality benchmark likely to cascade into Tier-1 audits.'\n"
            "- Do NOT add empty-region placeholder lines.\n"
            "- Do NOT mix parent buckets and child regions (e.g., not both Europe and Germany).\n"
            "- Prefer the most specific allowed region labels.\n"
            "- If a Footprint bullet restates the same fact already in a High Priority item body, "
            "omit it — it is redundant.\n"
            f"{region_list}\n\n"
        )
    )
    # ── OPERATIONAL ONLY: EMERGING TRENDS ────────────────────────────────────
    trends_section = (
        ""
        if is_executive or not mode["allow_trends"]
        else (
            "EMERGING TRENDS\n"
            "SECTION JOB: Forward-looking synthesis only — what might happen next quarter or beyond, "
            "not what already happened. Do NOT re-describe events already covered in High Priority Developments.\n"
            "- 1-3 bullets. Each trend MUST reference >=2 distinct records.\n"
            "- SPECIFICITY TEST: each bullet must include at least one named OEM, named model/platform, "
            "named region, or named metric. A bullet containing no proper noun is too generic — rewrite or omit.\n"
            "- Each bullet must use future-oriented language: 'may accelerate', 'is likely to', "
            "'could shift', 'appears poised to', 'suggests an emerging risk of'.\n"
            "- Frame as a question when genuine uncertainty exists (e.g., 'Will X lead to Y?').\n"
            "- No past-tense restatement of record facts. If you find yourself writing '[OEM] did X', "
            "you are restating High Priority — reframe as '[OEM]'s X decision may lead to Y for Apex Mobility'.\n"
            "- Do NOT include Apex Mobility supplier implications here; those belong in High Priority sub-fields.\n\n"
        )
    )
    # ── OPERATIONAL ONLY: CONFLICTS & UNCERTAINTY (standalone section) ────────
    # Executive version surfaces uncertainty inline per High Priority item instead
    if _has_uncertainty_signals(records):
        uncertainty_extra = (
            "Uncertainty signals detected in the input records (confidence=Medium/Low or forecast language present). "
        )
    else:
        uncertainty_extra = ""
    uncertainty_section = (
        ""
        if is_executive
        else (
            "CONFLICTS & UNCERTAINTY (REQUIRED — at least 1 item every brief)\n"
            + uncertainty_extra
            + "You MUST include at least one item. Choose from:\n"
            "- Contradictory figures, dates, or claims between records.\n"
            "- Any claim where confidence=Low or confidence=Medium, or evidence is single-sourced.\n"
            "- Claims containing forecast language (forecast, could, weighing, sources said, expected) "
            "— note the uncertainty and cite (REC:<id>).\n"
            "- Strategy-shift or guidance-change topics that lack concrete commitments.\n"
            "- If no hard contradictions exist, surface an unconfirmed forward-looking claim or a "
            "strategic signal that lacks a concrete commitment from the records.\n"
            "BANNED OUTPUT: 'None observed this period.' is never an acceptable answer for this section.\n\n"
        )
    )
    # ── OPERATIONAL ONLY: RECOMMENDED ACTIONS ────────────────────────────────
    actions_section = (
        ""
        if is_executive
        else (
            "RECOMMENDED ACTIONS\n"
            + (
                "- Exactly 2 bullets. Each must include: Owner + Action + Time horizon + Trigger + Deliverable.\n"
                "- QUALITY CHECK: if a Recommended Action could have been written without reading the records "
                "(no named OEM, no specific figure, no concrete trigger threshold), it is too generic — rewrite it.\n"
                "- Keep actions concise and grounded with (REC:<id>).\n\n"
                if is_single
                else (
                    f"- {mode['actions_bullets']} bullets. Each must specify:\n"
                    "  * Owner role (e.g., VP Sales, Engineering, Procurement, Strategy)\n"
                    "  * Concrete action grounded in a specific development above\n"
                    "  * Time horizon (immediate / this quarter / next 6 months)\n"
                    "  * Trigger/watch condition (if/when threshold — must name a specific metric or event)\n"
                    "  * Deliverable artifact (forecast update, risk memo, playbook, dashboard)\n"
                    "- QUALITY CHECK: if a Recommended Action could have been written without reading the records "
                    "(no named OEM, no specific figure, no concrete trigger threshold), it is too generic — rewrite it.\n"
                    "- Ground each in a specific development above.\n\n"
                )
            )
        )
    )
    # ── SYNTHESIS PROCEDURE ──────────────────────────────────────────────────
    self_review_checks = (
        # Executive version: fewer checks, inline uncertainty instead of standalone section
        "   CHECK A — Exec Summary framing: if the same OEM name + event appears in both "
        "EXECUTIVE SUMMARY and HIGH PRIORITY, remove it from EXECUTIVE SUMMARY (keep only "
        "the Apex Mobility implication).\n"
        "   CHECK B — Uncertainty caveats: every High Priority item must have an 'Uncertainty:' "
        "line. If any item is missing one, add it before outputting.\n"
        "   CHECK C — Actions genericism: executive version has no Actions section — if you "
        "have written one, remove it.\n"
        if is_executive
        else
        # Operational version: full five checks
        "   CHECK A — Cross-section repetition: if the same OEM name + event appears in both "
        "EXECUTIVE SUMMARY and HIGH PRIORITY, remove it from EXECUTIVE SUMMARY (keep only the "
        "Apex Mobility implication).\n"
        "   CHECK B — Trends restatement: if a trend bullet could pass as a High Priority past-tense "
        "fact, reframe it as a forward projection or remove it.\n"
        "   CHECK C — Footprint quality: every Footprint bullet must pass the three-part test "
        "(what happened + where specifically + why it matters for Apex Mobility). Remove any that fail.\n"
        "   CHECK D — Actions genericism: if a Recommended Action contains no named OEM, no specific "
        "figure, and no concrete trigger threshold, rewrite it.\n"
        "   CHECK E — Conflicts section: if CONFLICTS & UNCERTAINTY is empty or says 'None observed', "
        "you have failed — add at least one item before outputting.\n"
    )
    output_structure = (
        # Executive structure
        f"{title_heading}\n"
        f"Period: {week_range}\n"
        "Prepared by: Cognitra AI\n\n"
        "EXECUTIVE SUMMARY\n"
        + exec_section
        + "HIGH PRIORITY DEVELOPMENTS\n"
        + priority_instruction
        + "APPENDIX\n"
        + f"Items Covered: {len(records)}\n"
        + "Method: Structured extraction from source documents; human review and approval; LLM synthesis by Cognitra.\n"
        if is_executive
        else
        # Operational structure
        f"{title_heading}\n"
        f"Period: {week_range}\n"
        "Prepared by: Cognitra AI\n\n"
        "EXECUTIVE SUMMARY\n"
        + exec_section
        + "HIGH PRIORITY DEVELOPMENTS\n"
        + priority_instruction
        + region_section
        + trends_section
        + uncertainty_section
        + actions_section
        + "APPENDIX\n"
        + f"Items Covered: {len(records)}\n"
        + "Method: Structured extraction from source documents; human review and approval; LLM synthesis by Cognitra.\n"
    )
    # ── HARD CONSTRAINTS (shared, with mode-specific additions) ──────────────
    executive_extra_constraints = (
        "- EXECUTIVE FORMAT: output contains ONLY Executive Summary and High Priority Developments. "
        "Do not add Footprint, Trends, Conflicts, or Actions sections.\n"
        "- UNCERTAINTY INLINE: every High Priority item must include an 'Uncertainty:' caveat line. "
        "This replaces the standalone Conflicts & Uncertainty section.\n"
        if is_executive
        else
        "- FOOTPRINT QUALITY FLOOR: region entries must pass the three-part test (what + where + "
        "why for Apex Mobility). See step 9 CHECK C.\n"
        "- TRENDS SPECIFICITY: every Emerging Trend bullet must contain at least one proper noun "
        "(OEM name, model, region, or metric). Generic bullets without proper nouns are invalid.\n"
        "- MEDIUM RECORD ROUTING: priority=Medium records may not appear as standalone High Priority items. See step 8.\n"
        "- CONFLICTS REQUIRED: CONFLICTS & UNCERTAINTY must contain at least one item. "
        "'None observed this period.' is never acceptable.\n"
    )
    return (
        "You are a competitive intelligence analyst for Apex Mobility, a global automotive "
        "closure systems supplier (door latches, strikers, handles, smart entry, cinch "
        f"systems, window regulators). {intro}\n\n"
        f"Output mode: {output_mode.upper()}\n"
        f"Period: {week_range}\n"
        f"Records provided: {len(records)}\n"
        f"Target length: {mode['max_words']} words.\n\n"
        "SYNTHESIS PROCEDURE (follow in order, do not skip)\n"
        f"0. VALID IDS: use only these record IDs in REC citations: {record_ids_text}\n"
        "1. CLUSTER: group records by theme (not one-record-per-bullet).\n"
        "2. VALIDATE: for every claim, confirm it appears in at least one record's "
        "evidence_bullets or key_insights. Cite the record_id inline as (REC:<id>). "
        "If a claim draws from multiple records, cite all.\n"
        "3. NUMBERS: reproduce figures exactly as they appear in evidence_bullets. "
        "Do not round, extrapolate, or invent numbers. If two records conflict on a "
        "figure, flag it in CONFLICTS & UNCERTAINTY (operational) or in the item's "
        "Uncertainty caveat (executive).\n"
        "4. INFERENCE FIREWALL: a claim is acceptable only if it is (a) directly stated "
        "in a record, or (b) a single logical step from a stated fact, expressed with hedged "
        "language ('may', 'could', 'appears to'). Two-step inferences "
        "('X happened → Y will follow → therefore Z') must be flagged as speculation, "
        "not stated as analysis.\n"
        "5. TONE: use analytical executive language. Avoid dramatic wording such as "
        "'financial distress', 'collapse', 'crisis', 'catastrophic'. Prefer "
        "'margin compression', 'profitability deterioration', 'strategic pressure', 'competitive intensity'.\n"
        "6. ROLLUP FRAMING: if records include _macro_theme_rollups with 'Premium OEM Financial/Strategy Stress' "
        "or 'China Tech-Driven Premium Disruption', elevate that framing implicitly in the Executive Summary. "
        "Do not print rollup labels explicitly unless >3 records support the same rollup.\n"
        "7. SECTION DISCIPLINE: each section has a distinct, non-overlapping job.\n"
        "   - OEM event facts → HIGH PRIORITY DEVELOPMENTS body\n"
        "   - Apex Mobility supplier implications → 'Supplier Implications' sub-field only\n"
        "   - Uncertainty / forecast caveats → 'Uncertainty:' line per item (executive) "
        "or CONFLICTS & UNCERTAINTY section (operational)\n"
        "   - Strategic outlook for Apex Mobility → EXECUTIVE SUMMARY\n"
        "   - Forward projections → EMERGING TRENDS (operational only)\n"
        "   - Regional specifics → FOOTPRINT REGION SIGNALS (operational only, if not already in High Priority body)\n"
        "8. ROUTE MEDIUM-PRIORITY RECORDS: priority=Medium records may only appear as "
        "sub-bullets under a High Priority item or as supporting evidence in Emerging Trends "
        "(operational). Do not create standalone High Priority bullets for medium-priority records.\n"
        "9. SELF-REVIEW: before outputting, run all checks below. Fix any failures before writing output:\n"
        + self_review_checks
        + "10. WRITE: produce the brief in the output structure below.\n\n"
        "LENGTH SCALING (internal, do not print):\n"
        "- If 1 record: Executive Summary max 2 bullets; High Priority max 1; Recommended Actions max 2.\n"
        "- If 2-4 records: Executive Summary max 3 bullets; High Priority max 3.\n"
        "- If 5+ records: Executive Summary 4-5 bullets and include theme clustering.\n\n"
        "OUTPUT STRUCTURE\n\n"
        + output_structure
        + "\nHARD CONSTRAINTS\n"
        + f"- VALID REC IDs ONLY: citations must use one of [{record_ids_text}]. Do not use REC:1, REC:2, etc.\n"
        + "- GROUNDING: every factual claim must cite at least one (REC:<record_id>). See step 2.\n"
        + "- NO INVENTION: use only facts from the provided records. If a record lacks detail, "
        + "state the gap rather than filling it.\n"
        + "- INFERENCE FIREWALL: one logical step maximum from any stated fact. See step 4.\n"
        + "- NO FLUFF: avoid vague phrases ('dynamic environment', 'strategic pivot', "
        + "'rapidly evolving landscape'). Be specific or omit.\n"
        + "- NO DRAMATIC LANGUAGE: avoid 'financial distress', 'collapse', 'crisis', 'catastrophic'.\n"
        + "- CROSS-SYNTHESIS: do not summarize records one by one. Group by theme. See step 1.\n"
        + "- NUMERIC FIDELITY: reproduce numbers exactly. '$4.2B' stays '$4.2B'.\n"
        + "- NUMERIC ENFORCEMENT: when records contain numeric financial deltas, include at least one "
        + "exact figure in EXECUTIVE SUMMARY.\n"
        + "- TIER-1 LENS: at least one explicit Tier-1 implication grounded in evidence bullets.\n"
        + "- BANNED OPENERS: never start a sentence or clause with 'This signals', 'This indicates', "
        + "'This necessitates', 'This underscores', 'This highlights', 'This suggests', or 'This reflects' "
        + "as a standalone clause opener. Use subject-verb constructions instead.\n"
        + "- NO SECTION REPETITION: each fact or implication appears in exactly one section. See step 7.\n"
        + executive_extra_constraints
        + "- No emojis. Executive tone.\n\n"
        + "APPROVED RECORDS (JSON list):\n"
        + records_json
    )


def _build_synthesis_prompt(records: List[Dict], week_range: str, output_mode: str = "operational") -> str:
    """Prepare inputs and delegate to build_prompt."""
    mode = _choose_brief_mode(len(records))
    region_list = "\n".join(f"  - {r}" for r in FOOTPRINT_REGIONS)
    slim = [_slim_record(r) for r in records]
    records_json = json.dumps(slim, indent=1, default=str)
    record_ids = [str(r.get("record_id") or "").strip() for r in records if str(r.get("record_id") or "").strip()]
    record_ids_text = ", ".join(record_ids) if record_ids else "(none)"
    is_single = mode["name"] == "single"
    intro = (
        "Draft a single-record executive alert with high signal density."
        if is_single
        else "Draft a weekly executive brief."
    )
    return build_prompt(records, week_range, record_ids_text, records_json, mode, intro, region_list, output_mode)


def synthesize_weekly_brief_llm(
    records: List[Dict],
    week_range: str,
    provider: str = "gemini",
    web_check: bool = False,
    model_override: Optional[str] = None,
    output_mode: str = "operational",
) -> Tuple[str, Dict[str, Any]]:
    """Generate an LLM-synthesized weekly executive brief from approved records.

    Args:
        records: Approved records to synthesize.
        week_range: Human-readable period label (e.g. 'Feb 10-17, 2026').
        provider: LLM provider ('gemini', 'claude', 'chatgpt').
        web_check: If True, ask the LLM to verify claims against the web.
        model_override: Override the default model name.
        output_mode: 'operational' (full brief) or 'executive' (summary + high priority only).

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

    prompt = _build_synthesis_prompt(records, week_range, output_mode=output_mode)
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
