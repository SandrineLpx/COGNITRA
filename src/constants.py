from __future__ import annotations

# ---------------------------------------------------------------------------
# Canonical topics — multi-label, 1-4 per record.
# Tagging guidance (use / don't use) is embedded in the extraction prompt
# in model_router.py. Update both places when adding or renaming a topic.
#
#   OEM Strategy & Powertrain Shifts
#     Use: broad OEM pivots (BEV/ICE mix, vertical integration, platform resets, localization)
#     Not: single program updates (→ OEM Programs)
#   Closure Technology & Innovation
#     Use: ONLY when latch/door/handle/digital key/smart entry/cinch appears explicitly
#     Not: general vehicle electronics (→ Technology Partnerships)
#   OEM Programs & Vehicle Platforms
#     Use: specific program announcements (launches, refreshes, sourcing decisions)
#     Not: broad strategy narratives (→ OEM Strategy)
#   Regulatory & Safety
#     Use: regulations, standards, recalls, cybersecurity rules
#     Not: general political news (→ Market & Competition or Supply Chain)
#   Supply Chain & Manufacturing
#     Use: plant openings/closures, disruptions, logistics, labor, tariffs on supply
#     Not: pure financial performance (→ Financial & Business Performance)
#   Technology Partnerships & Components
#     Use: partnerships/component sourcing where tech is central (chips, sensors, connectivity)
#     Not: purely commercial alliances (→ Market & Competition)
#   Market & Competition
#     Use: demand, registrations, pricing, share shifts, competitor comparisons
#     Not: internal exec changes (→ Executive & Organizational)
#   Financial & Business Performance
#     Use: earnings, guidance, M&A, restructurings, insolvency (financial lens)
#     Not: exec churn without financial angle (→ Executive & Organizational)
#   Executive & Organizational
#     Use: leadership changes, governance, org restructuring
#     Not: M&A purely as transaction (→ Financial & Business Performance)
# ---------------------------------------------------------------------------
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

FOOTPRINT_REGIONS = [
    # Individual Apex Mobility countries (display = their own name)
    "Czech Republic", "France", "Germany", "Italy", "Morocco",
    "Mexico", "Portugal", "Russia", "Spain", "Sweden",
    "United Kingdom", "United States", "Thailand", "India",
    "China", "Taiwan", "Japan", "South Korea",
    # Sub-regional buckets
    "West Europe", "Central Europe", "East Europe",
    "Africa", "Middle East",
    "NAFTA", "ASEAN", "Indian Subcontinent",
    "Andean", "Mercosul", "Central America",
    "Oceania", "Rest of World",
    # Generic catch-alls (from broad aliases: eu→Europe, asia→South Asia, etc.)
    "Europe", "South America", "South Asia",
]

# Display regions = same set as FOOTPRINT_REGIONS.
# In the new design every footprint value is its own display value
# (individual Apex Mobility countries display by name; sub-regions display by market bucket).
DISPLAY_REGIONS = FOOTPRINT_REGIONS

# No collapse mapping needed: every footprint value is already a display value.
# Code uses FOOTPRINT_TO_DISPLAY.get(r, r) — empty dict means identity mapping.
FOOTPRINT_TO_DISPLAY: dict = {}

ALLOWED_SOURCE_TYPES = {"Bloomberg", "Automotive News", "Reuters", "Patent", "Press Release", "S&P", "MarkLines", "Financial News", "GlobalData", "Industry Publication", "Other"}
ALLOWED_ACTOR_TYPES = {"oem", "supplier", "technology", "industry", "other"}
ALLOWED_PRIORITY = {"High", "Medium", "Low"}
ALLOWED_CONF = {"High", "Medium", "Low"}
ALLOWED_REVIEW = {"Pending", "Approved", "Disapproved"}
# Legacy compat: old records may have "Not Reviewed" or "Reviewed" — treat as "Pending".
_LEGACY_REVIEW_MAP = {"Not Reviewed": "Pending", "Reviewed": "Pending"}

REQUIRED_KEYS = [
    "title","source_type","publish_date","publish_date_confidence","original_url",
    "actor_type","government_entities","companies_mentioned","mentions_our_company",
    "topics","keywords","country_mentions","regions_mentioned","regions_relevant_to_apex_mobility",
    "priority","confidence","evidence_bullets",
    "key_insights","review_status","notes"
]

# ---------------------------------------------------------------------------
# Macro-theme detection rules (postprocess-computed, not LLM-extracted).
# Each rule: name, required signal groups, min_groups to fire.
#   "companies": at least one company in the record's companies_mentioned
#   "keywords":  at least one keyword/regex found in record text
#   "topics":    at least one canonical topic present
#   "regions":   at least one footprint region present
# Optional per-rule fields:
#   "anti_keywords": list[str] — suppress theme if any match and <3 groups hit
#   "premium_company_gate": bool — require company match in PREMIUM_OEMS
#   "region_requirements": set[str] — require region group to include one of these
#   "rollup": str — cluster label for overlapping themes
# A theme fires when >= min_groups distinct signal groups match.
# ---------------------------------------------------------------------------

PREMIUM_OEMS = {
    "bmw", "mercedes-benz", "mercedes", "audi", "porsche",
    "jaguar", "land rover", "volvo cars", "bentley", "rolls-royce",
    "maserati", "lamborghini",
}

