from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import plotly.graph_objects as go
import streamlit as st

from data import cohort_retention_matrix, csv_download, get_data

data = get_data()
users = data["users"]
events = data["events"]

st.title("🔁 Cohort Retention")
st.caption("% of users still active N months after signup, by signup cohort.")

with st.sidebar:
    st.header("Cohort filters")
    max_months = st.slider("Months since signup to track", 3, 18, 12)
    channels = sorted(users["channel"].unique())
    sel_channels = st.multiselect("Acquisition channel", channels, channels)

u_sel = users.loc[users["channel"].isin(sel_channels)]
ev_sel = events[events["user_id"].isin(u_sel["user_id"])]

pct = cohort_retention_matrix(u_sel, ev_sel, max_months=max_months)

if pct.empty:
    st.info("No active events in the selected slice.")
else:
    fig = go.Figure(
        go.Heatmap(
            z=pct.values,
            x=[f"M{c}" for c in pct.columns],
            y=[str(p) for p in pct.index],
            text=pct.values,
            texttemplate="%{text}%",
            textfont={"size": 10},
            colorscale="Blues",
            zmin=0,
            zmax=100,
            colorbar=dict(title="% active"),
        )
    )
    fig.update_layout(
        height=max(320, 26 * len(pct)),
        xaxis_title="Months since signup",
        yaxis_title="Signup cohort",
        title="Retention heatmap",
    )
    st.plotly_chart(fig, width="stretch")

    st.divider()
    st.subheader("Retention table (%)")
    disp = pct.copy()
    disp.index = disp.index.astype(str)
    st.dataframe(disp, width="stretch")
    csv_download(disp, filename="retention_matrix.csv", key="retention_matrix")
