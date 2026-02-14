"""Lightweight RPD (Requests Per Day) tracker for Gemini API calls.

Persists call counts to a local JSON file. Resets at midnight Pacific Time
(matching Google's billing window).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Optional

_PT = timezone(timedelta(hours=-8))  # Pacific Standard (close enough for reset tracking)
_TRACKER_PATH = Path("data") / "api_usage.json"

# Gemini free-tier limits (as of Feb 2026):
#   gemini-2.5-flash:      5 RPM, 250K TPM, 20 RPD
#   gemini-2.5-flash-lite: 10 RPM, 250K TPM, 20 RPD
# Override via set_quota() if your plan differs.
DEFAULT_QUOTAS: Dict[str, int] = {
    "gemini-2.5-flash-lite": 20,
    "gemini-2.5-flash": 20,
}


def _pt_today() -> str:
    """Current date in Pacific Time as YYYY-MM-DD."""
    return datetime.now(_PT).strftime("%Y-%m-%d")


def _load() -> dict:
    try:
        return json.loads(_TRACKER_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict) -> None:
    _TRACKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TRACKER_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _ensure_today(data: dict) -> dict:
    """Reset counts if the stored date is not today (PT)."""
    today = _pt_today()
    if data.get("date") != today:
        data = {"date": today, "calls": {}, "quotas": data.get("quotas", {})}
    return data


def record_call(model: str, count: int = 1) -> None:
    """Record `count` API calls for `model`."""
    data = _ensure_today(_load())
    calls = data.setdefault("calls", {})
    calls[model] = calls.get(model, 0) + count
    _save(data)


def get_usage() -> Dict[str, Dict]:
    """Return {model: {used, quota, remaining}} for today."""
    data = _ensure_today(_load())
    calls = data.get("calls", {})
    custom_quotas = data.get("quotas", {})

    all_models = set(list(calls.keys()) + list(DEFAULT_QUOTAS.keys()) + list(custom_quotas.keys()))
    result = {}
    for model in sorted(all_models):
        quota = custom_quotas.get(model, DEFAULT_QUOTAS.get(model, 0))
        used = calls.get(model, 0)
        result[model] = {
            "used": used,
            "quota": quota,
            "remaining": max(0, quota - used),
        }
    return result


def get_remaining(model: str) -> int:
    """Remaining calls for a specific model today."""
    usage = get_usage()
    info = usage.get(model, {})
    return info.get("remaining", DEFAULT_QUOTAS.get(model, 0))


def set_quota(model: str, daily_limit: int) -> None:
    """Override the default quota for a model."""
    data = _ensure_today(_load())
    quotas = data.setdefault("quotas", {})
    quotas[model] = daily_limit
    _save(data)


def reset_date() -> Optional[str]:
    """Return the PT date of the current tracking window."""
    return _pt_today()
