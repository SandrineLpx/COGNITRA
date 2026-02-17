"""
Backward-compatible wrapper around the canonical dedupe engine.

`src.dedupe` is the single source of truth for deduplication logic.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from src.dedupe import dedup_and_rank as _dedup_and_rank


def dedup_and_rank(records: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    return _dedup_and_rank(records)
