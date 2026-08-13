from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.express as px
import streamlit as st

from data import PLAN_MRR, arpu, get_data, mrr_series

data = get_data()
users = data["users"]
subs = data["subscriptions"]

st.title("💰 Revenue")
st.caption("MRR growth, plan mix, ARPU, and logo churn.")

with st.sidebar:
    st.header("Filters")
    channels = sorted(users["channel"].unique())
    sel_channels = st.multiselect("Acquisition channel", channels, channels)

u_ids = users.loc[users["channel"].isin(sel_channels), "user_id"]
sub_sel = subs[subs["user_id"].isin(u_ids)]
us = users[users["user_id"].isin(u_ids)]

ms = mrr_series(sub_sel)
current_mrr = float(ms["mrr"].iloc[-1]) if not ms.empty else 0.0
paid = sub_sel["user_id"].nunique()
churned = int(sub_sel["churned"].sum())
logo_churn = churned / max(paid, 1)
arpu_val = arpu(sub_sel, us)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Current MRR", f"${current_mrr:,.0f}")
c2.metric("Paid users (ever)", f"{paid:,}")
c3.metric("ARPU (per total user)", f"${arpu_val:,.2f}")
c4.metric("Logo churn (period)", f"{logo_churn:.1%}", delta="-" if logo_churn > 0 else "0")

st.divider()

fig = px.line(ms, x="month", y="mrr", title="MRR growth", markers=True)
fig.update_layout(height=340, xaxis_title=None, yaxis_title="MRR ($)")
st.plotly_chart(fig, width="stretch")

st.subheader("MRR by plan")
plans = list(PLAN_MRR.keys())
fig2 = px.bar(
    ms, x="month", y=plans, title="MRR by plan (stacked)", barmode="stack"
)
fig2.update_layout(height=360, xaxis_title=None, yaxis_title="MRR ($)")
st.plotly_chart(fig2, width="stretch")

with st.expander("Raw monthly MRR table"):
    st.dataframe(ms, width="stretch", hide_index=True)
