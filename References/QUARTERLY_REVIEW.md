# Quarterly Review Checklist

> Copy this checklist each quarter. Work top-to-bottom — company watchlist first (no code risk), code enums last (run tests after).

**Quarter:** ____  **Reviewer:** ____  **Date:** ____

---

## 1. Company watchlist — `References/company-watchlist.md`
No code changes needed. Pure reference file.

- [ ] **Competitors**: new entrants? M&A that merged or eliminated players? Tier re-ranking?
- [ ] **OEM customers**: new brands, dissolved alliances, new EV OEMs reaching volume?
- [ ] **Tech ecosystem partners**: new sensor/access/actuator suppliers? Partnerships ended?
- [ ] **Critical signals / red flags**: still relevant? New disruption patterns?

## 2. Topics — `src/constants.py` → `CANON_TOPICS`
Topic names, tagging guidance (comments), and LLM prompt rules all live in code.

- [ ] Any topics to **add**? Update 3 places: `CANON_TOPICS` in `constants.py`, tagging comments above it, and `extraction_prompt()` in `model_router.py`
- [ ] Any topics to **rename**? Same 3 places, plus grep for old name in `MACRO_THEME_RULES`
- [ ] Any topics to **remove**? Same 3 places, plus check no macro-theme rule references it
- [ ] Run: `python -m pytest tests/ -q`

## 3. Regions — `src/constants.py` + `src/postprocess.py`
Most coupled to code. Check all three layers.

- [ ] **Display regions** (`DISPLAY_REGIONS` in `constants.py`): broad buckets still correct? New continent-level region needed?
- [ ] **Footprint regions** (`FOOTPRINT_REGIONS` in `constants.py`): Apex Mobility operational footprint changed? New plant country?
- [ ] **Collapse map** (`FOOTPRINT_TO_DISPLAY` in `constants.py`): every footprint entry maps to a display bucket?
- [ ] **Country mappings** (`COUNTRY_TO_FOOTPRINT` in `postprocess.py`): new countries appearing in ingested articles that aren't mapped?
- [ ] **City hints** (`_CITY_REGION_HINTS` in `postprocess.py`): new major auto-industry cities to add?
- [ ] **Region aliases** (`REGION_ALIASES` in `postprocess.py`): any informal region names the LLM uses that aren't caught?
- [ ] Run: `python -m pytest tests/test_regions_bucketed.py -v`

## 4. Macro themes — `src/constants.py` → `MACRO_THEME_RULES`
Review detection rules and thresholds.

- [ ] **Existing themes**: thresholds (`min_groups`) still appropriate? Keywords catching real articles?
- [ ] **New themes**: any recurring intelligence pattern that should be auto-detected?
- [ ] **`PREMIUM_OEMS`**: set still correct? Missing non-European premium (Genesis, Lexus)?
- [ ] **Rollups** (`STRUCTURAL_ROLLUP_RULES`): cluster labels still meaningful?
- [ ] **Anti-keywords**: any false suppressions observed?
- [ ] Run: `python -m pytest tests/test_macro_themes.py -v`

## 5. Other enums — `src/constants.py`
Quick scan.

- [ ] **`ALLOWED_SOURCE_TYPES`**: new publishers being ingested that default to "Other"?
- [ ] **`ALLOWED_ACTOR_TYPES`**: any actor category gap?
- [ ] **`ALLOWED_REVIEW`**: review workflow changed?

## 6. Final validation

- [ ] Run full test suite: `python -m pytest tests/ -v`
- [ ] Ingest one recent article and verify record looks correct
- [ ] Update "Last updated" date in `References/company-watchlist.md`

---

## Where things live (quick reference)

| What | Source of truth | Guidance doc |
|---|---|---|
| Topic names + guidance | `src/constants.py` → `CANON_TOPICS` (comments) + `model_router.py` → `extraction_prompt()` | — |
| Region enums | `src/constants.py` → `DISPLAY_REGIONS`, `FOOTPRINT_REGIONS` | `AGENTS.md` (two-tier architecture) |
| Country mappings | `src/postprocess.py` → `COUNTRY_TO_FOOTPRINT` | — |
| Company watchlist | `References/company-watchlist.md` | same file |
| Macro theme rules | `src/constants.py` → `MACRO_THEME_RULES` | `AGENTS.md` (how to add a theme) |
| Architecture & constraints | `AGENTS.md` | — |
