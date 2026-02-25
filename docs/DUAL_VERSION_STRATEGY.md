# Dual-Version Strategy: Keep Apex Untouched + Build Configurable

## Overview

Run **both versions in parallel**:
- **`main/`** — Current Apex Mobility system (100% unchanged)
- **`configurable/`** — New architecture (config-driven, testable)

Allows:
- Zero disruption to Apex operations
- Safe testing of new config system
- Side-by-side comparison
- Gradual migration when ready

---

## Folder Structure

```
COGNITRA/
├── main/                          ← CURRENT APEX (untouched)
│   ├── Home.py
│   ├── requirements.txt
│   ├── src/
│   │   ├── constants.py          (hardcoded for Apex)
│   │   ├── model_router.py       (Apex-specific prompt)
│   │   ├── postprocess.py        (Apex priority rules)
│   │   └── ...
│   ├── pages/
│   ├── data/
│   └── tests/
│
├── configurable/                 ← NEW SYSTEM (parallel)
│   ├── Home.py                   (tenant-agnostic)
│   ├── requirements.txt           (same deps)
│   ├── src/
│   │   ├── config_loader.py      (NEW)
│   │   ├── constants.py          (loads from config/)
│   │   ├── model_router.py       (templated prompts)
│   │   ├── postprocess.py        (config-driven rules)
│   │   └── ...
│   ├── pages/
│   ├── config/                   ← APEX CONFIG (default)
│   │   ├── company-config.yaml
│   │   ├── topics-taxonomy.yaml
│   │   ├── macro-themes.yaml
│   │   ├── priority-rules.yaml
│   │   ├── region-mapping.csv
│   │   └── source-types.yaml
│   ├── data/                     (isolated from main/)
│   ├── deployment/               (customer configs)
│   │   ├── apex_mobility/        (copy of config/)
│   │   ├── semicorp/
│   │   ├── pharma_corp/
│   │   └── ...
│   └── tests/
│
├── docs/
│   ├── REUSABILITY_STRATEGY.md   (you just read this)
│   ├── DUAL_VERSION_STRATEGY.md  (← you are here)
│   ├── MIGRATION_GUIDE.md        (← create after Phase 2)
│   └── ...
│
├── scripts/
│   ├── run_apex.sh               (run main/)
│   ├── run_configurable.sh       (run configurable/)
│   ├── compare_versions.py       (diff extraction results)
│   ├── migrate_records.py        (copy data from main→configurable)
│   └── ...
│
├── README.md                     (updated: mentions both versions)
├── CHANGELOG.md
└── requirements.txt              (top-level for both)
```

---

## Phase-by-Phase Implementation

### Phase 0: Prepare (Day 1)

**Goal**: Set up directory structure without touching `main/`

```bash
# Create new directory
mkdir -p configurable/src configurable/pages configurable/config configurable/deployment
mkdir -p configurable/data/pdfs configurable/data/briefs configurable/data/quality

# Copy structure (not main/)
# Main stays completely untouched

# Create scripts
mkdir -p scripts
```

**Files to create**: None yet in main/. Skip directly to Phase 1.

---

### Phase 1: Extract Apex Config (Week 1)

**Goal**: Parameterize Apex Mobility into YAML/CSV config files

#### 1.1 Create `configurable/src/config_loader.py`

