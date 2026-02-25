# COGNITRA Reusability Strategy

**Goal**: Transform COGNITRA from an Apex Mobility-specific system into a **generalized, industry-agnostic intelligence platform** that can be deployed for any company across any sector.

---

## Executive Summary

COGNITRA can be made reusable through a **Configuration-First Architecture** where:

1. **Domain knowledge** (topics, competitors, regions, thresholds) moves from hardcoded constants → **JSON/YAML config files**
2. **Company-specific logic** (prompt context, priority rules, macro themes) becomes **data-driven templates**
3. **The extraction and processing pipelines** remain **unchanged** (generic enough already)
4. **Deployment** happens via **config injection** at startup

This allows a single codebase to serve multiple customers with zero code changes.

---

## 1. Current Hard-Coded Apex Mobility Dependencies

### 1.1 In `src/constants.py`

```python
# Hard-coded as constants — need to parametrize:
CANON_TOPICS = [
    "OEM Strategy & Powertrain Shifts",           # ← Automotive-specific
    "Closure Technology & Innovation",             # ← Apex Mobility-specific
    "OEM Programs & Vehicle Platforms",            # ← Automotive-specific
    # ...
]

PREMIUM_OEMS = {
    "bmw", "mercedes-benz", "audi",               # ← Apex Mobility competitors
    # ...
}

MACRO_THEME_RULES = [
    {
        "name": "Luxury OEM Stress",              # ← Apex-specific theme
        "companies": PREMIUM_OEMS,
        # ...
    },
    # ...
]

FOOTPRINT_REGIONS = [                             # ← Hardcoded for Apex
    "Czech Republic", "France", "Germany",        # Individual markets
    "West Europe", "Central Europe",              # Sub-regions
    # ...
]
```

### 1.2 In `src/model_router.py` → `extraction_prompt()`

```python
def extraction_prompt(context_pack: str) -> str:
    return (
        "You are extracting structured intelligence for Apex Mobility, "
        "an automotive closure systems supplier... "
        
        # Hard-coded competitor list:
        "CLOSURE SYSTEMS COMPETITORS — set actor_type='supplier' for these:\n"
        "Tier 1: Hi-Lex, Aisin, Brose, Huf, Magna, Inteva, Mitsui Kinzoku\n"
        "Tier 2: Ushin, Witte, Mitsuba, Fudi, PHA, Cebi, Tri-Circle\n"
        "Our company: Apex Mobility\n"
        
        # Hard-coded topic guidance:
        "TOPIC CLASSIFICATION — pick 1-4 topics using these rules:\n"
        "- 'OEM Strategy & Powertrain Shifts'...\n"
        "- 'Closure Technology & Innovation'...\n"
        # ...
    )
```

### 1.3 In `data/new_country_mapping.csv`

```csv
# Hard-coded Apex Mobility footprint:
country,entry,region,market,relevant to Kieket,display
country,Czech Republic,Europe,Central Europe,Czech Republic,Czech Republic
country,France,Europe,West Europe,France,France
country,Germany,Europe,West Europe,Germany,Germany
# ... (only Apex-relevant countries)
```

### 1.4 In `src/postprocess.py`

```python
# Hard-coded priority boost logic for Apex:
def _boost_priority(rec: Dict) -> Optional[str]:
    macro_themes = rec.get("macro_themes_detected", [])
    regions = rec.get("regions_relevant_to_apex_mobility", [])
    
    # Amp up priority if footprint + theme align:
    if "Tariff & Trade Disruption" in macro_themes:
        if any(r in regions for r in [...Apex-specific footprint...]):
            priority = "High"
    # ...
```

---

## 2. Proposed Configuration Architecture

### 2.1 Config File Structure

```
config/
├── company-config.yaml          # Company profile, footprint, competitors
├── topics-taxonomy.yaml         # Industry topics + classification rules
├── macro-themes.yaml            # Theme detection rules
├── priority-rules.yaml          # Priority boosting heuristics
├── region-mapping.csv           # Country → footprint mapping
└── source-types.yaml            # Trusted source types for this industry
```

