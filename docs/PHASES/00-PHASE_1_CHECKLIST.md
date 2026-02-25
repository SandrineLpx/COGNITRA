# Phase 1 Checklist: Extract Apex Config

**Timeline**: ~1 day  
**Output**: 6 YAML/CSV config files in `configurable/config/`  
**Source**: Extract from `src/constants.py`, `src/model_router.py`, `src/postprocess.py`, `data/new_country_mapping.csv`

---

## File 1: `configurable/config/company-config.yaml`

**Source**: `src/constants.py` lines 100-247

**Extract these hardcoded values**:
```python
# Lines to extract:
PREMIUM_OEMS = { "bmw", "mercedes-benz", ... }
MACRO_THEME_RULES = [...]  # Check "premium_company_gate": True gates
FOOTPRINT_REGIONS = [...]  # Countries & regions
ALLOWED_SOURCE_TYPES = {...}
```

**What to create**:
```yaml
company:
  name: "Apex Mobility"
  industry: "Automotive - Closure Systems"
  domain_description: |
    (copy from AGENTS.md Introduction section)
  company_name: "Apex Mobility"
  company_aliases: ["Apex"]
  competitors:
    tier_1: ["Hi-Lex", "Aisin", "Brose", "Huf", "Magna", "Inteva", "Mitsui Kinzoku"]
    tier_2: ["Ushin", "Witte", "Mitsuba", "Fudi", "PHA", "Cebi", "Tri-Circle"]
  premium_customers: (copy from PREMIUM_OEMS list)
  core_markets: ["United States", "Germany", "France", "Czech Republic", "Mexico", "China", "Japan"]
  secondary_markets: ["United Kingdom", "Spain", "Italy", "India", "Thailand", "South Korea"]
```

**Effort**: 30 min (straightforward copy-paste)

---

## File 2: `configurable/config/topics-taxonomy.yaml`

**Source**: 
- `src/constants.py` lines 1-48 (CANON_TOPICS)
- `src/model_router.py` lines 335-375 (topic guidance in prompt)

**Extract**:
```python
CANON_TOPICS = [
    "OEM Strategy & Powertrain Shifts",           # ← Extract each
    "Closure Technology & Innovation",
    # ... etc
]

# From extraction_prompt(): "TOPIC CLASSIFICATION — pick 1-4 topics..."
# Guidance text: "Use: broad OEM pivots (BEV/ICE mix...)" etc
```

**What to create**:
```yaml
topics:
  - name: "OEM Strategy & Powertrain Shifts"
    description: "Broad OEM strategic pivots (BEV/ICE mix, vertical integration, platform resets, localization)"
    use_when: "Strategic pivot or market reposition"
    avoid_when: "Single program update"
    industry_keywords: [...]
  # ... repeat for all 9 topics
```

**Effort**: 45 min (read prompt, extract guidance, format YAML)

---

## File 3: `configurable/config/macro-themes.yaml`

**Source**: `src/constants.py` lines 110-220 (MACRO_THEME_RULES)

**Extract**:
```python
MACRO_THEME_RULES = [
    {
        "name": "Luxury OEM Stress",
        "min_groups": 2,
        "signals": { ... },
        "anti_keywords": [ ... ],
        "premium_company_gate": True,
        "rollup": "Premium OEM Financial/Strategy Stress",
    },
    # ... repeat for all 6 themes
]
```

**What to create**:
```yaml
macro_themes:
  - name: "Luxury OEM Stress"
    min_groups: 2
    signals:
      companies: ["premium_customers"]  # Reference config.company.premium_customers
      keywords: [r"margin", r"profit\s*warn", ...]
    anti_keywords: [r"record\s*profit", ...]
    requires_gate:
      premium_customers: true
    rollup: "Premium OEM Financial/Strategy Stress"
  # ... repeat for all 6 themes
```

**Effort**: 30 min (direct copy from constants.py)

---

## File 4: `configurable/config/priority-rules.yaml`

**Source**: `src/postprocess.py` lines 400-450 (function `_boost_priority()`)

**Extract the priority boost logic**:
```python
def _boost_priority(rec: Dict) -> Optional[str]:
    macro_themes = rec.get("macro_themes_detected", [])
    regions = rec.get("regions_relevant_to_apex_mobility", [])
    
    # Extract these rules:
    if "Tariff & Trade Disruption" in macro_themes:
        if any(r in [...Apex footprint...]):
            priority = "High"
    # ... more rules
```

