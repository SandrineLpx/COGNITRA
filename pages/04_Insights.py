import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import altair as alt
from src.storage import load_records
from src.dedupe import dedupe_records
from src.quality import QUALITY_RUNS_LOG, _read_jsonl
from src.ui_helpers import enforce_navigation_lock, safe_list, workflow_ribbon


# ── Pure helpers (unit-testable) ──────────────────────────────────────────

def get_effective_date(df: pd.DataFrame) -> pd.Series:
    """Return best available date: event_day > publish_date > created_at."""
    if "event_day" in df.columns:
        return df["event_day"]
    pub = pd.to_datetime(df.get("publish_date"), errors="coerce", utc=True).dt.tz_convert(None)
    cre = pd.to_datetime(df.get("created_at"), errors="coerce", utc=True).dt.tz_convert(None)
    return pub.combine_first(cre).dt.normalize()


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


# Placeholder alias map for company name canonicalization.
# Add entries as needed, e.g., {"General Motors": "GM", "Bayerische Motoren Werke": "BMW"}.
_COMPANY_ALIASES: dict[str, str] = {}


def canonicalize_company(name: str) -> str:
    """Normalize company name via alias map."""
    return _COMPANY_ALIASES.get(name.strip(), name.strip())


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


# ── Page setup ────────────────────────────────────────────────────────────

st.set_page_config(page_title="Insights", layout="wide")
enforce_navigation_lock("insights")
st.title("Insights")
workflow_ribbon(4)
st.caption("Exploratory analytics — not required for weekly executive output.")
st.caption("Optional analytics and trend monitoring for approved intelligence records.")

with st.sidebar:
    st.subheader("Data Mode")
    show_canonical_only = st.checkbox("Show canonical stories only", value=False)
    st.caption("Canonical: deduplicated (one story per source group).")

records = load_records()
if not records:
    st.info("No records yet.")
    st.stop()

if show_canonical_only:
    canonical, dups = dedupe_records(records)
    records = canonical
    st.info(f"Showing {len(records)} canonical records (suppressed {len(dups)} duplicates).")

df = pd.json_normalize(records)
if df.empty:
    st.info("No records after filters.")
    st.stop()

# Compute effective date once
publish_dt = pd.to_datetime(df.get("publish_date"), errors="coerce", utc=True).dt.tz_convert(None)
created_dt = pd.to_datetime(df.get("created_at"), errors="coerce", utc=True).dt.tz_convert(None)
event_ts = publish_dt.combine_first(created_dt)
df["publish_date_dt"] = publish_dt
df["created_at_dt"] = created_dt
df["event_day"] = event_ts.dt.normalize()

today = pd.Timestamp.today().normalize()
default_from = (today - pd.Timedelta(days=30)).date()
default_to = today.date()

st.subheader("Filters")
f1, f2, f3, f4 = st.columns(4)
with f1:
    date_from = st.date_input("From", value=default_from)
with f2:
    date_to = st.date_input("To", value=default_to)
with f3:
    statuses = sorted(df["review_status"].dropna().astype(str).unique().tolist()) if "review_status" in df else []
    sel_status = st.multiselect("Review Status", statuses, default=statuses)
with f4:
    sources = sorted(df["source_type"].dropna().astype(str).unique().tolist()) if "source_type" in df else []
    sel_sources = st.multiselect("Source Type", sources, default=sources)

t1, t2 = st.columns(2)
with t1:
    all_topics = sorted(
        pd.Series(df.get("topics", pd.Series(dtype=object))).apply(safe_list).explode().dropna().astype(str).unique().tolist()
    )
    all_topics = [t for t in all_topics if t and t not in ("", "None", "nan")]
    sel_topics = st.multiselect("Topics", all_topics, default=all_topics)
with t2:
    only_brief_included = st.checkbox("Exclude suppressed/duplicate records", value=True)

mask = pd.Series(True, index=df.index)
mask = mask & (df["event_day"] >= pd.Timestamp(date_from)) & (df["event_day"] <= pd.Timestamp(date_to))
if sel_status and "review_status" in df:
    mask = mask & df["review_status"].astype(str).isin(sel_status)