### 2.2 Example: `config/company-config.yaml`

```yaml
# ============================================================================
# COMPANY PROFILE
# ============================================================================

company:
  name: "Apex Mobility"
  industry: "Automotive - Closure Systems"
  domain_description: |
    Automotive closure systems supplier specializing in door latches,
    strikers, handles, smart entry, and cinch systems.
  
  # What mentions of THIS company are ground truth
  company_name: "Apex Mobility"
  company_aliases: ["Apex"]
  
  # Competitor watch list (structured with tiers)
  competitors:
    tier_1:
      - "Hi-Lex"
      - "Aisin"
      - "Brose"
      - "Huf"
      - "Magna"
      - "Magna Closures"
      - "Magna Mechatronics"
      - "Inteva"
      - "Mitsui Kinzoku"
    tier_2:
      - "Ushin"
      - "Witte"
      - "Mitsuba"
      - "Fudi"
      - "PHA"
      - "Cebi"
      - "Tri-Circle"
  
  # Premium customer segment (OEMs) for elevated signaling
  premium_customers:
    - "BMW"
    - "Mercedes-Benz"
    - "Audi"
    - "Porsche"
    - "Jaguar"
    - "Land Rover"
    - "Volvo Cars"
    - "Bentley"
    - "Rolls-Royce"
    - "Maserati"
    - "Lamborghini"
  
  # Geographic footprint (markets where company operates or plans)
  core_markets:
    - "United States"
    - "Germany"
    - "France"
    - "Czech Republic"
    - "Mexico"
    - "China"
    - "Japan"
  
  # Secondary markets (monitor but lower priority)
  secondary_markets:
    - "United Kingdom"
    - "Spain"
    - "Italy"
    - "India"
    - "Thailand"
    - "South Korea"
  
  # Regions for analytics aggregation
  region_groups:
    "North America": ["United States", "Mexico", "Canada"]
    "Western Europe": ["Germany", "France", "United Kingdom", "Spain", "Italy"]
    "Central Europe": ["Czech Republic", "Poland", "Hungary"]
    "Asia-Pacific": ["China", "Japan", "India", "Thailand", "South Korea"]
    "Rest of World": []  # Fallback catch-all

# ============================================================================
# PRIORITY ESCALATION RULES
# ============================================================================

priority_rules:
  # High priority triggers
  high_priority:
    # OEM strategy shifts affecting platform or sourcing
    - pattern: "oem|strategy|shift|sourcing"
      footprint_required: true
      boost: 2
    
    # Competitor wins or losses in core markets
    - pattern: "competitor.*win|contract|supply"
      companies: ["competitors"]  # Reference to config.company.competitors
      regions: ["core_markets"]   # Reference to config.company.core_markets
      boost: 1
    
    # Supply disruptions in footprint
    - pattern: "supply|disruption|shortage|plant.*close"
      regions: ["core_markets"]
      boost: 1
  
  # Medium priority triggers
  medium_priority:
    - pattern: "market|demand|demand"
      regions: ["secondary_markets"]
      boost: 0

# ============================================================================
# UNCERTAINTY & CAUTIONARY LANGUAGE
# ============================================================================

uncertainty_words: |
  \b(forecast|could|weighing|sources said|expected|may|might|
  uncertain|preliminary|unconfirmed|estimated|projected|reportedly|
  reconsider|reviewing|speculation)\b

uncertainty_topics: []  # Reference to topics (will be populated)
```

### 2.3 Example: `config/topics-taxonomy.yaml`

