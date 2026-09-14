"""Supabase transport layer for the Product Analytics dashboard.

The dashboard authenticates a demo user (email/password) and runs every query
through Row Level Security: the user only ever sees rows belonging to their
organization. No service-role key is used at runtime — it is only needed by
``scripts/seed_events.py`` for admin operations.
"""

from __future__ import annotations

import os
from pathlib import Path

from supabase import Client, create_client

_ENV_PATH = Path(__file__).parent / ".env"


def _load_env() -> None:
    if not _ENV_PATH.exists():
        return
    for line in _ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_env()

# Service-role key is only used by the seed script (local .env), so it can stay
# a module constant. The dashboard keys are read lazily in get_client() instead —
# Streamlit Cloud caches imported modules between reruns, so reading secrets at
# import time would miss secrets added after the app started.
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

_client: Client | None = None


def _get_secret(key: str) -> str:
    """Read from env, falling back to st.secrets (Streamlit Cloud).

    Called lazily on every client creation so secrets added after app start are
    picked up without a full process restart.
    """
    value = os.environ.get(key, "")
    if value:
        return value
    try:
        import streamlit as st

        return st.secrets.get(key, "")
    except Exception:  # noqa: BLE001 — no st.secrets outside Streamlit runtime
        return ""


def get_client() -> Client:
    """Client bound to the signed-in session (or anon if not signed in)."""
    global _client
    if _client is None:
        url = _get_secret("SUPABASE_URL")
        anon = _get_secret("SUPABASE_ANON_KEY")
        if not url or not anon:
            raise RuntimeError(
                "SUPABASE_URL / SUPABASE_ANON_KEY not set — add to .env "
                "or Streamlit Cloud → Settings → Secrets"
            )
        _client = create_client(url, anon)
    return _client


def get_service_client() -> Client:
    """Admin client (bypasses RLS) — used only by the seed script."""
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY not set in .env")
    return create_client(_get_secret("SUPABASE_URL"), SUPABASE_SERVICE_ROLE_KEY)


def sign_in(email: str, password: str) -> None:
    get_client().auth.sign_in_with_password({"email": email, "password": password})


def sign_out() -> None:
    get_client().auth.sign_out()


def is_authenticated() -> bool:
    try:
        return get_client().auth.get_session() is not None
    except Exception:
        return False


_PAGE = 1000  # PostgREST db-max-rows cap on Supabase


def send_ingest_event(
    user_id: str,
    event_name: str,
    properties: dict | None = None,
    timestamp: str | None = None,
) -> dict:
    """POST a custom event to the Edge Function ingest endpoint (server-side).

    Returns the parsed JSON response (``{"accepted": true, "event_id": ...}`` on
    success, an ``{"error": ...}`` body on a 4xx/5xx). Raises RuntimeError when
    the endpoint is unreachable or required secrets are missing.
    """
    import json
    import urllib.error
    import urllib.request

    base = _get_secret("SUPABASE_URL")
    api_key = _get_secret("INGEST_API_KEY")
    if not base or not api_key:
        raise RuntimeError(
            "SUPABASE_URL / INGEST_API_KEY not set — add to .env or secrets"
        )
    url = f"{base.rstrip('/')}/functions/v1/ingest"

    payload: dict = {"user_id": str(user_id), "event_name": event_name}
    if properties:
        payload["properties"] = properties
    if timestamp:
        payload["timestamp"] = timestamp

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:  # noqa: BLE001 — non-JSON error body
            return {"error": f"HTTP {e.code}"}
    except urllib.error.URLError as e:
        raise RuntimeError(f"ingest unreachable: {e.reason}") from e


def query(schema: str, table: str, columns: str = "*") -> list[dict]:
    """RLS-scoped select against a table/view in a custom schema.

    Paginates in chunks of ``_PAGE`` because Supabase caps a single PostgREST
    response at 1000 rows (``db-max-rows``).
    """
    rows: list[dict] = []
    offset = 0
    while True:
        page = (
            get_client()
            .schema(schema)
            .from_(table)
            .select(columns)
            .range(offset, offset + _PAGE - 1)
            .execute()
            .data
        )
        if not page:
            break
        rows.extend(page)
        if len(page) < _PAGE:
            break
        offset += _PAGE
    return rows