if sel_sources and "source_type" in df:
    mask = mask & df["source_type"].astype(str).isin(sel_sources)
if only_brief_included:
    excl = df["is_duplicate"].fillna(False) if "is_duplicate" in df.columns else pd.Series(False, index=df.index)
    mask = mask & (~excl)
if sel_topics:
    topic_set = set(sel_topics)
    topic_hit = pd.Series(
        [bool(set(safe_list(x)) & topic_set) for x in df.get("topics", [])],
        index=df.index,
    )
    mask = mask & topic_hit

fdf = df[mask].copy()
if fdf.empty:
    st.warning("No records match current filters.")
    st.stop()

# ── KPI ───────────────────────────────────────────────────────────────────
st.subheader("KPI")
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Records", len(fdf))
k2.metric("Approved", int((fdf.get("review_status") == "Approved").sum()) if "review_status" in fdf else 0)
k3.metric("Pending", int((fdf.get("review_status") == "Pending").sum()) if "review_status" in fdf else 0)
k4.metric("Disapproved", int((fdf.get("review_status") == "Disapproved").sum()) if "review_status" in fdf else 0)
k5.metric("Duplicates", int(fdf.get("is_duplicate", pd.Series(False)).fillna(False).sum()))
k6.metric("High Priority", int((fdf.get("priority") == "High").sum()) if "priority" in fdf else 0)

# ── Weekly Histogram ───────────────────────────────────────────────────────
st.subheader("Weekly Record Volume (Histogram)")
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
    st.altair_chart(chart, use_container_width=True)
else:
    st.caption("No dated records for weekly histogram.")

# ── Region x Topic Heatmap ────────────────────────────────────────────────
st.subheader("Region x Topic Heatmap")
if "regions_relevant_to_kiekert" in fdf and "topics" in fdf:
    hm = fdf[["regions_relevant_to_kiekert", "topics"]].copy()
    hm["regions_relevant_to_kiekert"] = hm["regions_relevant_to_kiekert"].apply(safe_list)
    hm["topics"] = hm["topics"].apply(safe_list)
    hm = hm.explode("regions_relevant_to_kiekert").explode("topics").dropna()
    if not hm.empty:
        ct = pd.crosstab(hm["regions_relevant_to_kiekert"], hm["topics"])
        fig, ax = plt.subplots(figsize=(8, 2.8))
        heatmap_cmap = LinearSegmentedColormap.from_list(
            "region_topic_heatmap",
            ["#ffffcc", "#a1dab4", "#41b6c4", "#2c7fb8", "#253494"],
        )
        im = ax.imshow(ct.values, aspect="auto", cmap=heatmap_cmap)
        ax.set_xticks(range(len(ct.columns)))
        ax.set_xticklabels(ct.columns, rotation=35, ha="right", fontsize=8)
        ax.set_yticks(range(len(ct.index)))
        ax.set_yticklabels(ct.index, fontsize=8)
        label_size = plt.rcParams.get("axes.labelsize", 10)
        ax.set_xlabel("Topic", fontsize=label_size)
        ax.set_ylabel("Region", fontsize=label_size)
        ax.set_title("Signals by Footprint Region and Topic")
        fig.colorbar(im, ax=ax)
        fig.tight_layout()
        st.pyplot(fig)
    else:
        st.caption("No region-topic pairs for heatmap.")