```yaml
# ============================================================================
# INDUSTRY-SPECIFIC TOPICS (1-4 per record)
# ============================================================================

topics:
  
  - name: "OEM Strategy & Powertrain Shifts"
    description: "Broad OEM strategic pivots (BEV/ICE mix, vertical integration, platform resets, localization)"
    use_when: "Strategic pivot or market reposition"
    avoid_when: "Single program update"
    industry_keywords:
      - oem|strategy|shift|pivot|powertrain|bev|ice|electric|vehicle|platform
  
  - name: "Closure Technology & Innovation"
    description: "Product innovation in door latches, handles, smart entry, cinch systems"
    use_when: "Explicit mention: latch|door|handle|digital key|smart entry|cinch"
    avoid_when: "General vehicle electronics"
    required_keywords:
      - "latch|door|handle|digital key|smart entry|cinch"  # MUST match one
    industry_keywords:
      - mechanism|actuator|electronics|software|digital
  
  - name: "OEM Programs & Vehicle Platforms"
    description: "Specific program announcements (launches, refreshes, sourcing)"
    use_when: "Program/platform launch or sourcing decision"
    avoid_when: "Broad strategy narratives"
    industry_keywords:
      - program|platform|model|launch|refresh|generation
  
  - name: "Supply Chain & Manufacturing"
    description: "Plant openings/closures, disruptions, logistics, labor, tariffs"
    use_when: "Manufacturing or supply execution news"
    avoid_when: "Pure financial performance"
    industry_keywords:
      - supply|manufacturing|plant|factory|production|disruption|logistics
  
  # ... more topics
```

### 2.4 Example: `config/macro-themes.yaml`

```yaml
# ============================================================================
# MACRO-THEME DETECTION RULES (postprocess-computed)
# ============================================================================

macro_themes:
  
  - name: "Competitor Financial Stress"
    min_groups: 2
    signals:
      companies: ["competitors.tier_1", "competitors.tier_2"]  # References config
      keywords:
        - r"margin|profit\s*warn|cost\s*cut|restructur"
        - r"sales\s*declin|downturn|layoff|headcount"
        - r"earnings\s*miss|revenue\s*drop"
    anti_keywords:
      - r"record\s*profit|sales\s*surge|beat\s*expect"
    requires_gate:
      premium_customers: true  # Must match premium_customers list
    rollup: "Competitor Stress & Opportunity"
  
  - name: "Supply Chain Disruption"
    min_groups: 2
    signals:
      keywords:
        - r"tariff|trade\s*war|import\s*dut|customs"
        - r"nearshoring|reshoring|supply\s*chain"
      regions: ["core_markets", "secondary_markets"]
    region_requirements: ["core_markets"]  # Must match at least one
    rollup: "Footprint-Based Supply Risk"
  
  - name: "Technology Partnership Acceleration"
    min_groups: 2
    signals:
      companies: ["tech_partners"]  # New external list
      keywords: ["ai|software|digital|cloud|edge|5g|autonomous"]
      topics: ["Technology Partnerships & Components"]
    rollup: "Strategic Tech Trends"

# Tech companies to watch (cross-industry)
tech_partners:
  - "nvidia"
  - "qualcomm"
  - "google"
  - "microsoft"
  - "amazon"
```

### 2.5 Example: `config/region-mapping.csv`

```csv
country,continent,region_bucket,core_market,secondary_market,display_name
country,United States,NAFTA,YES,,United States
country,Mexico,NAFTA,,YES,Mexico
country,Germany,West Europe,YES,,Germany
country,France,West Europe,YES,,France
country,Czech Republic,Central Europe,YES,,Czech Republic
country,China,Asia,,YES,China
country,Japan,Asia,,YES,Japan
country,Canada,NAFTA,,YES,Canada
country,United Kingdom,West Europe,,YES,United Kingdom
# ... expand as needed
```

---

## 3. Implementation: Configuration Loading

### 3.1 New Module: `src/config_loader.py`