MACRO_THEME_RULES = [
    {
        "name": "Luxury OEM Stress",
        "min_groups": 2,
        "signals": {
            "companies": PREMIUM_OEMS,
            "keywords": [r"margin", r"profit\s*warn", r"cost\s*cut", r"restructur",
                         r"sales\s*declin", r"downturn", r"layoff", r"headcount",
                         r"earnings\s*miss", r"revenue\s*drop"],
        },
        "anti_keywords": [r"record\s*profit", r"sales\s*surge", r"beat\s*expect"],
        "premium_company_gate": True,
        "rollup": "Premium OEM Financial/Strategy Stress",
    },
    {
        "name": "China EV Competitive Acceleration",
        "min_groups": 2,
        "signals": {
            "companies": {"byd", "nio", "xpeng", "li auto", "geely", "chery",
                          "great wall", "saic", "changan"},
            "keywords": [r"price\s*war", r"ev\s*export", r"electric\s*vehicle",
                         r"\bev\b", r"\bnev\b", r"battery\s*cost",
                         r"competition", r"market\s*share"],
            "regions": {"China", "South Asia"},
        },
        "anti_keywords": [r"ev\s*sales\s*stall", r"ev\s*slow"],
        # Require China as an explicitly operational market (in regions_relevant_to_apex_mobility,
        # derived from country_mentions). Prevents theme firing when Chinese EV brands are
        # mentioned only as competitive backdrop in a European market registrations article.
        "region_requirements": {"China"},
    },
    {
        "name": "Software-Defined Premium Shift",
        "min_groups": 2,
        "signals": {
            "companies": {
                "nvidia", "nvidia corp.",
                "huawei", "huawei technologies co.",
                "google", "google llc",
                "microsoft", "microsoft corporation",
                "openai", "openai inc.",
            },
            "keywords": [r"software.defined", r"\bsdv\b", r"digital\s*cockpit",
                         r"\bota\b", r"over.the.air", r"connected\s*car",
                         r"vehicle\s*software", r"digital\s*key",
                         r"smart\s*entry", r"e.?architecture",
                         r"\bopenai\b", r"\bmicrosoft\b", r"\bgoogle\b",
                         r"voice\s*control", r"infotainment", r"ai\s*assistant"],
            "topics": {"Closure Technology & Innovation",
                       "Technology Partnerships & Components"},
        },
    },
    {
        "name": "Margin Compression at Premium OEMs",
        "min_groups": 2,
        "signals": {
            "companies": PREMIUM_OEMS,
            "keywords": [r"margin", r"cost\s*pressure", r"profit", r"ebit",
                         r"pricing\s*pressure", r"supplier\s*squeeze",
                         r"raw\s*material", r"inflation"],
        },
        "anti_keywords": [r"record\s*profit", r"margin\s*expan"],
        "premium_company_gate": True,
        "rollup": "Premium OEM Financial/Strategy Stress",
    },
    {
        "name": "Tariff & Trade Disruption",
        "min_groups": 2,
        "signals": {
            "keywords": [r"tariff", r"trade\s*war", r"import\s*dut", r"customs",
                         r"section\s*301", r"nearshoring", r"reshoring",
                         r"trade\s*barrier", r"countervailing"],
            "regions": {"United States", "Mexico", "China", "West Europe", "East Europe", "Russia",
                       "South America"},
        },
        "region_requirements": {"United States", "China", "West Europe", "East Europe", "Russia"},
    },
    {
        "name": "EV Transition Slowdown",
        "min_groups": 2,
        "signals": {
            "keywords": [r"ev\s*slow", r"ev\s*delay", r"hybrid\s*pivot",
                         r"electrification\s*pause", r"ice\s*demand",
                         r"ev\s*adoption", r"charging\s*infra",
                         r"ev\s*target.*push", r"phase.?out\s*delay"],
            "topics": {"OEM Strategy & Powertrain Shifts"},
        },
        "anti_keywords": [r"ev\s*sales\s*surge", r"ev\s*record"],
    },
]

STRUCTURAL_ROLLUP_RULES = [
    {
        "themes": {"China EV Competitive Acceleration", "Software-Defined Premium Shift"},
        "rollup": "China Tech-Driven Premium Disruption",
    },
]

# Macro themes that can escalate priority when Apex Mobility footprint relevance exists.
MACRO_THEME_PRIORITY_ESCALATION_THEMES = {
    "Luxury OEM Stress",
    "Margin Compression at Premium OEMs",
    "China EV Competitive Acceleration",
    "Tariff & Trade Disruption",
}

# Single source of truth for uncertainty language detection.
# Used by both briefing.py (mandatory CONFLICTS & UNCERTAINTY section)
# and quality.py (KPI-B3 uncertainty compliance check).
UNCERTAINTY_WORDS = (
    r"\b(forecast|could|weighing|sources said|expected|may|might|"
    r"uncertain|preliminary|unconfirmed|estimated|projected|reportedly|"
    r"reconsider|reviewing|speculation)\b"
)

# Topics that trigger mandatory CONFLICTS & UNCERTAINTY in the weekly brief.
UNCERTAINTY_TOPICS = {
    "OEM Strategy & Powertrain Shifts",
    "Financial & Business Performance",
}

FIELD_POLICY = {
    "llm": [
        "title", "actor_type", "mentions_our_company", "topics", "keywords",
        "evidence_bullets", "key_insights",
        "review_status", "notes",
    ],
    "python": [
        "regions_mentioned", "regions_relevant_to_apex_mobility", "event_date",
        "priority_llm", "priority_final", "priority_reason",
    ],
    "hybrid": [
        "source_type", "publish_date", "publish_date_confidence", "original_url",
        "government_entities", "companies_mentioned", "country_mentions",
        "priority",
    ],
}
