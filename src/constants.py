from __future__ import annotations

CANON_TOPICS = [
    "OEM Strategy & Powertrain Shifts",
    "Closure Technology & Innovation",
    "OEM Programs & Vehicle Platforms",
    "Regulatory & Safety",
    "Supply Chain & Manufacturing",
    "Technology Partnerships & Components",
    "Market & Competition",
    "Financial & Business Performance",
    "Executive & Organizational",
]

FOOTPRINT_REGIONS = ["India", "China", "Europe (including Russia)", "Africa", "US", "Mexico", "Thailand"]

ALLOWED_SOURCE_TYPES = {"Bloomberg", "Automotive News", "Reuters", "Patent", "Press Release", "S&P", "MarkLines", "Other"}
ALLOWED_ACTOR_TYPES = {"oem", "supplier", "tech_partner", "government", "regulator", "industry_group", "media", "other"}
ALLOWED_PRIORITY = {"High", "Medium", "Low"}
ALLOWED_CONF = {"High", "Medium", "Low"}
ALLOWED_REVIEW = {"Not Reviewed", "Reviewed", "Approved"}

REQUIRED_KEYS = [
    "title","source_type","publish_date","publish_date_confidence","original_url",
    "actor_type","government_entities","companies_mentioned","mentions_our_company",
    "topics","keywords","country_mentions","regions_mentioned","regions_relevant_to_kiekert",
    "region_signal_type","supply_flow_hint","priority","confidence","evidence_bullets",
    "key_insights","strategic_implications","recommended_actions","review_status","notes"
]