```python
"""
Configuration loader: reads YAML/CSV and builds runtime constants.
Single source of truth for deployment-time customization.
"""

from pathlib import Path
from typing import Dict, Any, List
import yaml
import csv

class CompanyConfig:
    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self._load_all()
    
    def _load_all(self) -> None:
        """Load all config files at startup."""
        self.company = self._load_yaml("company-config.yaml")
        self.topics = self._load_yaml("topics-taxonomy.yaml")
        self.macro_themes = self._load_yaml("macro-themes.yaml")
        self.priority_rules = self._load_yaml("priority-rules.yaml")
        self.region_mapping = self._load_csv("region-mapping.csv")
        self.source_types = self._load_yaml("source-types.yaml")
        
        # Compute derived constants (canonicalized lists)
        self.COMPANY_NAME = self.company.get("company", {}).get("name")
        self.COMPETITORS_FLAT = self._flatten_competitors()
        self.PREMIUM_CUSTOMERS = self._get_premium_customers()
        self.CORE_MARKETS = self._get_core_markets()
        self.CANONICAL_TOPICS = [t["name"] for t in self.topics.get("topics", [])]
        # ...
    
    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        path = self.config_dir / filename
        if not path.exists():
            return {}
        with open(path) as f:
            return yaml.safe_load(f) or {}
    
    def _load_csv(self, filename: str) -> List[Dict[str, str]]:
        path = self.config_dir / filename
        if not path.exists():
            return []
        rows = []
        with open(path) as f:
            reader = csv.DictReader(f)
            rows.extend(reader)
        return rows
    
    def _flatten_competitors(self) -> set:
        """Flatten tier_1 + tier_2 competitors into single set."""
        competitors = self.company.get("company", {}).get("competitors", {})
        flat = set()
        for tier in ["tier_1", "tier_2"]:
            flat.update(competitors.get(tier, []))
        return flat
    
    def _get_premium_customers(self) -> set:
        """Get premium customer list (OEMs, etc.)."""
        return set(self.company.get("company", {}).get("premium_customers", []))
    
    def _get_core_markets(self) -> set:
        """Get core market list."""
        return set(self.company.get("company", {}).get("core_markets", []))


def load_runtime_constants(config_dir: Path = None) -> CompanyConfig:
    """Load config and return object usable by all modules."""
    if config_dir is None:
        config_dir = Path(__file__).parents[1] / "config"
    
    cfg = CompanyConfig(config_dir)
    return cfg
```

### 3.2 Update `src/constants.py` → Load from Config

```python
"""
Runtime constants loaded from config/ directory.
Apex Mobility is the default; swap config/ to deploy for other companies.
"""

from pathlib import Path
from src.config_loader import load_runtime_constants

# Load config at module import time
_CONFIG_DIR = Path(__file__).parents[1] / "config"
_RUNTIME_CONFIG = load_runtime_constants(_CONFIG_DIR)

# Export as module-level constants (backward compatible)
COMPANY_NAME = _RUNTIME_CONFIG.COMPANY_NAME
COMPETITORS = _RUNTIME_CONFIG.COMPETITORS_FLAT
PREMIUM_CUSTOMERS = _RUNTIME_CONFIG.PREMIUM_CUSTOMERS
CANON_TOPICS = _RUNTIME_CONFIG.CANONICAL_TOPICS
MACRO_THEME_RULES = _RUNTIME_CONFIG.macro_themes.get("macro_themes", [])
MACRO_THEME_PRIORITY_ESCALATION_THEMES = _RUNTIME_CONFIG._compute_escalation_themes()
CORE_MARKETS = _RUNTIME_CONFIG.CORE_MARKETS
FOOTPRINT_REGIONS = _RUNTIME_CONFIG._compute_footprint_regions()
DISPLAY_REGIONS = FOOTPRINT_REGIONS
COUNTRY_TO_FOOTPRINT = _RUNTIME_CONFIG._build_country_mapping()

# ... rest of constants stay the same
```

### 3.3 Update `src/model_router.py` → Load Prompt Template

