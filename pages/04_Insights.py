import streamlit as st
import pandas as pd
import altair as alt
import re
from collections import Counter
from src import ui
from src.quality import BRIEF_QC_LOG, QUALITY_RUNS_LOG, RECORD_QC_LOG, _read_jsonl as read_quality_jsonl
from src.ui_helpers import enforce_navigation_lock, load_records_cached, safe_list


# â”€â”€ Pure helpers (unit-testable) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def explode_list_column(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Safely explode a list column. Returns long-form df with col values as strings."""
    if col not in df.columns:
        return pd.DataFrame(columns=df.columns)
    out = df.copy()
    out[col] = out[col].apply(safe_list)
    out = out.explode(col)
    out[col] = out[col].astype(str).str.strip()
    out = out[out[col].ne("") & out[col].ne("None") & out[col].ne("nan")]
    return out


def weighted_explode(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Explode list column with weight = 1/len(list) per record to avoid double-counting."""
    if col not in df.columns:
        return pd.DataFrame(columns=list(df.columns) + ["_weight"])
    out = df.copy()
    out[col] = out[col].apply(safe_list)
    out["_weight"] = out[col].apply(lambda lst: 1.0 / max(len(lst), 1))
    out = out.explode(col)
    out[col] = out[col].astype(str).str.strip()
    out = out[out[col].ne("") & out[col].ne("None") & out[col].ne("nan")]
    return out


# Lightweight alias map for analytics display canonicalization.
# Keep this UI-focused (does not modify stored records).
_COMPANY_ALIASES: dict[str, str] = {
    "gm": "General Motors",
    "general motors co": "General Motors",
    "general motors company": "General Motors",
    "vw": "Volkswagen",
    "volkswagen ag": "Volkswagen",
    "ford motor co": "Ford",
    "ford motor company": "Ford",
    "renault sa": "Renault",
    "stellantis nv": "Stellantis",
    "mercedes-benz group ag": "Mercedes-Benz",
    "bmw ag": "BMW",
    "jlr": "Jaguar Land Rover",
    "kia corp": "Kia",
    "kia motors": "Kia",
}


def canonicalize_company(name: str) -> str:
    """Normalize company name via alias map."""
    clean = name.strip()
    return _COMPANY_ALIASES.get(clean.lower(), clean)


def classify_topic_momentum(prior: float, recent: float, delta: float,
                            emerging_threshold: float = 2.0) -> str:
    """Classify topic trend: Emerging / Expanding / Fading / Stable."""
    if prior < emerging_threshold and recent >= emerging_threshold:
        return "Emerging"
    if prior >= emerging_threshold and delta > 0:
        return "Expanding"
    if delta < 0:
        return "Fading"
    return "Stable"


def week_start(ts: pd.Series) -> pd.Series:
    """Monday-based week start from a datetime series."""
    return ts.dt.to_period("W-SUN").apply(lambda p: p.start_time)


def _normalize_filter_tokens(query: str) -> list[str]:
    normalized = " ".join(str(query or "").lower().replace(",", " ").split())
    return [tok for tok in normalized.split(" ") if tok]


def _insights_filter_blob(row: pd.Series) -> str:
    parts: list[str] = []
    scalar_fields = [
        "record_id",
        "title",
        "source_type",
        "publish_date",
        "priority",
        "confidence",
        "review_status",
    ]
    list_fields = [
        "topics",
        "macro_themes_detected",
        "regions_relevant_to_apex_mobility",
        "country_mentions",
        "companies_mentioned",
    ]
    for key in scalar_fields:
        value = str(row.get(key) or "").strip()
        if value:
            parts.append(value)
    for key in list_fields:
        values = safe_list(row.get(key))
        parts.extend(str(v).strip() for v in values if str(v).strip())
    return " ".join(parts).lower()


def _insights_matches_tokens(row: pd.Series, tokens: list[str]) -> bool:
    if not tokens:
        return True
    blob = _insights_filter_blob(row)
    return all(token in blob for token in tokens)


def _to_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _signed_int(value: int) -> str:
    if value > 0:
        return f"Increase {value}"
    if value < 0:
        return f"Decrease {abs(value)}"
    return "No change"


def _format_delta_change(cur: float | int | None, prev: float | int | None, *, kind: str = "float") -> str | None:
    if cur is None or prev is None:
        return None
    try:
        delta = float(cur) - float(prev)
    except Exception:
        return None
    if abs(delta) < 1e-9:
        return "No change"
    direction = "Increase" if delta > 0 else "Decrease"
    if kind == "pct":
        magnitude = f"{abs(delta):.0%}"
    elif kind == "int":
        magnitude = f"{abs(delta):.0f}"
    else:
        magnitude = f"{abs(delta):.1f}"
    return f"{direction} {magnitude}"


def _counter_max_delta(recent_counter: Counter, prior_counter: Counter) -> tuple[str, int]:
    keys = set(recent_counter.keys()) | set(prior_counter.keys())
    if not keys:
        return "", 0
    best_key = max(keys, key=lambda k: (recent_counter.get(k, 0) - prior_counter.get(k, 0), recent_counter.get(k, 0)))
    return str(best_key), int(recent_counter.get(best_key, 0) - prior_counter.get(best_key, 0))


_CLOSURE_SIGNAL_RE = re.compile(
    r"\b(latch|latches|door\s*system|door\s*handle|handle|digital\s*key|smart\s*entry|cinch|striker|closure)\b",
    re.IGNORECASE,
)


def _record_has_closure_signal(row: pd.Series) -> bool:
    topics = {str(x).strip().lower() for x in safe_list(row.get("topics"))}
    if "closure technology & innovation" in topics:
        return True
    text_parts = [str(row.get("title") or "")]
    for field in ("keywords", "evidence_bullets", "key_insights", "topics"):
        text_parts.extend(str(x) for x in safe_list(row.get(field)))
    return bool(_CLOSURE_SIGNAL_RE.search(" ".join(text_parts)))


def build_executive_snapshot_insights(
    recent: pd.DataFrame,
    prior: pd.DataFrame,
) -> list[str]:
    if recent.empty:
        return ["Coverage: No records in the last 7 days for the current filter window."]

    insights: list[str] = []

    recent_topics = Counter(str(x) for vals in recent.get("topics", []) for x in safe_list(vals))
    prior_topics = Counter(str(x) for vals in prior.get("topics", []) for x in safe_list(vals))
    if recent_topics:
        top_topics = recent_topics.most_common(2)
        topic_headline = ", ".join(f"{name} ({count})" for name, count in top_topics)
        insights.append(f"Market Shift: Top topic signals this week are {topic_headline}.")
        rising_topic, topic_delta = _counter_max_delta(recent_topics, prior_topics)
        if rising_topic and topic_delta > 0:
            insights.append(f"Momentum Signal: Fastest-rising topic is {rising_topic} ({_signed_int(topic_delta)} mention(s) vs prior week).")

    closure_recent = recent[recent.apply(_record_has_closure_signal, axis=1)].copy()
    closure_prior = prior[prior.apply(_record_has_closure_signal, axis=1)].copy()
    closure_recent_n = len(closure_recent)
    closure_prior_n = len(closure_prior)
    if closure_recent_n > 0:
        insights.append(
            f"Closure Signal: Closure-system mentions appear in {closure_recent_n} record(s) ({_signed_int(closure_recent_n - closure_prior_n)} vs prior week)."
        )
        closure_regions = Counter(
            str(x)
            for vals in closure_recent.get("regions_relevant_to_apex_mobility", [])
            for x in safe_list(vals)
        )
        if closure_regions:
            top_region, top_region_count = closure_regions.most_common(1)[0]
            insights.append(f"Regional Focus: Closure hotspot region is {top_region} ({top_region_count} mention(s)).")
        else:
            insights.append("Regional Focus: Closure-system mentions are present, but no footprint region signal was detected.")
    else:
        insights.append("Closure Signal: No closure-system mention detected in the recent 7-day window.")

    return insights[:5]


def _weighted_record_score(high: int, medium: int, low: int) -> int:
    return max(0, 100 - (25 * high) - (10 * medium) - (2 * low))


def _pick_latest_record_qc_run(qc_runs: list[dict]) -> dict:
    if not qc_runs:
        return {}

    preferred = [
        row for row in qc_runs
        if str(row.get("qc_scope") or "") == "record_only"
        and str(row.get("target_mode") or "") == "all_records"
    ]
    candidates = preferred or qc_runs
    return max(
        candidates,
        key=lambda r: (_to_int(r.get("run_version"), -1), str(r.get("created_at") or "")),
    )


def _record_qc_runs_for_breakdown(qc_runs: list[dict]) -> list[dict]:
    if not qc_runs:
        return []
    preferred = [
        row for row in qc_runs
        if str(row.get("qc_scope") or "") == "record_only"
        and str(row.get("target_mode") or "") == "all_records"
    ]
    candidates = preferred or qc_runs
    return sorted(
        candidates,
        key=lambda r: (_to_int(r.get("run_version"), -1), str(r.get("created_at") or "")),
        reverse=True,
    )


def build_record_qc_breakdown(
    records: list[dict],
    qc_runs: list[dict],
    record_qc_rows: list[dict],
    selected_run: dict | None = None,
) -> dict:
    """Build per-record QC scores for a selected run (defaults to latest available)."""
    run_row = selected_run or _pick_latest_record_qc_run(qc_runs)
    if not run_row:
        return {}

    run_id = str(run_row.get("run_id") or "")
    run_version = _to_int(run_row.get("run_version"), 0)

    if run_id:
        run_rows = [row for row in record_qc_rows if str(row.get("run_id") or "") == run_id]
    else:
        run_rows = [row for row in record_qc_rows if _to_int(row.get("version"), -1) == run_version]

    findings_by_record: dict[str, list[dict]] = {}
    for row in run_rows:
        rid = str(row.get("record_id") or "").strip()
        if rid:
            findings_by_record.setdefault(rid, []).append(row)

    records_by_id = {
        str(rec.get("record_id") or "").strip(): rec
        for rec in records
        if str(rec.get("record_id") or "").strip()
    }

    breakdown_rows: list[dict] = []
    for rid, rec in records_by_id.items():
        rec_findings = findings_by_record.get(rid, [])
        sev = Counter(str(f.get("severity") or "").title() for f in rec_findings)
        high = _to_int(sev.get("High"))
        medium = _to_int(sev.get("Medium"))
        low = _to_int(sev.get("Low"))
        score = _weighted_record_score(high, medium, low)
        types = Counter(
            str(f.get("finding_type") or "").strip()
            for f in rec_findings
            if str(f.get("finding_type") or "").strip()
        )
        top_types = ", ".join(f"{k} ({v})" for k, v in types.most_common(3))

        breakdown_rows.append(
            {
                "record_id": rid,
                "title": str(rec.get("title") or ""),
                "score": score,
                "high": high,
                "medium": medium,
                "low": low,
                "total_findings": len(rec_findings),
                "top_finding_types": top_types,
                "priority": str(rec.get("priority") or ""),
                "confidence": str(rec.get("confidence") or ""),
                "review_status": str(rec.get("review_status") or ""),
                "_findings": rec_findings,
            }
        )

    breakdown_rows.sort(
        key=lambda r: (r["score"], -r["high"], -r["medium"], -r["low"], r["record_id"])
    )
    avg_score = round(
        sum(row["score"] for row in breakdown_rows) / max(len(breakdown_rows), 1),
        1,
    )
    with_findings = sum(1 for row in breakdown_rows if row["total_findings"] > 0)

    return {
        "run_id": run_id,
        "run_version": run_version,
        "avg_score": avg_score,
        "rows": breakdown_rows,
        "records_with_findings": with_findings,
        "records_total": len(breakdown_rows),
    }


def _brief_qc_runs_for_breakdown(qc_runs: list[dict]) -> list[dict]:
    if not qc_runs:
        return []
    candidates = []
    for row in qc_runs:
        brief_id = str(row.get("brief_id") or "").strip()
        if not brief_id or brief_id == "no_brief":
            continue
        if row.get("weighted_brief_score") is None and _to_int(row.get("brief_qc_high"), 0) == 0 and _to_int(row.get("brief_qc_medium"), 0) == 0 and _to_int(row.get("brief_qc_low"), 0) == 0:
            continue
        candidates.append(row)
    return sorted(
        candidates,
        key=lambda r: (_to_int(r.get("run_version"), -1), str(r.get("created_at") or "")),
        reverse=True,
    )


def build_brief_qc_breakdown(
    qc_runs: list[dict],
    brief_qc_rows: list[dict],
    selected_run: dict | None = None,
) -> dict:
    run_row = selected_run
    if run_row is None:
        runs = _brief_qc_runs_for_breakdown(qc_runs)
        run_row = runs[0] if runs else None
    if not run_row:
        return {}

    run_id = str(run_row.get("run_id") or "")
    run_version = _to_int(run_row.get("run_version"), 0)
    if run_id:
        run_rows = [row for row in brief_qc_rows if str(row.get("run_id") or "") == run_id]
    else:
        run_rows = [row for row in brief_qc_rows if _to_int(row.get("version"), -1) == run_version]

    sev = Counter(str(f.get("severity") or "").title() for f in run_rows)
    by_issue = Counter(
        str(f.get("issue_type") or "").strip()
        for f in run_rows
        if str(f.get("issue_type") or "").strip()
    )
    issue_summary = ", ".join(f"{k} ({v})" for k, v in by_issue.most_common(5))

    return {
        "run_id": run_id,
        "run_version": run_version,
        "brief_id": str(run_row.get("brief_id") or ""),
        "created_at": str(run_row.get("created_at") or ""),
        "weighted_brief_score": run_row.get("weighted_brief_score"),
        "high": _to_int(sev.get("High")),
        "medium": _to_int(sev.get("Medium")),
        "low": _to_int(sev.get("Low")),
        "total_findings": len(run_rows),
        "issue_summary": issue_summary,
        "rows": run_rows,
    }


# â”€â”€ Page setup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

st.set_page_config(page_title="Cognitra", page_icon="assets/logo/cognitra-icon.png", layout="wide")
enforce_navigation_lock("insights")
ui.init_page(active_step="Insights")
ui.render_page_header(
    "Insights",
    subtitle="Analytics across your structured intelligence records. All metrics are derived from validated, approved data.",
    active_step="Insights",
)

ui.render_sidebar_utilities(model_label="analytics")

records = load_records_cached()
if not records:
    st.info("No records yet.")
    st.stop()

df = pd.json_normalize(records)
if df.empty:
    st.info("No records after selection.")
    st.stop()

# Compute effective date once (publish_date only)
publish_dt = pd.to_datetime(df.get("publish_date"), errors="coerce", utc=True).dt.tz_convert(None)
df["publish_date_dt"] = publish_dt
df["event_day"] = publish_dt.dt.normalize()

today = pd.Timestamp.today().normalize()
default_from = (today - pd.Timedelta(days=30)).date()
default_to = today.date()
all_regions = sorted(
    {
        str(x)
        for vals in df.get("regions_relevant_to_apex_mobility", [])
        for x in safe_list(vals)
        if str(x).strip()
    }
)
all_topics = sorted(
    {
        str(x)
        for vals in df.get("topics", [])
        for x in safe_list(vals)
        if str(x).strip()
    }
)

f1, f2, f3, f4, f5 = st.columns([2.0, 1.3, 1.4, 1.0, 1.0])
with f1:
    filter_search = st.text_input(
        "Search records",
        key="ins_filter_search",
        placeholder="Search records...",
        label_visibility="collapsed",
    )
with f2:
    filter_region = st.selectbox(
        "Region",
        options=["All Regions"] + all_regions,
        key="ins_filter_region",
        label_visibility="collapsed",
    )
with f3:
    filter_topic = st.selectbox(
        "Topic",
        options=["All Topics"] + all_topics,
        key="ins_filter_topic",
        label_visibility="collapsed",
    )
with f4:
    date_from = st.date_input(
        "From",
        value=default_from,
        key="ins_date_from",
        label_visibility="collapsed",
    )
with f5:
    date_to = st.date_input(
        "To",
        value=default_to,
        key="ins_date_to",
        label_visibility="collapsed",
    )
mask = pd.Series(True, index=df.index)
mask = mask & df["publish_date_dt"].notna()
mask = mask & (df["event_day"] >= pd.Timestamp(date_from)) & (df["event_day"] <= pd.Timestamp(date_to))
if "review_status" in df:
    mask = mask & df["review_status"].astype(str).isin(["Approved"])
if filter_region != "All Regions":
    mask = mask & df.get("regions_relevant_to_apex_mobility", pd.Series(dtype=object)).apply(
        lambda vals: filter_region in safe_list(vals)
    )
if filter_topic != "All Topics":
    mask = mask & df.get("topics", pd.Series(dtype=object)).apply(
        lambda vals: filter_topic in safe_list(vals)
    )
if str(filter_search).strip():
    search_tokens = _normalize_filter_tokens(filter_search)
    if search_tokens:
        mask = mask & df.apply(lambda row: _insights_matches_tokens(row, search_tokens), axis=1)

fdf = df[mask].copy()
if fdf.empty:
    st.warning("No records match current selection.")
    st.stop()

# â”€â”€ KPI â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
st.subheader("Executive Snapshot")
ref_today = pd.Timestamp.today().normalize()
recent_cutoff = ref_today - pd.Timedelta(days=7)
prior_cutoff = ref_today - pd.Timedelta(days=14)
recent = fdf[fdf["event_day"] >= recent_cutoff].copy()
prior = fdf[(fdf["event_day"] >= prior_cutoff) & (fdf["event_day"] < recent_cutoff)].copy()
recent_topics = Counter(str(x) for vals in recent.get("topics", []) for x in safe_list(vals))
prior_topics = Counter(str(x) for vals in prior.get("topics", []) for x in safe_list(vals))
recent_topic_total = sum(recent_topics.values())
prior_topic_total = sum(prior_topics.values())
topic_signal_delta = recent_topic_total - prior_topic_total
active_topics = len(recent_topics)

closure_recent = recent[recent.apply(_record_has_closure_signal, axis=1)].copy() if not recent.empty else recent
closure_prior = prior[prior.apply(_record_has_closure_signal, axis=1)].copy() if not prior.empty else prior
closure_recent_n = len(closure_recent)
closure_prior_n = len(closure_prior)
closure_delta = closure_recent_n - closure_prior_n
closure_regions = Counter(str(x) for vals in closure_recent.get("regions_relevant_to_apex_mobility", []) for x in safe_list(vals))
closure_top_region = closure_regions.most_common(1)[0][0] if closure_regions else "-"
closure_top_region_count = closure_regions.most_common(1)[0][1] if closure_regions else 0

sx1, sx2, sx3, sx4 = st.columns(4)
with sx1:
    ui.kpi_card(
        "Topic Signals (7d)",
        recent_topic_total,
        caption=f"Change vs prior week: {_signed_int(topic_signal_delta)}",
    )
with sx2:
    ui.kpi_card(
        "Active Topics (7d)",
        active_topics,
        caption="Distinct active topic clusters this week",
    )
with sx3:
    ui.kpi_card(
        "Closure-System Mentions (7d)",
        closure_recent_n,
        caption=f"Change vs prior week: {_signed_int(closure_delta)}",
    )
with sx4:
    ui.kpi_card(
        "Closure Hotspot Region",
        closure_top_region,
        caption=f"Mentions: {closure_top_region_count}",
    )

snapshot_insights = build_executive_snapshot_insights(recent, prior)
st.markdown("**Key insights**")
for line in snapshot_insights:
    if ":" in line:
        lead, detail = line.split(":", 1)
        st.markdown(f"- **{lead.strip()}:** {detail.strip()}")
    else:
        st.markdown(f"- {line}")

# â”€â”€ Weekly Histogram â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
trend_col1, trend_col2 = st.columns(2)

with trend_col1:
    st.subheader("Weekly Record Volume")
    weekly = fdf.dropna(subset=["event_day"]).copy()
    if not weekly.empty:
        weekly["event_week"] = weekly["event_day"].dt.to_period("W").dt.start_time
        weekly["source_type"] = weekly.get("source_type", pd.Series(index=weekly.index)).fillna("Unknown")
        weekly_hist = (
            weekly.groupby(["event_week", "source_type"], dropna=False)
            .size()
            .reset_index(name="count")
        )
        weekly_hist["week_label"] = weekly_hist["event_week"].dt.strftime("%Y-%m-%d")
        chart = (
            alt.Chart(weekly_hist)
            .mark_bar()
            .encode(
                x=alt.X("week_label:O", title="Week (start)"),
                y=alt.Y("count:Q", title="Records"),
                color=alt.Color("source_type:N", title="Source"),
                tooltip=["event_week:T", "source_type:N", "count:Q"],
            )
            .properties(height=280)
        )
        st.altair_chart(chart, width='stretch')
    else:
        st.caption("No dated records for weekly histogram.")

with trend_col2:
    st.subheader("Topic Momentum")
    st.caption("Weighted topic frequency change: recent half vs prior half of date range.")
    dated_rows = fdf.dropna(subset=["event_day"])
    if not dated_rows.empty and "topics" in dated_rows:
        date_min = dated_rows["event_day"].min()
        date_max = dated_rows["event_day"].max()
        midpoint = date_min + (date_max - date_min) / 2
        prior_df = dated_rows[dated_rows["event_day"] < midpoint]
        recent_df = dated_rows[dated_rows["event_day"] >= midpoint]
        st.caption(
            f"Prior: {date_min.strftime('%b %d')} - {(midpoint - pd.Timedelta(days=1)).strftime('%b %d')}  |  "
            f"Recent: {midpoint.strftime('%b %d')} - {date_max.strftime('%b %d')}"
        )

        prior_w = weighted_explode(prior_df, "topics")
        recent_w = weighted_explode(recent_df, "topics")

        prior_counts = prior_w.groupby("topics")["_weight"].sum() if not prior_w.empty else pd.Series(dtype=float)
        recent_counts = recent_w.groupby("topics")["_weight"].sum() if not recent_w.empty else pd.Series(dtype=float)

        all_topics_set = sorted(set(prior_counts.index) | set(recent_counts.index))
        if all_topics_set:
            momentum = pd.DataFrame({
                "topic": all_topics_set,
                "prior": [round(prior_counts.get(t, 0.0), 2) for t in all_topics_set],
                "recent": [round(recent_counts.get(t, 0.0), 2) for t in all_topics_set],
            })
            momentum["delta"] = round(momentum["recent"] - momentum["prior"], 2)
            momentum["pct_change"] = round(
                (momentum["recent"] - momentum["prior"]) / momentum["prior"].clip(lower=1e-9), 1
            )
            momentum["class"] = momentum.apply(
                lambda r: classify_topic_momentum(r["prior"], r["recent"], r["delta"]), axis=1
            )
            momentum = momentum.sort_values("delta")
            momentum["color_group"] = momentum["delta"].apply(
                lambda d: "Rising" if d > 0 else ("Falling" if d < 0 else "Flat")
            )
            chart = (
                alt.Chart(momentum)
                .mark_bar()
                .encode(
                    x=alt.X("delta:Q", title="Weighted change in mentions"),
                    y=alt.Y("topic:N", sort=momentum["topic"].tolist(), title=None),
                    color=alt.Color("color_group:N", legend=None),
                    tooltip=["topic", "prior", "recent", "delta", "pct_change", "class"],
                )
                .properties(height=max(180, len(momentum) * 24))
            )
            rule = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule().encode(x="x:Q")
            st.altair_chart(chart + rule, width='stretch')
        else:
            st.caption("Not enough topic data for momentum chart.")
    else:
        st.caption("Not enough dated records for momentum chart.")

# â”€â”€ Region x Topic Heatmap â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
st.subheader("Region-Topic Signal Matrix")
st.caption("Shows where footprint signals concentrate across topics. Weighted mode gives each record total weight 1 to reduce multi-tag inflation.")
if "regions_relevant_to_apex_mobility" in fdf and "topics" in fdf:
    hm_cols = ["regions_relevant_to_apex_mobility", "topics"]
    rid_col = "record_id"
    if rid_col in fdf.columns:
        hm_cols = [rid_col] + hm_cols
    hm = fdf[hm_cols].copy()
    if rid_col not in hm.columns:
        rid_col = "_rid"
        hm[rid_col] = hm.index.astype(str)

    hm["regions_relevant_to_apex_mobility"] = hm["regions_relevant_to_apex_mobility"].apply(safe_list)
    hm["topics"] = hm["topics"].apply(safe_list)
    hm = hm[
        (hm["regions_relevant_to_apex_mobility"].apply(len) > 0)
        & (hm["topics"].apply(len) > 0)
    ].copy()

    if not hm.empty:
        h1, h2, h3 = st.columns(3)
        with h1:
            top_regions = st.slider("Top regions", min_value=6, max_value=20, value=12, step=1, key="ins_heatmap_top_regions")
        with h2:
            top_topics = st.slider("Top topics", min_value=4, max_value=16, value=10, step=1, key="ins_heatmap_top_topics")
        with h3:
            heat_metric = st.selectbox(
                "Heatmap metric",
                options=["Weighted Share (%)", "Record Count"],
                index=0,
                key="ins_heatmap_metric",
            )
        if heat_metric == "Weighted Share (%)":
            st.caption("Weighted Share (%): each record contributes total weight 1 across all its region-topic pairs.")
        else:
            st.caption("Record Count: number of unique records tagged with each region-topic pair.")

        hm["_region_count"] = hm["regions_relevant_to_apex_mobility"].apply(lambda lst: max(len(lst), 1))
        hm["_topic_count"] = hm["topics"].apply(lambda lst: max(len(lst), 1))
        hm["_pair_weight"] = 1.0 / (hm["_region_count"] * hm["_topic_count"])

        hm_long = hm.explode("regions_relevant_to_apex_mobility").explode("topics")
        hm_long["regions_relevant_to_apex_mobility"] = hm_long["regions_relevant_to_apex_mobility"].astype(str).str.strip()
        hm_long["topics"] = hm_long["topics"].astype(str).str.strip()
        hm_long = hm_long[
            hm_long["regions_relevant_to_apex_mobility"].ne("")
            & hm_long["topics"].ne("")
        ].copy()
        hm_long = hm_long.drop_duplicates(subset=[rid_col, "regions_relevant_to_apex_mobility", "topics"])

        if not hm_long.empty:
            matrix = (
                hm_long
                .groupby(["regions_relevant_to_apex_mobility", "topics"], as_index=False)
                .agg(
                    record_pair_count=(rid_col, "nunique"),
                    weighted_signal=("_pair_weight", "sum"),
                )
            )
            matrix["weighted_signal"] = matrix["weighted_signal"].round(4)

            region_order = (
                matrix.groupby("regions_relevant_to_apex_mobility")["weighted_signal"]
                .sum()
                .sort_values(ascending=False)
                .head(top_regions)
                .index
                .tolist()
            )
            topic_order = (
                matrix.groupby("topics")["weighted_signal"]
                .sum()
                .sort_values(ascending=False)
                .head(top_topics)
                .index
                .tolist()
            )
            matrix = matrix[
                matrix["regions_relevant_to_apex_mobility"].isin(region_order)
            &   matrix["topics"].isin(topic_order)
            ].copy()

            matrix["weighted_share_pct"] = (
                matrix["weighted_signal"] / max(float(matrix["weighted_signal"].sum()), 1e-9) * 100.0
            ).round(1)
            matrix["record_count"] = matrix["record_pair_count"].astype(float)

            if heat_metric == "Weighted Share (%)":
                denom = max(float(matrix["weighted_signal"].sum()), 1e-9)
                matrix["value"] = (matrix["weighted_signal"] / denom * 100.0).round(1)
                color_title = "Weighted Share (%)"
                value_fmt = ".1f"
                label_threshold = 4.0
            else:
                matrix["value"] = matrix["record_count"]
                color_title = "Record Count"
                value_fmt = ".0f"
                label_threshold = max(float(matrix["value"].max()) * 0.4, 2.0)

            region_order = [r for r in region_order if r in set(matrix["regions_relevant_to_apex_mobility"])]
            topic_order = [t for t in topic_order if t in set(matrix["topics"])]

            heat = alt.Chart(matrix).mark_rect().encode(
                x=alt.X("topics:N", sort=topic_order, title="Topic"),
                y=alt.Y("regions_relevant_to_apex_mobility:N", sort=region_order, title="Footprint Region"),
                color=alt.Color("value:Q", title=color_title, scale=alt.Scale(scheme="teals")),
                tooltip=[
                    alt.Tooltip("regions_relevant_to_apex_mobility:N", title="Region"),
                    alt.Tooltip("topics:N", title="Topic"),
                    alt.Tooltip("record_pair_count:Q", title="Record pairs", format=".0f"),
                    alt.Tooltip("weighted_signal:Q", title="Weighted signal", format=".3f"),
                    alt.Tooltip("value:Q", title=color_title, format=value_fmt),
                ],
            ).properties(height=max(280, len(region_order) * 24))

            if len(matrix) <= 140:
                labels = alt.Chart(matrix).mark_text(fontSize=10).encode(
                    x=alt.X("topics:N", sort=topic_order),
                    y=alt.Y("regions_relevant_to_apex_mobility:N", sort=region_order),
                    text=alt.Text("value:Q", format=value_fmt),
                    color=alt.condition(f"datum.value > {label_threshold}", alt.value("white"), alt.value("#0f172a")),
                )
                st.altair_chart(heat + labels, width='stretch')
            else:
                st.altair_chart(heat, width='stretch')
        else:
            st.caption("No region-topic pairs for matrix.")
    else:
        st.caption("No region-topic pairs for matrix.")

st.subheader("Top Company Mentions")
if "companies_mentioned" in fdf:
    c1, c2 = st.columns(2)
    with c1:
        top_n = st.slider("Top companies", min_value=5, max_value=25, value=10, step=1, key="ins_top_companies_n")
    with c2:
        metric_mode = st.selectbox(
            "Metric",
            options=["Records mentioning company", "Share of filtered records (%)"],
            index=0,
            key="ins_top_companies_metric",
        )

    # Explode safely, canonicalize, and keep one mention per record/company.
    co_df = fdf[["record_id", "companies_mentioned"]].copy()
    co_long = explode_list_column(co_df, "companies_mentioned")
    if not co_long.empty:
        co_long["company"] = co_long["companies_mentioned"].apply(canonicalize_company)
        co_long["record_id"] = co_long["record_id"].astype(str)
        co_long = co_long.drop_duplicates(subset=["record_id", "company"])

        total_records = max(fdf.get("record_id", pd.Series(dtype=str)).astype(str).nunique(), 1)
        agg = (
            co_long.groupby("company", as_index=False)
            .agg(records=("record_id", "nunique"))
            .sort_values("records", ascending=False)
        )
        agg["share_pct"] = (agg["records"] / total_records * 100.0).round(1)
        agg = agg.head(top_n).copy()
        agg["value_label"] = agg["records"].astype(int).astype(str)
        if metric_mode == "Share of filtered records (%)":
            agg["value"] = agg["share_pct"]
            agg["value_label"] = agg["share_pct"].map(lambda x: f"{x:.1f}%")
            x_title = "Share of filtered records (%)"
            x_fmt = ".1f"
        else:
            agg["value"] = agg["records"].astype(float)
            x_title = "Records mentioning company"
            x_fmt = ".0f"

        if not agg.empty:
            chart = alt.Chart(agg).mark_bar(cornerRadiusEnd=4).encode(
                x=alt.X("value:Q", title=x_title),
                y=alt.Y("company:N", sort="-x", title=None),
                color=alt.Color("records:Q", legend=None, scale=alt.Scale(scheme="blues")),
                tooltip=[
                    alt.Tooltip("company:N", title="Company"),
                    alt.Tooltip("records:Q", title="Records", format=".0f"),
                    alt.Tooltip("share_pct:Q", title="Share %", format=".1f"),
                ],
            )
            labels = chart.mark_text(align="left", dx=4, fontSize=11).encode(
                text=alt.Text("value:Q", format=x_fmt),
            )
            st.altair_chart(chart + labels, width='stretch')
        else:
            st.caption("No company mentions in filtered records.")
    else:
        st.caption("No company mentions in filtered records.")
else:
    st.caption("No company data available.")

# â”€â”€ Quality Score Trend â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
st.divider()
st.subheader("Extraction Quality Score")
st.caption("Quality scores from automated QC runs. Higher is better (0-100). Run `python scripts/run_quality.py` to generate data.")

qc_runs = read_quality_jsonl(QUALITY_RUNS_LOG)
if qc_runs and len(qc_runs) >= 1:
    qc_df = pd.DataFrame(qc_runs)

    # --- KPI metrics row (latest run vs prior) ---
    latest = qc_runs[-1]
    prior = qc_runs[-2] if len(qc_runs) >= 2 else {}

    def _delta(key):
        cur = latest.get(key)
        prev = prior.get(key)
        if cur is not None and prev is not None:
            return round(float(cur) - float(prev), 2)
        return None

    def _delta_text(key: str, percent: bool = False) -> str | None:
        delta_val = _delta(key)
        if delta_val is None:
            return None
        if abs(delta_val) < 1e-9:
            return "No change"
        direction = "Increase" if delta_val > 0 else "Decrease"
        if percent:
            return f"{direction} {abs(delta_val):.0%}"
        return f"{direction} {abs(delta_val):.1f}"

    q1, q2, q3, q4 = st.columns(4)
    with q1:
        ui.kpi_card(
            "Overall Score",
            f"{latest.get('weighted_overall_score', '-')}",
            caption=_delta_text("weighted_overall_score", percent=False),
        )
    with q2:
        ui.kpi_card(
            "Evidence Grounding",
            f"{latest.get('KPI-R3', 0):.0%}",
            caption=_delta_text("KPI-R3", percent=True),
        )
    with q3:
        ui.kpi_card(
            "Canonicalization",
            f"{latest.get('KPI-R4', 0):.0%}",
            caption=_delta_text("KPI-R4", percent=True),
        )
    with q4:
        ui.kpi_card(
            "Geo Determinism",
            f"{latest.get('KPI-R5', 0):.0%}",
            caption=_delta_text("KPI-R5", percent=True),
        )

    bucket = st.radio(
        "Group runs by",
        options=["Hour", "Day", "Week", "Version"],
        index=1,
        horizontal=True,
        key="qc_score_bucket",
    )

    # --- Quality score trend line chart ---
    if "created_at" in qc_df.columns and len(qc_df) >= 2:
        # Normalize to timezone-naive UTC timestamps so day/week buckets render
        # consistently (no browser-local timezone date shifts).
        qc_df["run_date"] = (
            pd.to_datetime(qc_df["created_at"], errors="coerce", utc=True)
            .dt.tz_convert(None)
        )
        qc_df["run_version_num"] = pd.to_numeric(qc_df.get("run_version"), errors="coerce")
        if qc_df["run_version_num"].isna().all():
            qc_df["run_version_num"] = pd.Series(range(1, len(qc_df) + 1), index=qc_df.index, dtype=float)
        score_cols = ["weighted_overall_score", "weighted_record_score", "weighted_brief_score"]
        available = [c for c in score_cols if c in qc_df.columns]
        if available:
            plot_df = qc_df[["run_date", "run_version_num"] + available].dropna(subset=["run_date"])
            melted = plot_df.melt(
                id_vars=["run_date", "run_version_num"],
                value_vars=available,
                var_name="Score Type",
                value_name="Score",
            )
            melted["Score Type"] = melted["Score Type"].map({
                "weighted_overall_score": "Overall",
                "weighted_record_score": "Record",
                "weighted_brief_score": "Brief",
            })
            melted = melted.dropna(subset=["Score Type", "Score"])

            if bucket == "Version":
                melted["run_bucket_version"] = pd.to_numeric(melted["run_version_num"], errors="coerce")
                chart_df = (
                    melted
                    .dropna(subset=["run_bucket_version"])
                    .groupby(["run_bucket_version", "Score Type"], as_index=False)
                    .agg(
                        Score=("Score", "mean"),
                        Runs=("Score", "count"),
                    )
                    .sort_values("run_bucket_version")
                )
                chart_df["bucket_version"] = chart_df["run_bucket_version"].round().astype(int).astype(str)
            else:
                chart_df = pd.DataFrame()

            if bucket == "Hour":
                melted["run_bucket"] = melted["run_date"].dt.floor("h")
            elif bucket == "Day":
                melted["run_bucket"] = melted["run_date"].dt.floor("D")
            elif bucket == "Week":
                melted["run_bucket"] = melted["run_date"].dt.to_period("W-SUN").apply(lambda p: p.start_time)

            if bucket in {"Hour", "Day", "Week"}:
                chart_df = (
                    melted
                    .dropna(subset=["run_bucket"])
                    .groupby(["run_bucket", "Score Type"], as_index=False)
                    .agg(
                        Score=("Score", "mean"),
                        Runs=("Score", "count"),
                    )
                    .sort_values("run_bucket")
                )
                chart_df["bucket_day"] = chart_df["run_bucket"].dt.strftime("%Y-%m-%d")
                chart_df["bucket_week"] = "Week of " + chart_df["bucket_day"]

            if bucket == "Hour":
                x_enc = alt.X("run_bucket:T", title="QC Run Hour")
                tooltip_fields = ["run_bucket:T", "Score Type:N", "Score:Q", "Runs:Q"]
            elif bucket == "Day":
                day_order = chart_df["bucket_day"].drop_duplicates().tolist()
                x_enc = alt.X("bucket_day:N", title="QC Run Day", sort=day_order)
                tooltip_fields = ["bucket_day:N", "Score Type:N", "Score:Q", "Runs:Q"]
            elif bucket == "Week":
                week_order = chart_df["bucket_week"].drop_duplicates().tolist()
                x_enc = alt.X("bucket_week:N", title="QC Run Week", sort=week_order)
                tooltip_fields = ["bucket_week:N", "Score Type:N", "Score:Q", "Runs:Q"]
            else:
                version_order = chart_df["bucket_version"].drop_duplicates().tolist()
                x_enc = alt.X("bucket_version:N", title="QC Run Version", sort=version_order)
                tooltip_fields = ["bucket_version:N", "Score Type:N", "Score:Q", "Runs:Q"]

            lines = alt.Chart(chart_df).mark_line(point=True, strokeWidth=2).encode(
                x=x_enc,
                y=alt.Y("Score:Q", title="Quality Score", scale=alt.Scale(domain=[0, 100])),
                color=alt.Color("Score Type:N", scale=alt.Scale(
                    domain=["Overall", "Record", "Brief"],
                    range=["#1f77b4", "#2ca02c", "#ff7f0e"],
                ), legend=alt.Legend(title="Score Series", orient="top", direction="horizontal")),
                tooltip=tooltip_fields,
            )

            thresholds = pd.DataFrame([
                {"Score": 80, "label": "Good (80)"},
                {"Score": 60, "label": "Warning (60)"},
            ])
            rules = alt.Chart(thresholds).mark_rule(strokeDash=[4, 4], opacity=0.5).encode(
                y="Score:Q",
                color=alt.Color("label:N", scale=alt.Scale(
                    domain=["Good (80)", "Warning (60)"],
                    range=["#2ca02c", "#d62728"],
                ), legend=alt.Legend(title="Thresholds")),
            )

            st.altair_chart(lines + rules, width='stretch')
    else:
        st.caption("Need at least 2 QC runs to show trend chart.")
else:
    st.info("No quality runs found. Run `python scripts/run_quality.py` to generate quality data.")

# â”€â”€ Quality KPI Breakdown â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
st.subheader("QC Quick View")

_KPI_META = [
    # code, label, group, format, direction, target
    ("KPI-R1", "High-severity error rate",       "Record", "pct",   "lower",  "< 5%"),
    ("KPI-R2", "Medium-severity error rate",     "Record", "pct",   "lower",  "< 15%"),
    ("KPI-R3", "Evidence grounding pass rate",   "Record", "pct",   "higher", "> 80%"),
    ("KPI-R4", "Canonicalization pass rate",     "Record", "pct",   "higher", "> 90%"),
    ("KPI-R5", "Geo determinism pass rate",      "Record", "pct",   "higher", "> 80%"),
    ("KPI-B1", "Ungrounded claims (count)",      "Brief",  "int",   "lower",  "= 0"),
    ("KPI-B2", "Overreach citations (count)",    "Brief",  "int",   "lower",  "= 0"),
    ("KPI-B3", "Uncertainty compliance rate",    "Brief",  "pct",   "higher", "> 80%"),
    ("KPI-B4", "Cross-record themes cited",      "Brief",  "int",   "higher", "higher is better"),
    ("KPI-B5", "Action specificity (count)",     "Brief",  "int",   "higher", "higher is better"),
]

if qc_runs and len(qc_runs) >= 1:
    latest_run = qc_runs[-1]
    prior_run = qc_runs[-2] if len(qc_runs) >= 2 else {}

    s1, s2, s3 = st.columns(3)

    def _score_metric(col, key: str, label: str) -> None:
        cur = latest_run.get(key)
        prev = prior_run.get(key)
        if cur is None:
            with col:
                ui.kpi_card(label, "Not available")
            return
        delta = _format_delta_change(cur, prev, kind="float")
        with col:
            ui.kpi_card(label, f"{float(cur):.1f}", caption=delta)

    _score_metric(s1, "weighted_record_score", "Record score")
    _score_metric(s2, "weighted_brief_score", "Brief score")
    _score_metric(s3, "weighted_overall_score", "Overall score")

    record_qc_rows = read_quality_jsonl(RECORD_QC_LOG)
    brief_qc_rows = read_quality_jsonl(BRIEF_QC_LOG)

    latest_record_run = _record_qc_runs_for_breakdown(qc_runs)
    latest_record_run = latest_record_run[0] if latest_record_run else None
    qc_breakdown = build_record_qc_breakdown(
        records,
        qc_runs,
        record_qc_rows,
        selected_run=latest_record_run,
    )

    latest_brief_runs = _brief_qc_runs_for_breakdown(qc_runs)
    latest_brief_run = latest_brief_runs[0] if latest_brief_runs else None
    brief_breakdown = build_brief_qc_breakdown(
        qc_runs,
        brief_qc_rows,
        selected_run=latest_brief_run,
    )

    st.markdown("**Needs Attention**")
    n1, n2 = st.columns(2)
    with n1:
        worst_record = None
        if qc_breakdown:
            bad_rows = [row for row in qc_breakdown["rows"] if row.get("total_findings", 0) > 0]
            if bad_rows:
                worst_record = min(
                    bad_rows,
                    key=lambda r: (r.get("score", 100), -r.get("high", 0), -r.get("medium", 0), r.get("record_id", "")),
                )
        if worst_record:
            st.caption(
                f"Record: `{worst_record['record_id']}` | score {worst_record['score']} | "
                f"{worst_record['high']}H/{worst_record['medium']}M/{worst_record['low']}L"
            )
            st.caption("Action: inspect in Review and fix finding drivers.")
        else:
            st.caption("No record-level findings in latest record QC run.")

    with n2:
        if brief_breakdown:
            score_val = brief_breakdown.get("weighted_brief_score")
            st.caption(
                f"Brief: `{brief_breakdown.get('brief_id') or 'Not available'}` | "
                f"score {('Not available' if score_val is None else f'{float(score_val):.1f}')} | "
                f"{brief_breakdown['high']}H/{brief_breakdown['medium']}M/{brief_breakdown['low']}L"
            )
            brief_file = f"data/briefs/{brief_breakdown['brief_id']}.md" if brief_breakdown.get("brief_id") else ""
            if brief_file:
                st.caption(f"Action: regenerate `{brief_file}` in Brief, Saved Brief Browser.")
        else:
            st.caption("No brief-level findings in latest brief QC run.")

    with st.expander("Advanced: KPI Breakdown", expanded=False):
        rows = []
        for code, label, group, fmt, direction, target in _KPI_META:
            cur = latest_run.get(code)
            prev = prior_run.get(code)
            if cur is None:
                val_str = "Not available"
            elif fmt == "pct":
                val_str = f"{cur:.0%}"
            elif fmt == "score":
                val_str = f"{cur:.1f}"
            else:
                val_str = str(int(cur))

            if cur is not None and prev is not None:
                delta = float(cur) - float(prev)
                delta_kind = "pct" if fmt == "pct" else ("int" if fmt == "int" else "float")
                delta_str = _format_delta_change(cur, prev, kind=delta_kind) or "Not available"
                good = (direction == "higher" and delta > 0) or (direction == "lower" and delta < 0)
                flat = delta == 0
                trend_label = "no change" if flat else ("improved" if good else "declined")
                delta_str = f"{delta_str} ({trend_label})"
            else:
                delta_str = "Not available"

            rows.append(
                {
                    "Group": group,
                    "KPI": code,
                    "Description": label,
                    "Latest": val_str,
                    "vs Prior": delta_str,
                    "Target": target,
                }
            )
        st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)

    with st.expander("Advanced: Record QC Drilldown", expanded=False):
        if qc_breakdown:
            breakdown_runs = _record_qc_runs_for_breakdown(qc_runs)
            selected_breakdown_run = None
            if breakdown_runs:
                selected_breakdown_run = st.selectbox(
                    "QC version",
                    options=breakdown_runs,
                    format_func=lambda r: (
                        f"v{_to_int(r.get('run_version'), 0)}"
                        f" | {str(r.get('created_at') or '')[:19]}"
                        f" | {str(r.get('qc_scope') or 'pipeline')}"
                    ),
                    key="qc_breakdown_version_pick",
                )
            breakdown = build_record_qc_breakdown(
                records,
                qc_runs,
                record_qc_rows,
                selected_run=selected_breakdown_run,
            )

            if breakdown:
                show_only_bad = st.checkbox(
                    "Show only records with findings",
                    value=True,
                    key="qc_breakdown_show_only_bad",
                )
                breakdown_df = pd.DataFrame(breakdown["rows"])
                if show_only_bad:
                    breakdown_df = breakdown_df[breakdown_df["total_findings"] > 0]

                display_cols = [
                    "record_id",
                    "title",
                    "score",
                    "high",
                    "medium",
                    "low",
                    "total_findings",
                    "top_finding_types",
                    "priority",
                    "confidence",
                    "review_status",
                ]
                st.dataframe(
                    breakdown_df[display_cols] if not breakdown_df.empty else pd.DataFrame(columns=display_cols),
                    width='stretch',
                    hide_index=True,
                )

                inspect_options = [
                    row for row in breakdown["rows"]
                    if row["total_findings"] > 0
                ]
                if inspect_options:
                    selected = st.selectbox(
                        "Inspect record findings",
                        options=inspect_options,
                        format_func=lambda x: f"{x['record_id']} | score {x['score']} | {x['title'][:80]}",
                        key="qc_breakdown_record_pick",
                    )
                    selected_findings = selected.get("_findings") or []
                    finding_cols = [
                        "version",
                        "severity",
                        "finding_type",
                        "field",
                        "impact",
                        "notes",
                        "status",
                    ]
                    st.dataframe(
                        pd.DataFrame(selected_findings).reindex(columns=finding_cols),
                        width='stretch',
                        hide_index=True,
                    )
        else:
            st.caption("No record-level QC findings available.")

    with st.expander("Advanced: Brief QC Drilldown", expanded=False):
        brief_runs = _brief_qc_runs_for_breakdown(qc_runs)
        if brief_runs:
            selected_brief_run = st.selectbox(
                "Inspect brief QC run",
                options=brief_runs,
                format_func=lambda r: (
                    f"v{_to_int(r.get('run_version'), 0)}"
                    f" | {str(r.get('created_at') or '')[:19]}"
                    f" | {str(r.get('brief_id') or '')}"
                ),
                key="qc_brief_breakdown_version_pick",
            )
            detail = build_brief_qc_breakdown(
                qc_runs,
                brief_qc_rows,
                selected_run=selected_brief_run,
            )
            if detail:
                b_show_high_only = st.checkbox(
                    "Show only High-severity brief findings",
                    value=True,
                    key="qc_brief_show_only_high",
                )
                findings_df = pd.DataFrame(detail["rows"])
                if b_show_high_only and not findings_df.empty and "severity" in findings_df.columns:
                    findings_df = findings_df[findings_df["severity"].astype(str).str.title() == "High"]

                finding_cols = [
                    "version",
                    "severity",
                    "issue_type",
                    "section",
                    "claim_text",
                    "notes",
                    "status",
                ]
                st.dataframe(
                    findings_df.reindex(columns=finding_cols) if not findings_df.empty else pd.DataFrame(columns=finding_cols),
                    width='stretch',
                    hide_index=True,
                )
        else:
            st.caption("No brief-level QC runs available.")
else:
    st.info("Run `python scripts/run_quality.py` to populate QC details.")