**What to create**:
```yaml
priority_rules:
  high_priority:
    - pattern: "tariff|trade.*war"
      regions: ["core_markets"]
      boost: 2
    - pattern: "competitor.*win|supply.*disrupt"
      regions: ["core_markets"]
      boost: 1
  
  medium_priority:
    - pattern: "market|demand|share"
      regions: ["secondary_markets"]
      boost: 0
```

**Effort**: 30 min (decode _boost_priority logic)

---

## File 5: `configurable/config/region-mapping.csv`

**Source**: Simply copy `data/new_country_mapping.csv`

**What to do**:
```bash
cp data/new_country_mapping.csv configurable/config/region-mapping.csv
```

**Modify headers** (if needed):
- Ensure columns: `country`, `footprint_region`, `core_market`, `secondary_market`, `display_name`
- Add boolean flags for marketing priority

**Effort**: 15 min (copy + verify headers)

---

## File 6: `configurable/config/source-types.yaml`

**Source**: `src/constants.py` + `src/dedupe.py` (ALLOWED_SOURCE_TYPES, PUBLISHER_SCORE)

**Extract**:
```python
ALLOWED_SOURCE_TYPES = {
    "Bloomberg", "Automotive News", "Reuters", "Patent", "Press Release",
    "S&P", "MarkLines", "Financial News", "GlobalData", "Industry Publication", "Other"
}

# From src/dedupe.py:
PUBLISHER_SCORE = {
    "S&P": 100,
    "Bloomberg": 90,
    "Reuters": 80,
    # ...
}
```

**What to create**:
```yaml
source_types:
  - name: "Bloomberg"
    ranking_weight: 90
  - name: "Reuters"
    ranking_weight: 80
  - name: "Financial News"
    ranking_weight: 78
  # ... etc
```

**Effort**: 15 min (simple mapping)

---

## Summary Checklist

```
PHASE 1 EXTRACTION CHECKLIST
─────────────────────────────

File 1: company-config.yaml        ☐ Extract from constants.py (30 min)
File 2: topics-taxonomy.yaml       ☐ Extract from constants.py + model_router.py (45 min)
File 3: macro-themes.yaml          ☐ Extract from constants.py (30 min)
File 4: priority-rules.yaml        ☐ Extract from postprocess.py (30 min)
File 5: region-mapping.csv         ☐ Copy from data/ (15 min)
File 6: source-types.yaml          ☐ Extract from constants.py + dedupe.py (15 min)

Verification:                      ☐ Test YAML syntax (yaml lint)
                                   ☐ Verify all values present
                                   ☐ Compare with hardcoded originals

Total Time: ~2.5 hours
```

---

## How to Proceed

1. **Open each source file** in the IDE
2. **Find the lines to extract** (use Ctrl+F to search)
3. **Create corresponding YAML/CSV file** in `configurable/config/`
4. **Validate syntax** (YAML linter, or simple Python `yaml.safe_load()`)
5. **Compare with originals** (make sure nothing is lost)

---

## Validation Script (Optional)

After creating all 6 files, run this to validate:

```python
# scripts/validate_phase1.py
import yaml
from pathlib import Path

config_dir = Path("configurable/config")

files = [
    "company-config.yaml",
    "topics-taxonomy.yaml",
    "macro-themes.yaml",
    "priority-rules.yaml",
    "region-mapping.csv",
    "source-types.yaml",
]

for filename in files:
    path = config_dir / filename
    if not path.exists():
        print(f"❌ {filename} NOT FOUND")
    else:
        print(f"✅ {filename} exists")
        # Try to parse YAML (skip CSV)
        if filename.endswith(".yaml"):
            try:
                with open(path) as f:
                    data = yaml.safe_load(f)
                print(f"   ✅ Valid YAML")
            except Exception as e:
                print(f"   ❌ Invalid YAML: {e}")
```

---

**Next Step**: When Phase 1 files are ready, move to Phase 2 (create `config_loader.py`)

**Questions?**: Refer to [`docs/REUSABILITY_STRATEGY.md`](#section-2) and [`docs/DUAL_VERSION_STRATEGY.md`](#phase-1-extract-apex-config) for templates.