```python
def extraction_prompt(context_pack: str, config: CompanyConfig) -> str:
    """
    Build extraction prompt from config.
    
    No hard-coding of company name, competitors, topics, regions.
    All comes from config/ at runtime.
    """
    
    # Build competitor list from config
    competitors_text = _format_competitors_block(config)
    
    # Build topic guidance from config
    topic_guidance = _format_topic_guidance(config)
    
    # Build region list from config
    region_list = _format_region_list(config)
    
    return (
        f"You are extracting structured intelligence for {config.COMPANY_NAME}, "
        f"a {config.company.get('company', {}).get('industry')} entity. "
        f"{config.company.get('company', {}).get('domain_description')} "
        f"Return JSON only matching the schema. Follow these rules strictly:\n\n"
        # ... standard rules ...
        f"\nCOMPETITORS — set actor_type='supplier' for these companies:\n"
        f"{competitors_text}"
        f"\n{topic_guidance}"
        f"\n{region_list}"
        # ... rest of prompt ...
        f"\nINPUT (context pack):\n{context_pack}"
    )
```

---

## 4. Deployment Model

### 4.1 Single-Company Deployment (Current Model)

```
COGNITRA/
├── config/
│   └── company-config.yaml      ← Apex Mobility profile
├── Home.py
├── src/
│   ├── constants.py             ← Loads from config/
│   ├── model_router.py          ← Uses constants
│   └── ...
├── data/                        ← Apex Mobility records
└── streamlit_config.toml        ← Apex branding
```

### 4.2 Multi-Tenant Deployment (SaaS)

```
COGNITRA/
├── deployment/
│   ├── apex_mobility/
│   │   ├── config/              ← Apex-specific
│   │   ├── data/
│   │   └── streamlit_config.toml
│   ├── semiconductor_vendor/
│   │   ├── config/              ← Semiconductor-specific
│   │   ├── data/
│   │   └── streamlit_config.toml
│   └── pharma_company/
│       ├── config/              ← Pharma-specific
│       ├── data/
│       └── streamlit_config.toml
├── Home.py                      ← Tenant-agnostic
├── src/
│   ├── constants.py
│   ├── config_loader.py
│   └── ...
└── scripts/
    └── deploy-tenant.sh         ← Spin up new config
```

### 4.3 Launch Command

```bash
# Apex Mobility (default)
CONFIG_DIR=./config COMPANY_NAME="Apex Mobility" streamlit run Home.py

# Switch to semiconductor vendor
CONFIG_DIR=./deployment/semiconductor/config COMPANY_NAME="SemiCorp" streamlit run Home.py

# Switch to pharma
CONFIG_DIR=./deployment/pharma/config COMPANY_NAME="PharmaCorp" streamlit run Home.py
```

---

## 5. Customization Scope by Domain

### 5.1 Automotive (Current: Apex Mobility)

```yaml
# Topics
topics:
  - OEM Strategy & Powertrain Shifts
  - Closure Technology & Innovation     # ← Replace with your component focus
  - OEM Programs & Vehicle Platforms
  - Regulatory & Safety
  - Supply Chain & Manufacturing
  - Technology Partnerships & Components
  - Market & Competition
  - Financial & Business Performance
  - Executive & Organizational

# Competitors (replace tier lists)
tier_1:
  - Your Direct Competitors
  - ...
tier_2:
  - Secondary Competitors
  - ...

# Premium Customers (OEMs you supply to)
premium_customers:
  - BMW
  - Mercedes-Benz
  - ...
```

### 5.2 Semiconductor Supply