```python
"""
Configuration loader: reads YAML/CSV and builds runtime constants.
Single source of truth for deployment-time customization.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml
import csv
import os

class CompanyConfig:
    """Load and validate company configuration."""
    
    def __init__(self, config_dir: Path):
        self.config_dir = Path(config_dir)
        if not self.config_dir.exists():
            raise ValueError(f"Config directory not found: {config_dir}")
        self._load_all()
    
    def _load_all(self) -> None:
        """Load all config files at startup."""
        self.company = self._load_yaml("company-config.yaml")
        self.topics = self._load_yaml("topics-taxonomy.yaml")
        self.macro_themes = self._load_yaml("macro-themes.yaml")
        self.priority_rules = self._load_yaml("priority-rules.yaml")
        self.region_mapping = self._load_csv("region-mapping.csv")
        self.source_types = self._load_yaml("source-types.yaml")
        
        # Compute derived constants
        self.COMPANY_NAME = self.company.get("company", {}).get("name", "Unknown")
        self.INDUSTRY = self.company.get("company", {}).get("industry", "")
        self.COMPETITORS_FLAT = self._flatten_competitors()
        self.PREMIUM_CUSTOMERS = self._get_premium_customers()
        self.CORE_MARKETS = self._get_core_markets()
        self.SECONDARY_MARKETS = self._get_secondary_markets()
        self.CANONICAL_TOPICS = [t["name"] for t in self.topics.get("topics", [])]
        self.COUNTRY_TO_FOOTPRINT = self._build_country_mapping()
        self.FOOTPRINT_REGIONS = self._extract_footprint_regions()
    
    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        """Load YAML config file."""
        path = self.config_dir / filename
        if not path.exists():
            print(f"Warning: {filename} not found in {self.config_dir}. Using empty config.")
            return {}
        try:
            with open(path, encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Error loading {filename}: {e}")
            return {}
    
    def _load_csv(self, filename: str) -> List[Dict[str, str]]:
        """Load CSV config file."""
        path = self.config_dir / filename
        if not path.exists():
            print(f"Warning: {filename} not found in {self.config_dir}. Using empty list.")
            return []
        try:
            rows = []
            with open(path, encoding='utf-8') as f:
                reader = csv.DictReader(f)
                rows.extend(reader or [])
            return rows
        except Exception as e:
            print(f"Error loading {filename}: {e}")
            return []
    
    def _flatten_competitors(self) -> set:
        """Flatten tier_1 + tier_2 competitors into single set."""
        competitors_config = self.company.get("company", {}).get("competitors", {})
        flat = set()
        for tier in ["tier_1", "tier_2"]:
            companies = competitors_config.get(tier, [])
            if isinstance(companies, list):
                flat.update(c.lower() if isinstance(c, str) else c for c in companies)
        return flat
    
    def _get_premium_customers(self) -> set:
        """Get premium customer list."""
        customers = self.company.get("company", {}).get("premium_customers", [])
        return set(c.lower() if isinstance(c, str) else c for c in customers)
    
    def _get_core_markets(self) -> set:
        """Get core market list."""
        markets = self.company.get("company", {}).get("core_markets", [])
        return set(markets)
    
    def _get_secondary_markets(self) -> set:
        """Get secondary market list."""
        markets = self.company.get("company", {}).get("secondary_markets", [])
        return set(markets)
    
    def _build_country_mapping(self) -> Dict[str, str]:
        """Build country → footprint region mapping from CSV."""
        mapping = {}
        for row in self.region_mapping:
            country = row.get("country", "").strip()
            footprint = row.get("footprint_region", "").strip()
            if country and footprint:
                mapping[country] = footprint
        
        # Fallback for unmapped countries
        if not mapping:
            mapping = {"default": "Rest of World"}
        
        return mapping
    
    def _extract_footprint_regions(self) -> set:
        """Extract unique footprint regions from mapping."""
        regions = set(self.COUNTRY_TO_FOOTPRINT.values())
        return regions


def load_runtime_config(config_dir: Optional[Path] = None) -> CompanyConfig:
    """
    Load config from given directory (or env var CONFIG_DIR).
    """
    if config_dir is None:
        config_dir = os.getenv("CONFIG_DIR")
    
    if config_dir is None:
        # Default: look for config/ next to this script
        config_dir = Path(__file__).parents[2] / "configurable" / "config"
    
    config_dir = Path(config_dir)
    return CompanyConfig(config_dir)

# Load at module import time for backward compatibility
_INSTANCE = None

def get_config() -> CompanyConfig:
    """Get singleton config instance."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = load_runtime_config()
    return _INSTANCE
```

#### 1.2 Create `configurable/config/company-config.yaml`

Extract from current `src/constants.py`:

