from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import plotly.express as px
import streamlit as st

from data import csv_download, event_frequency, get_data
from supabase_client import send_ingest_event

data = get_data()
events = data["events"]

st.title("📡 Events")
st.caption(
    "Event stream by name + отправка произвольных событий через Edge Function "
    "ingest (REQ-011)."
)

st.subheader("Event frequency by name")
freq = event_frequency(events)
if freq.empty:
    st.info("Нет событий в выбранном срезе.")
else:
    fig = px.bar(freq, x="event_name", y="count", title="Events by name", text="count")
    fig.update_traces(textposition="outside")
    fig.update_layout(height=380, xaxis_title=None, yaxis_title="events")
    st.plotly_chart(fig, width="stretch")
    st.dataframe(freq, width="stretch", hide_index=True)
    csv_download(freq, filename="events_frequency.csv", key="events_freq")

st.divider()
st.subheader("Send a custom event via ingest")

with st.form("ingest_form"):
    c1, c2 = st.columns(2)
    user_id = c1.text_input("User id (external)", value="u00001")
    event_name = c2.text_input("Event name", value="feature_used")
    props = st.text_area(
        "Properties (JSON, optional)", value='{"feature": "export"}', height=90
    )
    submitted = st.form_submit_button("Отправить через ingest")

if submitted:
    if not event_name.strip():
        st.error("event_name обязателен.")
    else:
        parsed: dict | None = {}
        if props.strip():
            try:
                parsed = json.loads(props)
                if not isinstance(parsed, dict):
                    st.error("properties должен быть JSON-объектом.")
                    parsed = None
            except json.JSONDecodeError as e:
                st.error(f"Некорректный JSON: {e}")
                parsed = None
        if parsed is not None:
            try:
                resp = send_ingest_event(user_id.strip(), event_name.strip(), parsed)
            except RuntimeError as e:
                st.error(str(e))
                resp = None
            if resp is not None:
                if resp.get("accepted"):
                    st.success(
                        f"Событие принято (202), event_id={resp.get('event_id')}. "
                        "Данные обновлены."
                    )
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(f"Ingest вернул ошибку: {resp.get('error', resp)}")