```yaml
# Topics
topics:
  - Chip Design & Architecture Shifts
  - Process Technology Roadmaps        # Replaces closure tech
  - Fab Capacity & Manufacturing
  - Regulatory & Security
  - Supply Chain & Geopolitics
  - Technology Partnerships
  - Market & Competition (Fab share, design wins)
  - Financial & Business Performance
  - M&A & Strategic Moves

# Competitors
tier_1:
  - TSMC
  - Samsung
  - Intel
  - ...
tier_2:
  - GlobalFoundries
  - UMC
  - ...

# Premium Customers (flagship accounts)
premium_customers:
  - Apple
  - Qualcomm
  - ...

# Core Markets
core_markets:
  - Taiwan
  - South Korea
  - United States
  - Japan
  - China

# Region Groups
region_groups:
  "Taiwan": ["Taiwan"]
  "South Korea": ["South Korea"]
  "US": ["United States"]
  "Japan": ["Japan"]
  "China": ["China"]
  "Europe": ["Germany", "Netherlands"]
```

### 5.3 Pharmaceutical (Supply/Manufacturing Focus)

```yaml
# Topics
topics:
  - Pipeline & Drug Development
  - Manufacturing & Supply Chain    # ← Different priorities
  - Regulatory & Approval
  - M&A & Partnerships
  - Market & Competition
  - Clinical & Safety Data
  - Financial & Business Performance
  - Executive & Organizational

# Competitors
tier_1:
  - Pfizer
  - Moderna
  - Roche
  - ...

# Premium Customers (large pharma collaborators)
premium_customers:
  - WHO
  - FDA
  - EMA
  - Major Health Systems

# Core Markets
core_markets:
  - United States
  - Germany
  - United Kingdom
  - Japan
  - India
```

---

## 6. Implementation Roadmap

### Phase 1: Configuration Extraction (1-2 weeks)
- [ ] Create `src/config_loader.py`
- [ ] Define config schema (YAML + CSV formats)
- [ ] Extract all Apex-specific constants → config files
- [ ] Update `src/constants.py` to load from config
- [ ] Update `src/model_router.py` → extraction_prompt() loads from config
- [ ] Test backward compatibility (Apex Mobility as default)

### Phase 2: Prompt Templating (1 week)
- [ ] Parameterize extraction prompt (company name, competitors, topics, regions)
- [ ] Create prompt template builder (`_format_competitors_block()`, etc.)
- [ ] Test prompt quality with sample PDFs

### Phase 3: Priority & Scoring Rules (1 week)
- [ ] Move `_boost_priority()` logic to config-driven rules
- [ ] Parameterize macro-theme detection (company list, keyword sets, regions)
- [ ] Test scoring consistency

### Phase 4: Documentation & Examples (1 week)
- [ ] Create `docs/DEPLOYMENT_GUIDE.md` (step-by-step for new company)
- [ ] Create example configs for 2-3 other industries
- [ ] Document all customization points

### Phase 5: Testing & Validation (1 week)
- [ ] Multi-tenant test (spin up 3 different company configs)
- [ ] Verify records isolate per tenant
- [ ] Verify LLM prompts differ correctly
- [ ] Verify priority scoring adapts

### Phase 6: Deployment Automation (optional)
- [ ] Create CLI to scaffold new company config
- [ ] Create Docker template for multi-tenant SaaS
- [ ] Create GitHub Actions for config validation

---

## 7. Key Customization Checklist

For any new company deployment:

```
Company Onboarding Checklist
─────────────────────────────

Config Files:
 ☐ company-config.yaml
   ☐ Company name & industry
   ☐ Domain description (1-2 sentences)
   ☐ Competitor lists (tier 1, tier 2)
   ☐ Premium customers/users (if applicable)
   ☐ Core markets (primary footprint)
   ☐ Secondary markets
   ☐ Region groups (how to aggregate geographically)

 ☐ topics-taxonomy.yaml
   ☐ 6-10 industry-specific topics
   ☐ Use/avoid guidance for each
   ☐ Required keywords (domain discrimination)
   ☐ Industry keywords (context)

 ☐ macro-themes.yaml
   ☐ 4-6 macro themes relevant to company
   ☐ Signal groups (companies, keywords, topics, regions)
   ☐ Anti-keywords & gates
   ☐ Rollup rules (if theme clustering applies)

 ☐ priority-rules.yaml
   ☐ High-priority triggers (3-5)
   ☐ Medium-priority triggers (2-3)
   ☐ Low-priority triggers (optional)
   ☐ Footprint & company requirements

 ☐ region-mapping.csv
   ☐ All countries → footprint regions (100+ countries)
   ☐ Core vs secondary market flags
   ☐ Display names

 ☐ source-types.yaml
   ☐ Trusted publishers for this domain
   ☐ Ranking weights (Bloomberg = 90, etc.)

Data & Deployment:
 ☐ data/ directory (isolated per company)
 ☐ .streamlit/secrets.toml (Gemini API key)
 ☐ Streamlit page titles & branding
 ☐ Home page KPIs (customize if needed)
```