```yaml
company:
  name: "Apex Mobility"
  industry: "Automotive - Closure Systems"
  domain_description: |
    Automotive closure systems supplier specializing in door latches,
    strikers, handles, smart entry, and cinch systems.
  
  company_name: "Apex Mobility"
  company_aliases: ["Apex"]
  
  competitors:
    tier_1:
      - "Hi-Lex"
      - "Aisin"
      - "Brose"
      - "Huf"
      - "Magna"
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
  
  core_markets:
    - "United States"
    - "Germany"
    - "France"
    - "Czech Republic"
    - "Mexico"
    - "China"
    - "Japan"
  
  secondary_markets:
    - "United Kingdom"
    - "Spain"
    - "Italy"
    - "India"
    - "Thailand"
    - "South Korea"

priority_rules:
  high_priority:
    - pattern: "oem|strategy|shift|sourcing"
      footprint_required: true
      boost: 2
    - pattern: "competitor.*win|contract|supply"
      regions: ["core_markets"]
      boost: 1
  
  medium_priority:
    - pattern: "market|demand"
      regions: ["secondary_markets"]
      boost: 0

uncertainty_words: |
  \b(forecast|could|weighing|sources said|expected|may|might|
  uncertain|preliminary|unconfirmed|estimated|projected|reportedly|
  reconsider|reviewing|speculation)\b

uncertainty_topics: []
```

#### 1.3 Create `configurable/config/topics-taxonomy.yaml`

Extract from current `src/constants.py` + prompt guidance:

```yaml
topics:
  - name: "OEM Strategy & Powertrain Shifts"
    description: "Broad OEM strategic pivots (BEV/ICE mix, vertical integration, platform resets, localization)"
    use_when: "Strategic pivot or market reposition"
    avoid_when: "Single program update"
    industry_keywords:
      - "oem"
      - "strategy"
      - "shift"
      - "pivot"
      - "powertrain"
      - "bev"
      - "ice"
      - "electric"
      - "platform"
  
  - name: "Closure Technology & Innovation"
    description: "Product innovation in door latches, handles, smart entry, cinch systems"
    use_when: "Explicit mention of closure systems"
    avoid_when: "General vehicle electronics"
    required_keywords:
      - "latch"
      - "door"
      - "handle"
      - "digital key"
      - "smart entry"
      - "cinch"
    industry_keywords:
      - "mechanism"
      - "actuator"
      - "electronics"
      - "software"
  
  - name: "OEM Programs & Vehicle Platforms"
    description: "Specific program announcements (launches, refreshes, sourcing)"
    use_when: "Program/platform launch or sourcing decision"
    avoid_when: "Broad strategy narratives"
    industry_keywords:
      - "program"
      - "platform"
      - "model"
      - "launch"
      - "refresh"
      - "generation"
  
  - name: "Regulatory & Safety"
    description: "Regulations, standards, recalls, cybersecurity"
    use_when: "Regulatory or safety news"
    avoid_when: "General political news"
    industry_keywords:
      - "regulation"
      - "standard"
      - "recall"
      - "cybersecurity"
      - "nhtsa"
      - "epa"
  
  - name: "Supply Chain & Manufacturing"
    description: "Plant changes, disruptions, logistics, labor, tariffs"
    use_when: "Manufacturing or supply news"
    avoid_when: "Pure financial performance"
    industry_keywords:
      - "supply"
      - "manufacturing"
      - "plant"
      - "factory"
      - "production"
      - "disruption"
      - "logistics"
  
  - name: "Technology Partnerships & Components"
    description: "Partnerships and component sourcing"
    use_when: "Tech partnership or sourcing"
    avoid_when: "Purely commercial alliances"
    industry_keywords:
      - "partnership"
      - "technology"
      - "component"
      - "chip"
      - "sensor"
      - "connectivity"
  
  - name: "Market & Competition"
    description: "Demand, registrations, pricing, share shifts"
    use_when: "Market or competitive news"
    avoid_when: "Internal exec changes"
    industry_keywords:
      - "market"
      - "competition"
      - "demand"
      - "registrations"
      - "pricing"
      - "share"
  
  - name: "Financial & Business Performance"
    description: "Earnings, guidance, M&A, restructurings"
    use_when: "Financial or business news"
    avoid_when: "Exec churn without financial angle"
    industry_keywords:
      - "earnings"
      - "revenue"
      - "profit"
      - "guidance"
      - "acquisition"
      - "merger"
      - "restructuring"
      - "ipo"
  
  - name: "Executive & Organizational"
    description: "Leadership changes, governance, org restructuring"
    use_when: "Leadership or governance news"
    avoid_when: "M&A purely as transaction"
    industry_keywords:
      - "executive"
      - "ceo"
      - "leadership"
      - "cfo"
      - "cto"
      - "governance"
      - "board"
```

