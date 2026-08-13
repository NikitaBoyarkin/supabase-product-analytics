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

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

_client: Client | None = None


def get_client() -> Client:
    """Client bound to the signed-in session (or anon if not signed in)."""
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_ANON_KEY:
            raise RuntimeError("SUPABASE_URL / SUPABASE_ANON_KEY not set in .env")
        _client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    return _client


def get_service_client() -> Client:
    """Admin client (bypasses RLS) — used only by the seed script."""
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY not set in .env")
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


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