---

## 8. Example: Deploying for Semiconductor Vendor

### Step 1: Create Config

```bash
mkdir -p deployment/semicorp/config
```

### Step 2: `deployment/semicorp/config/company-config.yaml`

```yaml
company:
  name: "SemiCorp"
  industry: "Semiconductors - Fabless Design"
  domain_description: |
    Fabless semiconductor design company focusing on AI accelerators
    and edge computing chips. Primary markets: TSMC, Samsung foundries.
  
  company_name: "SemiCorp"
  company_aliases: ["Semi", "SemiCorp Inc"]
  
  competitors:
    tier_1:
      - "Qualcomm"
      - "Broadcom"
      - "NVIDIA"
      - "AMD"
      - "Intel"
    tier_2:
      - "MediaTek"
      - "Marvell"
      - "Analog Devices"
  
  premium_customers:
    - "TSMC"
    - "Samsung"
    - "Intel Foundry Services"
  
  core_markets:
    - "Taiwan"
    - "South Korea"
    - "United States"
    - "Japan"
    - "China"
  
  secondary_markets:
    - "Germany"
    - "Netherlands"
    - "Israel"
  
  region_groups:
    "Foundry Asia": ["Taiwan", "South Korea", "Japan", "China"]
    "US & Americas": ["United States", "Canada", "Mexico"]
    "Europe": ["Germany", "Netherlands", "United Kingdom"]
```

### Step 3: `deployment/semicorp/config/topics-taxonomy.yaml`

```yaml
topics:
  - name: "Chip Design & Architecture Roadmaps"
    description: "New chip architectures, instruction sets, design breakthroughs"
    use_when: "New architecture or design innovation"
    avoid_when: "Generic performance claims"
    required_keywords:
      - "architecture|instruction set|design|rdna|zen"
  
  - name: "Fab Technology & Process Nodes"
    description: "Process node rollouts (3nm, 2nm), yield improvements, new fabs"
    use_when: "Fab process or technology advancement"
    avoid_when: "General fab news without process specifics"
    required_keywords:
      - "process|node|nm|fab|wafer|yield|euv"
  
  # ... more topics
```

### Step 4: `deployment/semicorp/config/macro-themes.yaml`

```yaml
macro_themes:
  - name: "Fab Capacity Crunch"
    min_groups: 2
    signals:
      keywords:
        - r"capacity|shortage|wait.*time|backlog"
        - r"node.*crunch|overbooked|allocation"
      regions: ["core_markets"]
    region_requirements: ["core_markets"]
    rollup: "Foundry Risk"
  
  - name: "Design Win Announcements"
    min_groups: 2
    signals:
      keywords:
        - r"design.*win|customer.*win|adopt|design.*in"
      companies: ["premium_customers"]
  
  # ... more themes
```

### Step 5: Launch

```bash
CONFIG_DIR=./deployment/semicorp/config \
COMPANY_NAME="SemiCorp" \
streamlit run Home.py
```

**Result**: Same COGNITRA codebase, completely different extraction & scoring tailored to semiconductors.

---

## 9. Benefits of This Approach