# ── Topic Momentum (weighted, classified, Altair) ─────────────────────────
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
        f"Prior: {date_min.strftime('%b %d')} – {(midpoint - pd.Timedelta(days=1)).strftime('%b %d')}  |  "
        f"Recent: {midpoint.strftime('%b %d')} – {date_max.strftime('%b %d')}"
    )

    # Weighted explode: each record contributes weight 1 split across its topics
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

        # Altair horizontal bar chart colored by delta sign
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
            .properties(height=max(180, len(momentum) * 28))
        )
        rule = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule().encode(x="x:Q")
        st.altair_chart(chart + rule, use_container_width=True)

        # Detail table below
        st.dataframe(
            momentum[["topic", "prior", "recent", "delta", "pct_change", "class"]].sort_values("delta", ascending=False),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("Not enough topic data for momentum chart.")
else:
    st.caption("Not enough dated records for momentum chart.")

# ── Top Company Mentions (canonicalized, unique per record) ───────────────
st.subheader("Top Company Mentions")
if "companies_mentioned" in fdf:
    # Explode safely, then canonicalize and dedupe within each record
    co_df = fdf[["companies_mentioned"]].copy()
    co_df["_idx"] = range(len(co_df))
    co_long = explode_list_column(co_df, "companies_mentioned")
    if not co_long.empty:
        co_long["companies_mentioned"] = co_long["companies_mentioned"].apply(canonicalize_company)
        # Unique per record: drop duplicate company within same record
        co_long = co_long.drop_duplicates(subset=["_idx", "companies_mentioned"])
        top = co_long["companies_mentioned"].value_counts().head(10).sort_values()
        if not top.empty:
            fig_c, ax_c = plt.subplots(figsize=(8, max(2.5, len(top) * 0.35)))
            ax_c.barh(top.index, top.values)
            ax_c.set_xlabel("Records mentioning company")
            ax_c.set_title("Top 10 Companies (unique per record)")
            fig_c.tight_layout()
            st.pyplot(fig_c)
        else:
            st.caption("No company mentions in filtered records.")
    else:
        st.caption("No company mentions in filtered records.")
else:
    st.caption("No company data available.")

# ── Quality Score Trend ───────────────────────────────────────────────────
st.subheader("Extraction Quality Score")
st.caption("Quality scores from automated QC runs. Higher is better (0–100). Run `python scripts/run_quality.py` to generate data.")

qc_runs = _read_jsonl(QUALITY_RUNS_LOG)
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

    q1, q2, q3, q4 = st.columns(4)
    q1.metric(
        "Overall Score",
        f"{latest.get('weighted_overall_score', '—')}",
        delta=_delta("weighted_overall_score"),
    )
    q2.metric(
        "Evidence Grounding",
        f"{latest.get('KPI-R3', 0):.0%}",
        delta=f"{_delta('KPI-R3'):+.0%}" if _delta("KPI-R3") is not None else None,
    )
    q3.metric(
        "Canonicalization",
        f"{latest.get('KPI-R4', 0):.0%}",
        delta=f"{_delta('KPI-R4'):+.0%}" if _delta("KPI-R4") is not None else None,
    )
    q4.metric(
        "Geo Determinism",
        f"{latest.get('KPI-R5', 0):.0%}",
        delta=f"{_delta('KPI-R5'):+.0%}" if _delta("KPI-R5") is not None else None,
    )

    # --- Quality score trend line chart ---
    if "created_at" in qc_df.columns and len(qc_df) >= 2:
        qc_df["run_date"] = pd.to_datetime(qc_df["created_at"], errors="coerce")
        score_cols = ["weighted_overall_score", "weighted_record_score", "weighted_brief_score"]
        available = [c for c in score_cols if c in qc_df.columns]
        if available:
            plot_df = qc_df[["run_date"] + available].dropna(subset=["run_date"])
            melted = plot_df.melt(id_vars="run_date", value_vars=available, var_name="Score Type", value_name="Score")
            melted["Score Type"] = melted["Score Type"].map({
                "weighted_overall_score": "Overall",
                "weighted_record_score": "Record",
                "weighted_brief_score": "Brief",
            })

            # Threshold reference lines
            thresholds = pd.DataFrame([
                {"Score": 80, "label": "Good (80)"},
                {"Score": 60, "label": "Warning (60)"},
            ])

            lines = alt.Chart(melted).mark_line(point=True, strokeWidth=2).encode(
                x=alt.X("run_date:T", title="QC Run Date"),
                y=alt.Y("Score:Q", title="Quality Score", scale=alt.Scale(domain=[0, 100])),
                color=alt.Color("Score Type:N", scale=alt.Scale(
                    domain=["Overall", "Record", "Brief"],
                    range=["#1f77b4", "#2ca02c", "#ff7f0e"],
                )),
                tooltip=["run_date:T", "Score Type:N", "Score:Q"],
            )

            rules = alt.Chart(thresholds).mark_rule(strokeDash=[4, 4], opacity=0.5).encode(
                y="Score:Q",
                color=alt.Color("label:N", scale=alt.Scale(
                    domain=["Good (80)", "Warning (60)"],
                    range=["#2ca02c", "#d62728"],
                ), legend=alt.Legend(title="Thresholds")),
            )

            st.altair_chart(lines + rules, use_container_width=True)
    else:
        st.caption("Need at least 2 QC runs to show trend chart.")
else:
    st.info("No quality runs found. Run `python scripts/run_quality.py` to generate quality data.")

# ── Quality KPI Breakdown ─────────────────────────────────────────────────
st.subheader("Quality KPI Breakdown")
st.caption("Individual KPIs that compose the scores in the Extraction Quality Score graph above.")

_KPI_META = [
    # code, label, group, format, direction, target
    ("KPI-R1", "High-severity error rate",       "Record", "pct",   "lower",  "< 5%"),
    ("KPI-R2", "Medium-severity error rate",     "Record", "pct",   "lower",  "< 15%"),
    ("KPI-R3", "Evidence grounding pass rate",   "Record", "pct",   "higher", "> 80%"),
    ("KPI-R4", "Canonicalization pass rate",     "Record", "pct",   "higher", "> 90%"),
    ("KPI-R5", "Geo determinism pass rate",      "Record", "pct",   "higher", "> 80%"),
    ("weighted_record_score", "Record score",    "Record", "score", "higher", "≥ 80"),
    ("KPI-B1", "Ungrounded claims (count)",      "Brief",  "int",   "lower",  "= 0"),
    ("KPI-B2", "Overreach citations (count)",    "Brief",  "int",   "lower",  "= 0"),
    ("KPI-B3", "Uncertainty compliance rate",    "Brief",  "pct",   "higher", "> 80%"),
    ("KPI-B4", "Cross-record themes cited",      "Brief",  "int",   "higher", "↑ higher"),
    ("KPI-B5", "Action specificity (count)",     "Brief",  "int",   "higher", "↑ higher"),
    ("weighted_brief_score",  "Brief score",     "Brief",  "score", "higher", "≥ 80"),
    ("weighted_overall_score","Overall score",   "Overall","score", "higher", "≥ 80"),
]

if qc_runs and len(qc_runs) >= 1:
    latest_run = qc_runs[-1]
    prior_run  = qc_runs[-2] if len(qc_runs) >= 2 else {}

    rows = []
    for code, label, group, fmt, direction, target in _KPI_META:
        cur  = latest_run.get(code)
        prev = prior_run.get(code)

        # Format latest value
        if cur is None:
            val_str = "—"
        elif fmt == "pct":
            val_str = f"{cur:.0%}"
        elif fmt == "score":
            val_str = f"{cur:.1f}"
        else:
            val_str = str(int(cur))

        # Delta vs prior
        if cur is not None and prev is not None:
            delta = float(cur) - float(prev)
            if fmt == "pct":
                delta_str = f"{delta:+.0%}"
            elif fmt == "score":
                delta_str = f"{delta:+.1f}"
            else:
                delta_str = f"{delta:+.0f}"
            # Arrow: ✓ good move, ✗ bad move
            good = (direction == "higher" and delta > 0) or (direction == "lower" and delta < 0)
            flat = delta == 0
            arrow = "→" if flat else ("✓" if good else "✗")
            delta_str = f"{delta_str} {arrow}"
        else:
            delta_str = "—"

        rows.append({
            "Group": group,
            "KPI": code if code.startswith("KPI") else "Score",
            "Description": label,
            "Latest": val_str,
            "vs Prior": delta_str,
            "Target": target,
        })

    kpi_table = pd.DataFrame(rows)
    st.dataframe(kpi_table, use_container_width=True, hide_index=True)
else:
    st.info("Run `python scripts/run_quality.py` to populate quality KPI data.")

csv = fdf.to_csv(index=False).encode("utf-8")
st.download_button(
    "Download filtered records CSV",
    data=csv,
    file_name="dashboard_filtered_records.csv",
    mime="text/csv",
)