#### 1.4 Create `configurable/config/macro-themes.yaml`

Extract from current `src/constants.py`:

```yaml
macro_themes:
  - name: "Luxury OEM Stress"
    min_groups: 2
    signals:
      companies: ["premium_customers"]
      keywords:
        - r"margin"
        - r"profit\s*warn"
        - r"cost\s*cut"
        - r"restructur"
        - r"sales\s*declin"
        - r"downturn"
        - r"layoff"
        - r"headcount"
        - r"earnings\s*miss"
        - r"revenue\s*drop"
    anti_keywords:
      - r"record\s*profit"
      - r"sales\s*surge"
      - r"beat\s*expect"
    requires_gate:
      premium_customers: true
    rollup: "Premium OEM Financial/Strategy Stress"
  
  - name: "China EV Competitive Acceleration"
    min_groups: 2
    signals:
      companies:
        - "byd"
        - "nio"
        - "xpeng"
        - "li auto"
        - "geely"
        - "chery"
        - "great wall"
        - "saic"
        - "changan"
      keywords:
        - r"price\s*war"
        - r"ev\s*export"
        - r"electric\s*vehicle"
        - r"\bev\b"
        - r"\bnev\b"
        - r"battery\s*cost"
        - r"competition"
        - r"market\s*share"
      regions:
        - "China"
        - "South Asia"
    anti_keywords:
      - r"ev\s*sales\s*stall"
      - r"ev\s*slow"
    region_requirements:
      - "China"
  
  # ... more themes
```

#### 1.5 Create `configurable/config/region-mapping.csv`

Extract from current `data/new_country_mapping.csv`:

```csv
country,continent,footprint_region,core_market,secondary_market,display_name
Czech Republic,Europe,Czech Republic,YES,,Czech Republic
France,Europe,France,YES,,France
Germany,Europe,Germany,YES,,Germany
Italy,Europe,Italy,,YES,Italy
Morocco,Africa,Morocco,YES,,Morocco
Mexico,North America,Mexico,YES,,Mexico
Portugal,Europe,Portugal,,YES,Portugal
Russia,Europe,Russia,YES,,Russia
Spain,Europe,Spain,,YES,Spain
Sweden,Europe,Sweden,,YES,Sweden
United Kingdom,Europe,United Kingdom,,YES,United Kingdom
United States,North America,United States,YES,,United States
Thailand,Asia,Thailand,,YES,Thailand
India,Asia,India,,YES,India
China,Asia,China,YES,,China
Taiwan,Asia,Taiwan,,YES,Taiwan
Japan,Asia,Japan,,YES,Japan
South Korea,Asia,South Korea,,YES,South Korea
# ... expand with all ~90 countries
```

#### 1.6 Create `configurable/config/source-types.yaml`

```yaml
source_types:
  - name: "Bloomberg"
    ranking_weight: 90
  - name: "Reuters"
    ranking_weight: 80
  - name: "Financial News"
    ranking_weight: 78
  - name: "MarkLines"
    ranking_weight: 76
  - name: "Automotive News"
    ranking_weight: 75
  - name: "Industry Publication"
    ranking_weight: 72
  - name: "Press Release"
    ranking_weight: 60
  - name: "Patent"
    ranking_weight: 55
  - name: "Other"
    ranking_weight: 50
```

---

### Phase 1.5: Update `configurable/src/constants.py`

Copy from `main/src/constants.py` but load from config:

