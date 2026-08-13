"""Data layer for the Product Analytics dashboard.

API-compatible with the original ``streamlit-app/data.py`` so the existing
pages work unchanged — but the data now comes from Supabase Postgres through
RLS-scoped queries instead of an in-memory generator.

Heavy lifting (event stream, joins, RLS) lives in the database; the metric
helpers below are pure-pandas reshapers that keep the exact shapes the pages
expect. SQL-side analytics views are in ``sql/002_views.sql``.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from supabase_client import query

# --- Config (kept for page compatibility) ----------------------------------
PERIOD_START = pd.Timestamp("2024-01-01")
PERIOD_END = pd.Timestamp("2025-06-30")
FUNNEL_STEPS = ["app_open", "signup", "activate", "start_trial", "subscribe"]
PLAN_MRR = {"pro": 49, "business": 199, "enterprise": 999}


@st.cache_data(ttl=300, show_spinner="Загрузка данных из Supabase…")
def get_data() -> dict[str, pd.DataFrame]:
    """Fetch users / events / subscriptions via RLS-scoped SQL queries."""
    users_rows = query("analytics", "users")
    events_rows = query("analytics", "v_events")
    subs_rows = query("analytics", "v_subscriptions")

    users = pd.DataFrame(users_rows)
    if not users.empty:
        users["user_id"] = users["external_id"]
        users["signup_date"] = pd.to_datetime(users["created_at"], format="mixed").dt.tz_localize(None)
        props = users["properties"].apply(pd.Series)
        for col in ("channel", "country", "device", "segment"):
            if col not in props.columns:
                props[col] = None
            # Ingested users may lack a property key → NaN breaks sorted()/groupby
            props[col] = props[col].fillna("unknown")
        users = pd.concat(
            [users[["user_id", "signup_date"]], props[["channel", "country", "device", "segment"]]],
            axis=1,
        )
        users["signup_month"] = users["signup_date"].dt.to_period("M")
    else:
        users = pd.DataFrame(
            columns=["user_id", "signup_date", "channel", "country", "device", "segment", "signup_month"]
        )

    events = pd.DataFrame(events_rows)
    if not events.empty:
        events["event_date"] = pd.to_datetime(events["event_time"], format="mixed").dt.tz_localize(None)
    else:
        events = pd.DataFrame(columns=["user_id", "event_name", "event_date"])

    subs = pd.DataFrame(subs_rows)
    if not subs.empty:
        subs["start_date"] = pd.to_datetime(subs["start_date"])
        subs["churn_date"] = pd.to_datetime(subs["churn_date"])
        subs["churned"] = subs["churn_date"].notna()
    else:
        subs = pd.DataFrame(columns=["user_id", "plan", "mrr", "start_date", "churn_date", "churned"])

    return {"users": users, "events": events, "subscriptions": subs}


# --- Metric helpers (pure pandas, identical to streamlit-app/data.py) ------
def active_users(events: pd.DataFrame, start, end) -> int:
    """Distinct users with an `active` event in [start, end]."""
    mask = (
        (events["event_date"] >= pd.Timestamp(start))
        & (events["event_date"] <= pd.Timestamp(end))
        & (events["event_name"] == "active")
    )
    return int(events.loc[mask, "user_id"].nunique())


def daily_active_users(events: pd.DataFrame) -> pd.Series:
    act = events[events["event_name"] == "active"]
    if act.empty:
        return pd.Series(dtype=int)
    return act.groupby(act["event_date"].dt.date)["user_id"].nunique().sort_index()


def funnel_counts(events: pd.DataFrame) -> dict[str, int]:
    return {
        s: int(events.loc[events["event_name"] == s, "user_id"].nunique())
        for s in FUNNEL_STEPS
    }


def cohort_retention_matrix(
    users: pd.DataFrame, events: pd.DataFrame, max_months: int = 12
) -> pd.DataFrame:
    """Cohort retention %: rows = signup month, cols = months since signup."""
    act = events.loc[events["event_name"] == "active", ["user_id", "event_date"]].merge(
        users[["user_id", "signup_month"]], on="user_id"
    )
    act["event_month"] = act["event_date"].dt.to_period("M")
    act["month_index"] = act["event_month"].astype("int64") - act["signup_month"].astype("int64")
    act = act[(act["month_index"] >= 0) & (act["month_index"] <= max_months)]
    if act.empty:
        return pd.DataFrame()
    cohort_sizes = users.groupby("signup_month").size()
    mat = act.groupby(["signup_month", "month_index"])["user_id"].nunique().unstack(fill_value=0)
    mat = mat.reindex(cohort_sizes.index)
    pct = (mat.div(cohort_sizes, axis=0) * 100).round(1)
    return pct


def mrr_series(subs: pd.DataFrame) -> pd.DataFrame:
    """Monthly MRR (total + per plan) where subscription is active that month."""
    months = pd.period_range(PERIOD_START, PERIOD_END, freq="M")
    rows = []
    for m in months:
        me = m.to_timestamp("M")
        active = subs[(subs["start_date"] <= me) & ((~subs["churned"]) | (subs["churn_date"] > me))]
        row: dict = {"month": str(m), "mrr": float(active["mrr"].sum())}
        for p in PLAN_MRR:
            row[p] = float(active.loc[active["plan"] == p, "mrr"].sum())
        rows.append(row)
    return pd.DataFrame(rows)


def conversion_by_channel(users: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    sub_uids = set(events.loc[events["event_name"] == "subscribe", "user_id"])
    u = users.assign(paid=users["user_id"].isin(sub_uids))
    g = u.groupby("channel").agg(users=("user_id", "nunique"), paid=("paid", "sum"))
    g["conversion"] = (g["paid"] / g["users"]).round(4)
    return g


def arpu(subs: pd.DataFrame, users: pd.DataFrame, asof=PERIOD_END) -> float:
    active = subs[(subs["start_date"] <= asof) & ((~subs["churned"]) | (subs["churn_date"] > asof))]
    denom = max(len(users), 1)
    return float(active["mrr"].sum()) / denom
