from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import streamlit as st
from scipy import stats

from supabase_client import query

st.set_page_config(page_title="Experiments", page_icon="🧪", layout="wide")

st.title("🧪 A/B Experiments")
st.caption(
    "Результаты считаются в SQL-вьюхе `experiments.v_results`; "
    "значимость — χ²-тест на таблице конверсий."
)

rows = query("experiments", "v_results")
if not rows:
    st.info("Нет экспериментов. Запусти `uv run python scripts/seed_events.py`.")
    st.stop()

df = pd.DataFrame(rows)

for exp_id, g in df.groupby("experiment_id"):
    st.subheader(g["experiment"].iloc[0])
    st.caption(f"status: {g['status'].iloc[0]}")

    table = g[["variant", "assigned", "converted", "conversion"]].copy()
    table["conversion"] = (table["conversion"] * 100).round(2)
    table.columns = ["Вариант", "Назначено", "Конверсий", "Конверсия %"]
    st.dataframe(table, width="stretch")

    control = g[g["variant"] == "control"]
    treatment = g[g["variant"] != "control"]
    if control.empty or treatment.empty:
        continue

    c = control.iloc[0]
    t = treatment.iloc[0]
    conv_c, n_c = int(c["converted"]), int(c["assigned"])
    conv_t, n_t = int(t["converted"]), int(t["assigned"])

    lift = (conv_t / n_t - conv_c / n_c) / (conv_c / n_c) if conv_c and n_c else None
    chi2, p = stats.chi2_contingency([[conv_c, n_c - conv_c], [conv_t, n_t - conv_t]])[:2]

    c1, c2 = st.columns(2)
    c1.metric("Lift vs control", f"{lift * 100:+.1f}%" if lift is not None else "—")
    c2.metric("p-value (χ²)", f"{p:.4f}")

    if p < 0.05:
        st.success("Статистически значимо (p < 0.05)")
    else:
        st.warning("Не значимо (p ≥ 0.05)")
    st.divider()