```python
"""
Runtime constants loaded from configurable/config/ directory.
Default: Apex Mobility; swap CONFIG_DIR env var to deploy for other companies.
"""

from src.config_loader import get_config

# Load config at module import time
_CONFIG = get_config()

# Export module-level constants (backward compatible with main/)
COMPANY_NAME = _CONFIG.COMPANY_NAME
INDUSTRY = _CONFIG.INDUSTRY
COMPETITORS = _CONFIG.COMPETITORS_FLAT
PREMIUM_OEMS = _CONFIG.PREMIUM_CUSTOMERS  # Alias for backward compat
CANON_TOPICS = _CONFIG.CANONICAL_TOPICS
MACRO_THEME_RULES = [t for t in _CONFIG.macro_themes.get("macro_themes", [])]
FOOTPRINT_REGIONS = list(_CONFIG.FOOTPRINT_REGIONS)
DISPLAY_REGIONS = FOOTPRINT_REGIONS
FOOTPRINT_TO_DISPLAY = {}  # Identity mapping
COUNTRY_TO_FOOTPRINT = _CONFIG.COUNTRY_TO_FOOTPRINT

# ... rest stays the same as main/
ALLOWED_SOURCE_TYPES = {"Bloomberg", "Automotive News", "Reuters", "Patent", ...}
ALLOWED_ACTOR_TYPES = {"oem", "supplier", "technology", "industry", "other"}
# etc.
```

---

### Phase 2: Refactor Key Modules (Week 2)

#### 2.1 Copy + Minimize Changes to `configurable/src/model_router.py`

Change **only** the `extraction_prompt()` function to use config:

```python
def extraction_prompt(context_pack: str) -> str:
    """Build extraction prompt from config (no hardcoding)."""
    from src.config_loader import get_config
    config = get_config()
    
    company_name = config.COMPANY_NAME
    industry = config.INDUSTRY
    domain_desc = config.company.get("company", {}).get("domain_description", "")
    
    # Build competitor block from config
    competitors_text = _format_competitors_block(config)
    
    # Build topic guidance from config
    topic_guidance = _format_topic_guidance(config)
    
    # Build region list from config
    region_list = _format_region_list(config)
    
    return (
        f"You are extracting structured intelligence for {company_name}, "
        f"a {industry} entity. {domain_desc} "
        f"Return JSON only matching the schema. Follow these rules strictly:\n\n"
        # ... standard rules (unchanged) ...
        f"\nCOMPETITORS — set actor_type='supplier' for these companies:\n"
        f"{competitors_text}\n"
        f"\n{topic_guidance}\n"
        f"\n{region_list}\n"
        # ... rest of prompt ...
        f"\nINPUT (context pack):\n{context_pack}"
    )


def _format_competitors_block(config) -> str:
    """Format competitors block from config."""
    competitors = config.company.get("company", {}).get("competitors", {})
    lines = []
    
    tier_1 = competitors.get("tier_1", [])
    if tier_1:
        lines.append(f"Tier 1: {', '.join(tier_1)}")
    
    tier_2 = competitors.get("tier_2", [])
    if tier_2:
        lines.append(f"Tier 2: {', '.join(tier_2)}")
    
    our_company = config.company.get("company", {}).get("company_name", "Our Company")
    lines.append(f"Our company: {our_company}")
    
    return "\n".join(lines)


def _format_topic_guidance(config) -> str:
    """Format topic classification guidance from config."""
    topics = config.topics.get("topics", [])
    lines = ["TOPIC CLASSIFICATION — pick 1-4 topics using these rules:"]
    
    for topic in topics:
        name = topic.get("name", "")
        description = topic.get("description", "")
        use_when = topic.get("use_when", "")
        avoid_when = topic.get("avoid_when", "")
        
        lines.append(f"- '{name}': {description}. Use: {use_when}. Avoid: {avoid_when}.")
    
    return "\n".join(lines)


def _format_region_list(config) -> str:
    """Format region list from config."""
    regions = sorted(config.FOOTPRINT_REGIONS)
    return f"Valid regions: {', '.join(regions)}"
```

#### 2.2 Minimal Change to `configurable/src/postprocess.py`

Just update `_boost_priority()` to use config:

