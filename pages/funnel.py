from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data import FUNNEL_STEPS, funnel_counts, get_data

data = get_data()
users = data["users"]
events = data["events"]

st.title("🪣 Conversion Funnel")
st.caption("app_open → signup → activate → start_trial → subscribe")

with st.sidebar:
    st.header("Funnel filters")
    seg = st.multiselect("Segment", sorted(users["segment"].unique()), sorted(users["segment"].unique()))
    ch = st.multiselect("Channel", sorted(users["channel"].unique()), sorted(users["channel"].unique()))
    dev = st.multiselect("Device", sorted(users["device"].unique()), sorted(users["device"].unique()))
    ctry = st.multiselect("Country", sorted(users["country"].unique()), sorted(users["country"].unique()))

mask = (
    users["segment"].isin(seg)
    & users["channel"].isin(ch)
    & users["device"].isin(dev)
    & users["country"].isin(ctry)
)
u_sel = users.loc[mask, "user_id"]
ev = events[events["user_id"].isin(u_sel)]

counts = funnel_counts(ev)
total = counts.get("app_open", 0) or 1

fig = go.Figure(
    go.Funnel(
        y=FUNNEL_STEPS,
        x=[counts[s] for s in FUNNEL_STEPS],
        textinfo="value+percent initial",
        marker={"color": "#4DA8DA"},
    )
)
fig.update_layout(height=400)
st.plotly_chart(fig, width="stretch")

st.divider()
st.subheader("Step-by-step drop-off")
rows = []
prev = None
for step in FUNNEL_STEPS:
    c = counts[step]
    step_conv = c / prev if prev else 1.0
    drop = 1 - step_conv if prev else 0.0
    overall = c / total
    rows.append(
        {
            "step": step,
            "users": c,
            "step conversion": f"{step_conv:.1%}",
            "overall conversion": f"{overall:.1%}",
            "drop-off": f"{drop:.1%}" if prev else "—",
        }
    )
prev = c
st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
