import streamlit as st

from supabase_client import is_authenticated, sign_in, sign_out

st.set_page_config(
    page_title="Product Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

DEMO_EMAIL = "demo@acme-saas.dev"
DEMO_PASSWORD = "demo-password-123"

if not is_authenticated():
    st.title("🔐 Product Analytics — вход")
    st.caption(
        "Демо-доступ: email/password ниже (создаётся `scripts/seed_events.py`). "
        "Все запросы идут через RLS — юзер видит только свою организацию."
    )
    with st.form("login"):
        email = st.text_input("Email", value=DEMO_EMAIL)
        password = st.text_input("Password", type="password", value=DEMO_PASSWORD)
        submitted = st.form_submit_button("Войти")
    if submitted:
        try:
            sign_in(email, password)
            st.rerun()
        except Exception as e:  # noqa: BLE001
            st.error(f"Ошибка входа: {e}")
    st.stop()

overview = st.Page("pages/overview.py", title="Overview", icon="🏠")
funnel = st.Page("pages/funnel.py", title="Funnel", icon="🪣")
retention = st.Page("pages/retention.py", title="Retention", icon="🔁")
revenue = st.Page("pages/revenue.py", title="Revenue", icon="💰")
segments = st.Page("pages/segments.py", title="Segments", icon="🎯")
experiments = st.Page("pages/experiments.py", title="Experiments", icon="🧪")

pg = st.navigation(
    [overview, funnel, retention, revenue, segments, experiments],
    position="sidebar",
)
st.sidebar.divider()
st.sidebar.caption("Supabase-backed • RLS-scoped • demo org")
if st.sidebar.button("Выйти"):
    sign_out()
    st.rerun()
pg.run()