```python
def _boost_priority(rec: Dict) -> Optional[str]:
    """Boost priority based on config-driven rules."""
    from src.config_loader import get_config
    config = get_config()
    
    macro_themes = rec.get("macro_themes_detected", [])
    regions = rec.get("regions_relevant_to_apex_mobility", [])
    core_markets = config.CORE_MARKETS
    
    # Apply config-based priority rules
    priority_rules = config.priority_rules.get("high_priority", [])
    
    for rule in priority_rules:
        pattern = rule.get("pattern", "")
        footprint_req = rule.get("footprint_required", False)
        boost = rule.get("boost", 0)
        
        # Check if macro theme matches pattern
        theme_match = any(
            re.search(pattern, theme, re.IGNORECASE)
            for theme in macro_themes
        )
        
        if theme_match:
            if footprint_req and not any(r in core_markets for r in regions):
                continue  # Skip if footprint required but not met
            
            return "High" if boost >= 2 else "Medium"
    
    return None
```

---

### Phase 3: Create Launch Scripts (Day 1 of Week 3)

#### 3.1 `scripts/run_apex.sh` (Windows: `run_apex.bat`)

```bash
#!/bin/bash
# Launch APEX MOBILITY (original system — untouched)

echo "🟢 Starting COGNITRA — Apex Mobility (main/ directory)"
cd main/
streamlit run Home.py --logger.level=info

# Cleanup
cd ..
```

**Windows version** (`scripts/run_apex.bat`):
```batch
@echo off
REM Launch APEX MOBILITY (original system — untouched)

echo 🟢 Starting COGNITRA - Apex Mobility (main/ directory)
cd main
streamlit run Home.py --logger.level=info

REM Cleanup
cd ..
```

#### 3.2 `scripts/run_configurable.sh` (Windows: `run_configurable.bat`)

```bash
#!/bin/bash
# Launch CONFIGURABLE SYSTEM (new arch — any company)

CONFIG_DIR="${1:-.}/configurable/config"
COMPANY_NAME="${2:-Apex Mobility}"

echo "🔵 Starting COGNITRA — Configurable System"
echo "   Company: $COMPANY_NAME"
echo "   Config: $CONFIG_DIR"

export CONFIG_DIR
export COMPANY_NAME

cd configurable/
streamlit run Home.py --logger.level=info

cd ..
```

**Windows version** (`scripts/run_configurable.bat`):
```batch
@echo off
REM Launch CONFIGURABLE SYSTEM (new arch — any company)

setlocal enabledelayedexpansion
if "%~1"=="" (
    set CONFIG_DIR=%CD%\configurable\config
) else (
    set CONFIG_DIR=%1
)

if "%~2"=="" (
    set COMPANY_NAME=Apex Mobility
) else (
    set COMPANY_NAME=%2
)

echo 🔵 Starting COGNITRA - Configurable System
echo    Company: !COMPANY_NAME!
echo    Config: !CONFIG_DIR!

set CONFIG_DIR=!CONFIG_DIR!
set COMPANY_NAME=!COMPANY_NAME!

cd configurable
streamlit run Home.py --logger.level=info

cd ..
```

#### 3.3 `scripts/run_tenant.sh` (Multi-tenant launcher)

```bash
#!/bin/bash
# Launch configurable system for ANY tenant

TENANT="${1:-apex_mobility}"
CONFIG_DIR="./configurable/deployment/$TENANT/config"

if [ ! -d "$CONFIG_DIR" ]; then
    echo "❌ Tenant not found: $TENANT"
    echo "   Available tenants:"
    ls -d configurable/deployment/*/config 2>/dev/null | sed 's|configurable/deployment/||; s|/config||' | sed 's/^/     /'
    exit 1
fi

echo "🔷 Starting COGNITRA — $TENANT"
export CONFIG_DIR
cd configurable/
streamlit run Home.py
cd ..
```

---

### Phase 4: Create Apex Config in `configurable/deployment/` (Day 2 of Week 3)

```bash
# Copy Apex config as a deployment template
mkdir -p configurable/deployment/apex_mobility/config

cp configurable/config/* configurable/deployment/apex_mobility/config/

# Data isolation
mkdir -p configurable/deployment/apex_mobility/data/pdfs
mkdir -p configurable/deployment/apex_mobility/data/briefs
mkdir -p configurable/deployment/apex_mobility/data/quality
```

