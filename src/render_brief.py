from __future__ import annotations
from datetime import date

def _list(items: list[str]) -> str:
    if not items:
        return "- [None]\n"
    return "".join([f"- {x}\n" for x in items])

def render_intelligence_brief(rec: dict) -> str:
    summary_date = date.today().isoformat()
    publish_date = rec.get("publish_date") or "Unknown"
    url = rec.get("original_url") or "[optional]"

    md = []
    md.append("INTELLIGENCE BRIEF\n\n")
    md.append(f"Summary Date: {summary_date}\n")
    md.append(f"Source Type: {rec.get('source_type')}\n")
    md.append(f"Publish Date: {publish_date}\n")
    md.append(f"Original URL: {url}\n\n")

    md.append("Title\n")
    md.append(f"{rec.get('title')}\n\n")

    md.append("Companies Mentioned\n")
    md.append(_list(rec.get('companies_mentioned', [])) + "\n")

    md.append("Actor Type\n")
    md.append(f"- {rec.get('actor_type')}\n")
    ge = rec.get("government_entities") or []
    if ge:
        md.append("\nGovernment/Regulators (if applicable)\n")
        md.append(_list(ge))
    md.append("\n")

    md.append(
        "Countries Mentioned: "
        f"{', '.join(rec.get('country_mentions', [])) or '[None]'}"
        " | Relevant Regions: "
        f"{', '.join(rec.get('regions_relevant_to_apex_mobility', [])) or '[None]'}\n"
    )
    rst = rec.get("region_signal_type")
    if rst:
        md.append(f"Region Signal Type: {rst}\n")
    sfh = rec.get("supply_flow_hint") or ""
    if sfh:
        md.append(f"Supply Flow Hint: {sfh}\n")
    md.append("\n")

    md.append("Topics Covered (canonical)\n")
    md.append(_list(rec.get("topics", [])) + "\n")

    md.append(f"Priority: {rec.get('priority')} | Confidence: {rec.get('confidence')}\n\n")

    md.append("Evidence (verifiable facts)\n")
    md.append(_list(rec.get("evidence_bullets", [])) + "\n")

    md.append("Key Insights (interpretation)\n")
    md.append(_list(rec.get("key_insights", [])) + "\n")

    si = rec.get("strategic_implications") or []
    if si:
        md.append("Strategic Implications (closure systems supplier lens)\n")
        md.append(_list(si) + "\n")

    ra = rec.get("recommended_actions") or []
    if ra:
        md.append("Recommended Actions\n")
        md.append(_list(ra) + "\n")

    md.append("Review\n")
    md.append(f"Reviewed By: {rec.get('reviewed_by','[name]')}\n")
    md.append(f"Review Status: {rec.get('review_status')}\n")
    notes = rec.get("notes") or ""
    if notes:
        md.append(f"Notes: {notes}\n")

    return "".join(md)