| Benefit | How It Works |
|---------|------------|
| **Zero Code Changes** | Deploy for new company by swapping config/ folder |
| **Easy Onboarding** | Fill out 6 YAML files + 1 CSV; no coding required |
| **Consistent Quality** | Extraction pipeline unchanged (proven, battle-tested) |
| **Multi-Tenant** | Run N instances simultaneously, isolated data, shared code |
| **Domain Flexibility** | Supports automotive, semiconductor, pharma, energy, etc. |
| **Audit Trail** | All company-specific rules in human-readable YAML |
| **Version Control** | Git track config changes per company; rollback easily |
| **A/B Testing** | Compare scoring with different configs on same data |

---

## 10. Constraints & Considerations

### 10.1 What Stays Generic (No Change)

- **Pipeline**: PDF → extract → postprocess → store → brief (works for all)
- **LLM call structure**: Gemini structured JSON (industry-agnostic)
- **Postprocessing logic**: Priority/confidence scoring algorithm (reusable)
- **Deduplication**: Story-level dedup + publisher ranking (domain-independent)
- **Quality module**: R1-R5, B1-B5 KPIs (generic enough)
- **UI/UX**: Streamlit pages adapt to any company

### 10.2 What Becomes Configurable

- **Constants**: CANON_TOPICS, PREMIUM_OEMS, MACRO_THEME_RULES
- **Prompt**: Company context, competitor list, topic guidance, region list
- **Data storage**: Isolated per company (data/apex_mobility/ vs data/semicorp/)
- **Region mapping**: Country → footprint (industry-specific bucketing)
- **Priority rules**: Heuristics for what "matters" to this company
- **Branding**: Logo, company name, page titles

### 10.3 What's Hard to Parameterize

- **New field types**: If company needs fundamentally new extraction fields, requires schema change
- **Custom workflows**: If company needs unique pages (e.g., patent-specific review), requires new Streamlit pages
- **Domain-specific NLP**: If company needs custom NER (named entity recognition), requires new model
- **Complex calculations**: If company needs industry-specific scoring (e.g., drug approval timelines), might need domain logic

**Solution**: Keep config 80/20 rule — config handles 80% of customization; remaining 20% gets custom code/module for that company.

---

## 11. Next Steps

1. **Read AGENTS.md** for architectural guardrails (respect LLM vs computed field boundary)
2. **Create `src/config_loader.py`** with `CompanyConfig` class
3. **Extract Apex constants** → `config/company-config.yaml` (and other YAML files)
4. **Refactor constants.py** to load from config at import time
5. **Refactor model_router.py** → pass config to `extraction_prompt()`
6. **Test end-to-end** with Apex Mobility (should work identically)
7. **Create example configs** for 2-3 other industries
8. **Document deployment guide** for new customers

---

## Appendix: Config Schema Documentation

### `company-config.yaml` Structure

```yaml
company:
  name: str                           # Display name
  industry: str                       # Industry sector
  domain_description: str             # 2-3 sentence explanation
  company_name: str                   # Internal company name
  company_aliases: [str]              # Alternate names (lower-cased for matching)
  
  competitors:
    tier_1: [str]                     # Direct competitors (critical to watch)
    tier_2: [str]                     # Secondary competitors
  
  premium_customers: [str]            # Key accounts / OEMs / strategic partners
  
  core_markets: [str]                 # Primary geographic footprint
  secondary_markets: [str]            # Secondary markets (monitor)
  
  region_groups:                      # Custom geographic aggregations
    {region_name: [countries]}        # For dashboard/analytics

priority_rules:
  high_priority: [rule]               # High-priority triggers
  medium_priority: [rule]             # Medium-priority triggers

uncertainty_words: regex              # Soft/uncertain language detection
uncertainty_topics: [str]             # Topics requiring uncertainty section
```

---

**Document Version**: 1.0  
**Date**: 2026-02-23  
**Author**: COGNITRA Architecture Team  
**Status**: Ready for Implementation