Now deployment looks like:

```
configurable/deployment/
├── apex_mobility/          ← Default Apex (same as configurable/config)
│   ├── config/
│   └── data/
├── semicorp/               ← Ready for semiconductor vendor
│   ├── config/
│   └── data/
├── pharma_corp/            ← Ready for pharma
│   ├── config/
│   └── data/
└── ...
```

---

### Phase 5: Comparison & Testing (Week 3-4)

#### 5.1 Create `scripts/compare_versions.py`

```python
"""
Run the same PDF through both versions and compare extractions.
Useful for validating configurable system matches main/.
"""

import json
import subprocess
import sys
from pathlib import Path
import tempfile

def extract_via_main(pdf_path: str) -> dict:
    """Extract via main/ version."""
    # Simulate extraction (would call API)
    print(f"📄 Extracting via main/ (Apex Mobility)...")
    # ... call main version ...
    pass

def extract_via_configurable(pdf_path: str, config_dir: str) -> dict:
    """Extract via configurable/ version."""
    print(f"📄 Extracting via configurable/ ({config_dir})...")
    # ... call configurable version ...
    pass

def compare(rec1: dict, rec2: dict) -> dict:
    """Compare two records."""
    diffs = {}
    
    fields_to_check = [
        "title", "topics", "companies_mentioned", "priority", "confidence",
        "macro_themes_detected"
    ]
    
    for field in fields_to_check:
        v1 = rec1.get(field)
        v2 = rec2.get(field)
        
        if v1 != v2:
            diffs[field] = {
                "main": v1,
                "configurable": v2,
                "match": False
            }
    
    return diffs

if __name__ == "__main__":
    pdf_path = sys.argv[1]
    
    rec_main = extract_via_main(pdf_path)
    rec_config = extract_via_configurable(pdf_path, "./configurable/config")
    
    diffs = compare(rec_main, rec_config)
    
    if not diffs:
        print("✅ Records match perfectly!")
    else:
        print(f"⚠️  Found {len(diffs)} differences:")
        for field, diff in diffs.items():
            print(f"\n  {field}:")
            print(f"    main:         {diff['main']}")
            print(f"    configurable: {diff['configurable']}")
```

#### 5.2 Create `scripts/validate_configs.py`

```python
"""
Validate all config files in deployment/ directory.
Checks YAML syntax, required fields, consistency.
"""

import yaml
from pathlib import Path

def validate_company_config(config_path: Path) -> list:
    """Validate company-config.yaml."""
    errors = []
    
    try:
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
    except Exception as e:
        return [f"Invalid YAML: {e}"]
    
    # Check required fields
    required = ["company"]
    company = cfg.get("company", {})
    
    required_company_fields = ["name", "industry", "competitors", "core_markets"]
    for field in required_company_fields:
        if field not in company:
            errors.append(f"Missing: company.{field}")
    
    return errors

def validate_all_tenants():
    """Validate all tenant configs."""
    deployment_dir = Path("configurable/deployment")
    
    for tenant_dir in deployment_dir.iterdir():
        if not tenant_dir.is_dir():
            continue
        
        config_dir = tenant_dir / "config"
        if not config_dir.exists():
            print(f"⚠️  {tenant_dir.name}: no config/ directory")
            continue
        
        print(f"\n📋 Validating {tenant_dir.name}...")
        
        errors = validate_company_config(config_dir / "company-config.yaml")
        
        if errors:
            print(f"  ❌ Errors found:")
            for err in errors:
                print(f"     - {err}")
        else:
            print(f"  ✅ Config valid")

if __name__ == "__main__":
    validate_all_tenants()
```

---

### Phase 6: Documentation (Week 4)

#### 6.1 Create `docs/MIGRATION_GUIDE.md`

