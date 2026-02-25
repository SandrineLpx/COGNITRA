# Folder Structure Tree - Phase 0 Complete

**Generated**: 2026-02-23  
**Status**: ✅ All directories created, ready for Phase 1

---

## Visual Folder Tree

```
COGNITRA/
│
├── configurable/                   ← NEW (parallel system, local only)
│   ├── README.md                   ← Phase guide
│   ├── src/                        ← Python module
│   │   └── __init__.py             ← Package marker
│   ├── pages/                      ← Streamlit pages (empty, copy in Phase 2)
│   ├── config/                     ← Config files (empty, Phase 1)
│   │   ├── company-config.yaml     (to be created)
│   │   ├── topics-taxonomy.yaml    (to be created)
│   │   ├── macro-themes.yaml       (to be created)
│   │   ├── priority-rules.yaml     (to be created)
│   │   ├── region-mapping.csv      (to be created)
│   │   └── source-types.yaml       (to be created)
│   ├── data/                       ← Runtime storage (isolated)
│   │   ├── pdfs/
│   │   ├── briefs/
│   │   └── quality/
│   ├── deployment/                 ← Multi-tenant templates
│   │   └── apex_mobility/          ← Apex as first tenant
│   │       ├── config/             ← Apex config copy (Phase 1)
│   │       │   ├── company-config.yaml (to be created)
│   │       │   ├── topics-taxonomy.yaml (to be created)
│   │       │   ├── macro-themes.yaml (to be created)
│   │       │   ├── priority-rules.yaml (to be created)
│   │       │   ├── region-mapping.csv (to be created)
│   │       │   └── source-types.yaml (to be created)
│   │       └── data/               ← Tenant-isolated storage
│   │           ├── pdfs/
│   │           ├── briefs/
│   │           └── quality/
│   └── tests/                      ← Tests (Phase 5)
│       └── __init__.py             ← Package marker
│
├── scripts/                        ← Utilities (already existed)
│   ├── README.md                   ← NEW (Phase 3 placeholder)
│   ├── run_quality.py              (existing)
│   ├── dedupe_jsonl.py             (existing)
│   └── ... (other existing scripts)
│
├── main/                           ← ORIGINAL APEX (UNTOUCHED ✅)
│   ├── Home.py
│   ├── src/
│   │   ├── constants.py            ← Source for config extraction
│   │   ├── model_router.py         ← Source for config extraction
│   │   ├── postprocess.py          ← Source for config extraction
│   │   └── ...
│   ├── pages/
│   ├── data/
│   └── ... (0% changes)
│
├── .gitignore                      ← UPDATED (added configurable/ ignore)
│
├── PHASE_0_COMPLETE.md             ← NEW (completion summary)
├── PHASE_0_STATUS.md               ← NEW (verification checklist)
├── PHASE_1_CHECKLIST.md            ← NEW (next step guide)
│
├── docs/
│   ├── REUSABILITY_STRATEGY.md     ← Architecture (created earlier)
│   ├── DUAL_VERSION_STRATEGY.md    ← Implementation (created earlier)
│   └── ... (existing docs)
│
└── ... (all other original files)
```

---

## What's New (Phase 0)

### Directories Created: 18+

**Core Structure**:
- `configurable/src/` — Python module
- `configurable/pages/` — Streamlit pages
- `configurable/config/` — Configuration files
- `configurable/tests/` — Test suite

**Data Isolation**:
- `configurable/data/` — Runtime data (pdfs/, briefs/, quality/)
- `configurable/deployment/apex_mobility/` — Tenant template
  - `config/` — Apex configuration template
  - `data/` — Tenant-isolated storage

**Utilities**:
- `scripts/` — Existing scripts + new README.md

### Documentation Created: 4 files

- `configurable/README.md` — Phase guide and roadmap
- `PHASE_0_COMPLETE.md` — This completion summary
- `PHASE_0_STATUS.md` — Verification instructions
- `PHASE_1_CHECKLIST.md` — Detailed file-by-file extraction guide
- `scripts/README.md` — Phase 3 placeholder

### Git Configuration

- Updated `.gitignore` with configurable/ ignore rules
- Result: Won't sync to GitHub (local development only)

---

## Files to be Created (Later Phases)

### Phase 1: Configuration Files (6 files)

```
configurable/config/
├── company-config.yaml             ← Extract from constants.py
├── topics-taxonomy.yaml            ← Extract from constants.py + model_router.py
├── macro-themes.yaml               ← Extract from constants.py
├── priority-rules.yaml             ← Extract from postprocess.py
├── region-mapping.csv              ← Copy from data/new_country_mapping.csv
└── source-types.yaml               ← Extract from constants.py
```

### Phase 2: Python Module (1 file)

```
configurable/src/
├── config_loader.py                ← NEW (loads YAML/CSV)
├── constants.py                    ← Modified (loads from config/)
├── model_router.py                 ← Modified (templated prompts)
├── postprocess.py                  ← Modified (config-driven rules)
└── ... (rest copied as-is)
```

### Phase 3: Launch Scripts (3 files)

```
scripts/
├── run_apex.bat / run_apex.sh      ← Launch main/
├── run_configurable.bat / run_configurable.sh ← Launch configurable/
├── run_tenant.sh                   ← Launch any tenant
├── compare_versions.py             ← Validation
└── validate_configs.py             ← Config checker
```

---

## Key Points

| ✅ Completed | Details |
|---|---|
| **Folder structure** | All 18+ directories created |
| **Git ignore** | configurable/ not tracked, won't sync to GitHub |
| **Documentation** | 4 new files explaining phases, roadmap, checklists |
| **main/ safety** | 0% changes, completely untouched |
| **Ready for Phase 1** | Extraction can begin immediately |

---

## Size & Scope

```
Total new folders:           18+
Total files created:         ~10 (mostly __init__.py, README.md, checklists)
Total code written:          0 (Phase 0 is structure only)
Code modifications:          0 (main/ untouched)
Git impact:                  0 (ignored, not synced)
Time investment:            ~30 min (folder creation + git config)
```

---

## Ready for Phase 1?

**Prerequisites** ✅:
- Folder structure ✅
- Git configured ✅
- Documentation ready ✅
- main/ untouched ✅

**Start Phase 1 when ready**:

1. Open `PHASE_1_CHECKLIST.md`
2. For each of 6 config files:
   - Find source lines in `src/constants.py`, `src/model_router.py`, etc.
   - Extract values
   - Create YAML/CSV file in `configurable/config/`
3. Validate YAML syntax
4. Total time: ~2.5 hours

---

## Tree Command Output

To generate this tree yourself on Windows:

```powershell
# PowerShell (install Tree module)
tree /F /A "configurable"

# Or generate with Python
python -c "
import os
for root, dirs, files in os.walk('configurable'):
    level = root.replace('configurable', '').count(os.sep)
    indent = ' ' * 2 * level
    print(f'{indent}{os.path.basename(root)}/')
    subindent = ' ' * 2 * (level + 1)
    for file in files:
        print(f'{subindent}{file}')
"
```

To verify from bash:

```bash
tree configurable
# or
find configurable -type f | sort
find configurable -type d | sort
```

---

**Status**: ✅ Phase 0 Complete - Ready for Phase 1

**Next**: See `PHASE_1_CHECKLIST.md` to begin config extraction (~2.5 hours)
