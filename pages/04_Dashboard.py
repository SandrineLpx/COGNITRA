import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import altair as alt
import ast
from src.storage import load_records
from src.dedupe import dedupe_records


# ── Pure helpers (unit-testable) ──────────────────────────────────────────

def get_effective_date(df: pd.DataFrame) -> pd.Series:
    """Return best available date: event_day > publish_date > created_at."""
    if "event_day" in df.columns:
        return df["event_day"]
    pub = pd.to_datetime(df.get("publish_date"), errors="coerce", utc=True).dt.tz_convert(None)
    cre = pd.to_datetime(df.get("created_at"), errors="coerce", utc=True).dt.tz_convert(None)
    return pub.combine_first(cre).dt.normalize()


def _safe_list(val):
    """Ensure val is a list. Parses stringified lists; returns [] on failure."""
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        s = val.strip()
        if s.startswith("["):
            try:
                parsed = ast.literal_eval(s)
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []
        return [s] if s else []
    return []


def explode_list_column(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Safely explode a list column. Returns long-form df with col values as strings."""
    if col not in df.columns:
        return pd.DataFrame(columns=df.columns)
    out = df.copy()
    out[col] = out[col].apply(_safe_list)
    out = out.explode(col)
    out[col] = out[col].astype(str).str.strip()
    out = out[out[col].ne("") & out[col].ne("None") & out[col].ne("nan")]
    return out


def weighted_explode(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Explode list column with weight = 1/len(list) per record to avoid double-counting."""
    if col not in df.columns:
        return pd.DataFrame(columns=list(df.columns) + ["_weight"])
    out = df.copy()
    out[col] = out[col].apply(_safe_list)
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

st.set_page_config(page_title="Dashboard", layout="wide")
st.title("Dashboard")

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
        pd.Series(df.get("topics", pd.Series(dtype=object))).apply(_safe_list).explode().dropna().astype(str).unique().tolist()
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
    excl = df["exclude_from_brief"].fillna(False) if "exclude_from_brief" in df.columns else pd.Series(False, index=df.index)
    mask = mask & (~excl)
if sel_topics:
    topic_set = set(sel_topics)
    topic_hit = pd.Series(
        [bool(set(_safe_list(x)) & topic_set) for x in df.get("topics", [])],
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
k5.metric("Excluded", int(fdf.get("exclude_from_brief", pd.Series(False)).fillna(False).sum()))
k6.metric("High Priority", int((fdf.get("priority") == "High").sum()) if "priority" in fdf else 0)

# ── Monthly Histogram ──────────────────────────────────────────────────────
st.subheader("Monthly Record Volume (Histogram)")
monthly = fdf.dropna(subset=["event_day"]).copy()
if not monthly.empty:
    monthly["event_month"] = monthly["event_day"].dt.to_period("M").dt.to_timestamp()
    monthly_hist = monthly.groupby("event_month").size().reset_index(name="count")
    chart = (
        alt.Chart(monthly_hist)
        .mark_bar(color="#1565c0")
        .encode(
            x=alt.X("event_month:T", title="Month"),
            y=alt.Y("count:Q", title="Records"),
            tooltip=["event_month:T", "count:Q"],
        )
        .properties(height=280)
    )
    st.altair_chart(chart, use_container_width=True)
else:
    st.caption("No dated records for monthly histogram.")

# ── Region x Topic Heatmap ────────────────────────────────────────────────
st.subheader("Region x Topic Heatmap")
if "regions_relevant_to_kiekert" in fdf and "topics" in fdf:
    hm = fdf[["regions_relevant_to_kiekert", "topics"]].copy()
    hm["regions_relevant_to_kiekert"] = hm["regions_relevant_to_kiekert"].apply(_safe_list)
    hm["topics"] = hm["topics"].apply(_safe_list)
    hm = hm.explode("regions_relevant_to_kiekert").explode("topics").dropna()
    if not hm.empty:
        ct = pd.crosstab(hm["regions_relevant_to_kiekert"], hm["topics"])
        fig, ax = plt.subplots(figsize=(8, 2.8))
        im = ax.imshow(ct.values, aspect="auto")
        ax.set_xticks(range(len(ct.columns)))
        ax.set_xticklabels(ct.columns, rotation=35, ha="right", fontsize=8)
        ax.set_yticks(range(len(ct.index)))
        ax.set_yticklabels(ct.index, fontsize=8)
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
                color=alt.Color(
                    "color_group:N",
                    scale=alt.Scale(
                        domain=["Rising", "Falling", "Flat"],
                        range=["#2e7d32", "#d32f2f", "#9e9e9e"],
                    ),
                    legend=None,
                ),
                tooltip=["topic", "prior", "recent", "delta", "pct_change", "class"],
            )
            .properties(height=max(180, len(momentum) * 28))
        )
        rule = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color="gray").encode(x="x:Q")
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
            ax_c.barh(top.index, top.values, color="#1565c0")
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

# ── Priority Distribution Over Time + High-Ratio Line ────────────────────
st.subheader("Priority Distribution Over Time")
if not dated_rows.empty and "priority" in dated_rows:
    weekly = dated_rows.copy()
    weekly["week"] = week_start(weekly["event_day"])
    pri_weekly = weekly.groupby(["week", "priority"]).size().reset_index(name="count")
    if not pri_weekly.empty:
        pivot_pri = pri_weekly.pivot(index="week", columns="priority", values="count").fillna(0)
        for col in ["High", "Medium", "Low"]:
            if col not in pivot_pri.columns:
                pivot_pri[col] = 0
        pivot_pri = pivot_pri[["High", "Medium", "Low"]]

        # Stacked bar chart
        fig_p, ax_p = plt.subplots(figsize=(8, 3))
        pivot_pri.plot.bar(stacked=True, ax=ax_p, color={"High": "#d32f2f", "Medium": "#f9a825", "Low": "#2e7d32"})
        ax_p.set_xlabel("Week")
        ax_p.set_ylabel("Records")
        ax_p.set_title("Priority Distribution by Week")
        ax_p.set_xticklabels([d.strftime("%b %d") for d in pivot_pri.index], rotation=35, ha="right", fontsize=8)
        ax_p.legend(title="Priority")
        fig_p.tight_layout()
        st.pyplot(fig_p)

        # High-ratio + volatility index line chart
        totals = pivot_pri.sum(axis=1).clip(lower=1)
        ratio_df = pd.DataFrame({
            "Week": pivot_pri.index,
            "High Ratio": (pivot_pri["High"] / totals).round(2),
            "Volatility Index": ((pivot_pri["High"] + 0.5 * pivot_pri["Medium"]) / totals).round(2),
        }).set_index("Week")

        st.caption("High Ratio = High / Total per week. Volatility Index = (High + 0.5 * Medium) / Total.")
        st.line_chart(ratio_df)
    else:
        st.caption("Not enough data for priority chart.")
else:
    st.caption("Not enough dated records for priority chart.")

# ── Drilldown ─────────────────────────────────────────────────────────────
st.subheader("Drilldown")
show_cols = [
    "record_id",
    "title",
    "source_type",
    "priority",
    "confidence",
    "review_status",
    "publish_date",
    "exclude_from_brief",
]
show_cols = [c for c in show_cols if c in fdf.columns]
st.dataframe(fdf[show_cols].sort_values(by=["publish_date"], ascending=False), use_container_width=True, hide_index=True)

csv = fdf.to_csv(index=False).encode("utf-8")
st.download_button(
    "Download filtered CSV",
    data=csv,
    file_name="dashboard_filtered_records.csv",
    mime="text/csv",
)