```markdown
# Migration Guide: main/ → configurable/

When to migrate from Apex Mobility (main/) to Configurable Arch (configurable/):

1. **Validation Phase** (Weeks 1-2)
   - Run both side-by-side
   - Compare extrac results on sample PDFs
   - Verify priority/confidence scoring matches

2. **Data Migration** (Week 3)
   - Copy records.jsonl from main/data → configurable/data
   - Verify all records load correctly
   - Re-run quality checks

3. **Cutover** (Week 4)
   - Deploy configurable/ to production
   - Monitor for 1 week
   - Archive main/ (don't delete)

4. **Post-Cutover** (Week 5+)
   - Retire main/ (keep in git history)
   - Onboard new customers via deployment/
```

#### 6.2 Update `README.md`

Add section:

```markdown
## Dual-Version Architecture

COGNITRA runs in **two modes**:

### `main/` — Apex Mobility (Current Production)
- Hardcoded for Apex Mobility closure systems
- Fully tested, zero changes
- Legacy operation mode

### `configurable/` — Generalized Multi-Tenant (New)
- Config-driven (YAML/CSV)
- Same extraction/scoring pipeline
- Ready for other companies/industries

### Running

```bash
# Run Apex Mobility (main/)
./scripts/run_apex.sh

# Run configurable with Apex config (same as main but configurable)
./scripts/run_configurable.sh

# Run configurable for SemiCorp
./scripts/run_tenant.sh semicorp
```
```

---

## Key Principles

### ✅ Do This

```
✅ Keep main/ 100% untouched
   - No file changes
   - No import changes
   - No constants modifications

✅ Parallel development
   - main/ remains stable
   - configurable/ in development
   - Both can run simultaneously

✅ Gradual cutover
   - Validate configurable for weeks
   - Compare results with main/
   - Flip switch when confident

✅ Archive history
   - Keep main/ in git forever
   - Proves one version → other
```

### ❌ Don't Do This

```
❌ Don't modify main/
   - Any change risks Apex operations
   - Force config changes to configurable/ only

❌ Don't data-share
   - Keep data/main/ and data/configurable/ separate
   - Avoid accidental data loss

❌ Don't rush cutover
   - Validate for minimum 2 weeks
   - Get stakeholder sign-off
```

---

## Directory Summary

```
COGNITRA/
├── main/                           ← APEX (ZIP & ARCHIVE if migrating)
│   ├── Home.py                     (untouched)
│   ├── src/constants.py            (hardcoded)
│   ├── data/records.jsonl          (Apex records)
│   └── ...
│
├── configurable/                   ← NEW (in development)
│   ├── Home.py                     (generic)
│   ├── src/
│   │   ├── config_loader.py        (NEW)
│   │   ├── constants.py            (loads from config/)
│   │   └── ...
│   ├── config/                     (Apex config — default)
│   ├── data/                       (isolated)
│   ├── deployment/
│   │   ├── apex_mobility/          (Apex as tenant)
│   │   ├── semicorp/               (future customer)
│   │   └── ...
│   └── ...
│
├── scripts/
│   ├── run_apex.sh                 (launch main/)
│   ├── run_configurable.sh         (launch configurable/)
│   ├── run_tenant.sh               (launch any tenant)
│   ├── compare_versions.py         (validate parity)
│   └── validate_configs.py         (validate YAML)
│
└── docs/
    ├── REUSABILITY_STRATEGY.md
    ├── DUAL_VERSION_STRATEGY.md
    ├── MIGRATION_GUIDE.md
    └── ...
```

---

## Timeline

| Week | Phase | Deliverable |
|------|-------|------------|
| 1 | Config Extraction | Apex YAML/CSV config files |
| 2 | Module Refactoring | configurable/src/ with minimal changes |
| 3 | Testing & Scripts | Comparison & validation scripts |
| 4 | Documentation | Migration guide + examples |
| 5+ | Validation & Cutover | A/B testing, stakeholder sign-off, migration |

---

## Success Criteria

✅ main/ runs identically (zero changes)  
✅ configurable/ produces identical extractions for same PDFs  
✅ Both versions can run simultaneously without conflict  
✅ Configuration files are human-readable YAML/CSV  
✅ Easy to spin up new tenant (copy deployment/apex_mobility → deployment/new_company)  
✅ Confidence to migrate within 4 weeks  

---

**Author**: Generated Feb 23, 2026  
**Status**: Ready to implement Phase 0-1
