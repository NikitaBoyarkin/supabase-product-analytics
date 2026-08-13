from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.express as px
import streamlit as st

from data import (
    PERIOD_END,
    PERIOD_START,
    active_users,
    conversion_by_channel,
    daily_active_users,
    get_data,
)

data = get_data()
users = data["users"]
events = data["events"]
subs = data["subscriptions"]

st.title("📊 Product Analytics")
st.caption("Synthetic SaaS demo — AARRR funnel, retention, and revenue.")

with st.sidebar:
    st.header("Filters")
    channels = sorted(users["channel"].unique())
    sel_channels = st.multiselect("Acquisition channel", channels, channels)
    dr = st.date_input(
        "Activity date range",
        value=(PERIOD_START.date(), PERIOD_END.date()),
        min_value=PERIOD_START.date(),
        max_value=PERIOD_END.date(),
    )

start, end = pd.Timestamp(dr[0]), pd.Timestamp(dr[1])
u_ids = users.loc[users["channel"].isin(sel_channels), "user_id"]
ev = events[
    (events["user_id"].isin(u_ids))
    & (events["event_date"] >= start)
    & (events["event_date"] <= end)
]
us = users[users["user_id"].isin(u_ids)]
sub_sel = subs[subs["user_id"].isin(u_ids)]

total_users = len(us)
paid = sub_sel["user_id"].nunique()
mrr_now = float(sub_sel.loc[~sub_sel["churned"], "mrr"].sum())
au30 = active_users(events[events["user_id"].isin(u_ids)], end - pd.Timedelta(days=30), end)
conv = paid / total_users if total_users else 0
stick = au30 / total_users if total_users else 0

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total users", f"{total_users:,}")
c2.metric("Paid users", f"{paid:,}", delta=f"{conv:.1%} conv.")
c3.metric("MRR (active)", f"${mrr_now:,.0f}")
c4.metric("Active (30d)", f"{au30:,}")
c5.metric("Stickiness (DAU30/total)", f"{stick:.0%}")

st.divider()

dau = daily_active_users(ev)
if not dau.empty:
    fig = px.area(dau.reset_index(name="DAU"), x="event_date", y="DAU", title="Daily Active Users")
    fig.update_layout(height=320, xaxis_title=None, yaxis_title=None)
    st.plotly_chart(fig, width="stretch")

c_l, c_r = st.columns(2)

signups = us.groupby("signup_month").size().reset_index(name="signups")
signups["signup_month"] = signups["signup_month"].astype(str)
fig_s = px.bar(signups, x="signup_month", y="signups", title="New signups by month")
fig_s.update_layout(height=360)
c_l.plotly_chart(fig_s, width="stretch")

conv_df = conversion_by_channel(us, events).reset_index()
conv_df["conversion"] = (conv_df["conversion"] * 100).round(1)
fig_c = px.bar(
    conv_df, x="channel", y="conversion", text="conversion", title="Signup→Paid conversion by channel (%)"
)
fig_c.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
fig_c.update_layout(height=360)
c_r.plotly_chart(fig_c, width="stretch")
