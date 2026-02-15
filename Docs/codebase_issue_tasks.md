# Codebase Issue Tasks

This backlog proposes one focused task in each requested category.

## 1) Typo fix task

**Task:** Rename typoed test class `TestOWeeklyBriefing` to `TestWeeklyBriefing`.

- **Why:** The leading `O` appears accidental and reduces readability/searchability in test reports.
- **Location:** `test_scenarios.py`.
- **Acceptance criteria:**
  - Class name is updated consistently.
  - Test collection output shows `TestWeeklyBriefing`.

## 2) Bug fix task

**Task:** Resolve failing test import by either restoring `normalize_title` in `src/dedupe.py` or updating tests to use the current internal normalizer API.

- **Why:** `pytest` currently fails during collection due to `ImportError: cannot import name 'normalize_title'`.
- **Locations:**
  - `test_scenarios.py` imports `normalize_title`.
  - `src/dedupe.py` does not define/export `normalize_title`.
- **Acceptance criteria:**
  - `pytest -q test_scenarios.py` runs without collection errors.
  - Title normalization tests validate an actual supported public function.

## 3) Comment/documentation discrepancy task

**Task:** Reconcile dependency documentation in `README.md` with actual runtime/test imports.

- **Why:** README dependency list omits currently used packages (e.g., `altair`, `google-genai`, and `pytest`), while the code/docs reference them.
- **Locations:**
  - `README.md` dependency section.
  - `pages/04_Dashboard.py` imports `altair`.
  - `README.md` model routing references Gemini (`google-genai`).
  - `test_scenarios.py` uses `pytest`.
- **Acceptance criteria:**
  - README dependency/setup instructions include all required core packages for app + tests.
  - A fresh setup using README succeeds for basic run and test commands.

## 4) Test improvement task

**Task:** Make date-sensitive tests deterministic by replacing hard-coded calendar dates with relative dates or a frozen clock.

- **Why:** Tests such as weekly candidate filtering use fixed dates (e.g., `2026-02-12`) that can become stale and flaky over time.
- **Location:** `test_scenarios.py` weekly briefing tests.
- **Acceptance criteria:**
  - Tests pass consistently regardless of current date.
  - No reliance on real current time for assertions.
  - Add one regression test that demonstrates boundary behavior at exactly `N` days.
