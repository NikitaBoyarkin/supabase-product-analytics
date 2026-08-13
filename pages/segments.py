from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import plotly.express as px
import streamlit as st

from data import get_data

data = get_data()
users = data["users"]
events = data["events"]
subs = data["subscriptions"]

st.title("🎯 Segments")
st.caption("Distributions, conversion, and ARPU across segment / channel / country / device.")

sub_uids = set(events.loc[events["event_name"] == "subscribe", "user_id"])
sub_rev = subs.groupby("user_id")["mrr"].first()
users_aug = users.copy()
users_aug["paid"] = users_aug["user_id"].isin(sub_uids)
users_aug["mrr"] = users_aug["user_id"].map(sub_rev).fillna(0)


def _dist(col: str):
    g = users_aug.groupby(col).agg(
        users=("user_id", "nunique"),
        paid=("paid", "sum"),
        mrr=("mrr", "sum"),
    )
    g["conversion %"] = (g["paid"] / g["users"] * 100).round(1)
    g["ARPU $"] = (g["mrr"] / g["users"]).round(2)
    return g.reset_index()


c1, c2 = st.columns(2)
for col, container in (("segment", c1), ("channel", c2)):
    g = _dist(col)
    fig = px.bar(g, x=col, y="users", title=f"Users by {col}", text="users")
    fig.update_traces(textposition="outside")
    fig.update_layout(height=320, yaxis_title=None)
    container.plotly_chart(fig, width="stretch")

c3, c4 = st.columns(2)
for col, container in (("country", c3), ("device", c4)):
    g = _dist(col)
    fig = px.bar(g, x=col, y="users", title=f"Users by {col}", text="users")
    fig.update_traces(textposition="outside")
    fig.update_layout(height=320, yaxis_title=None)
    container.plotly_chart(fig, width="stretch")

st.divider()
st.subheader("Conversion & ARPU by dimension")
dim = st.selectbox("Dimension", ["segment", "channel", "country", "device"])
g = _dist(dim)
st.dataframe(g, width="stretch", hide_index=True)
