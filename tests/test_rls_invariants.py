"""Static invariants for the RLS boundary declared in ``sql/004_rls.sql``.

The README claims "anonymous sees 0 rows" and that ``service_role`` is granted
separately. These tests turn those prose claims into assertions over the raw
migration SQL — read as text, with no database, no Supabase client, no
credentials and no network. Each assertion fails the moment the SQL stops
making the claim true, so the security statement is backed by a mechanism
rather than by prose.

The mutation-control test proves the suite is not vacuous: it deletes one
``enable row level security`` line in memory and requires the same helper to
flag exactly that table.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"
RLS_SQL = SQL_DIR / "004_rls.sql"
SERVICE_ROLE_SQL = SQL_DIR / "005_service_role_grants.sql"

# Every table that must have RLS enabled, as (schema, table).
RLS_TABLES: list[tuple[str, str]] = [
    ("analytics", "organizations"),
    ("analytics", "api_keys"),
    ("analytics", "users"),
    ("analytics", "events"),
    ("analytics", "subscriptions"),
    ("analytics", "org_members"),
    ("experiments", "experiments"),
    ("experiments", "variants"),
    ("experiments", "assignments"),
    ("experiments", "metrics"),
]

# Tables that a user may read through an RLS policy. ``api_keys`` is
# intentionally absent: with RLS on and no policy, the default is deny.
POLICY_TABLES = {
    "analytics.org_members",
    "analytics.organizations",
    "analytics.users",
    "analytics.events",
    "analytics.subscriptions",
    "experiments.experiments",
    "experiments.variants",
    "experiments.assignments",
    "experiments.metrics",
}


def _norm(text: str) -> str:
    """Collapse whitespace so multi-line SQL statements match a single pattern."""
    return re.sub(r"\s+", " ", text).strip().lower()


def missing_rls_tables(sql: str) -> list[tuple[str, str]]:
    """Tables of :data:`RLS_TABLES` whose ``enable row level security`` is absent."""
    norm = _norm(sql)
    missing: list[tuple[str, str]] = []
    for schema, table in RLS_TABLES:
        if f"alter table {schema}.{table} enable row level security" not in norm:
            missing.append((schema, table))
    return missing


def _statements(norm_sql: str, verb: str) -> list[str]:
    """Return every ``<verb> ... ;`` statement in already-normalized SQL."""
    return re.findall(rf"{verb}[^;]+;", norm_sql)


@pytest.fixture(scope="module")
def rls_sql() -> str:
    assert RLS_SQL.is_file(), f"missing migration: {RLS_SQL}"
    return RLS_SQL.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def service_role_sql() -> str:
    assert SERVICE_ROLE_SQL.is_file(), f"missing migration: {SERVICE_ROLE_SQL}"
    return SERVICE_ROLE_SQL.read_text(encoding="utf-8")


def test_every_table_enables_row_level_security(rls_sql: str) -> None:
    missing = missing_rls_tables(rls_sql)
    assert missing == [], f"RLS not enabled for: {missing}"


def test_mutation_control_removing_enable_rls_is_detected(rls_sql: str) -> None:
    mutated = re.sub(
        r"alter table analytics\.events\s+enable row level security;",
        "",
        rls_sql,
    )
    assert mutated != rls_sql, "mutation did not apply — the guard would be vacuous"
    assert ("analytics", "events") in missing_rls_tables(mutated)


def test_policy_covers_every_readable_table(rls_sql: str) -> None:
    norm = _norm(rls_sql)
    policy_tables = set(re.findall(r"create policy\s+\w+\s+on\s+([\w.]+)", norm))
    assert POLICY_TABLES <= policy_tables, POLICY_TABLES - policy_tables
    assert "analytics.api_keys" not in policy_tables


def test_anon_has_no_select_grant_on_api_keys(rls_sql: str) -> None:
    norm = _norm(rls_sql)
    exposed = [
        stmt
        for stmt in _statements(norm, "grant")
        if " select " in stmt and (" to anon" in stmt or "authenticated" in stmt)
    ]
    assert exposed, "expected at least one select grant (guards against a vacuous test)"
    for stmt in exposed:
        assert "api_keys" not in stmt, "api_keys must never be readable by anon"


def test_service_role_grants_are_separated_from_public_grants(
    rls_sql: str, service_role_sql: str
) -> None:
    # 004 grants to anon/authenticated; the elevated service_role grants live in 005.
    assert "to service_role" not in _norm(rls_sql)
    assert "to service_role" in _norm(service_role_sql)


def test_ingest_event_is_security_definer(rls_sql: str) -> None:
    norm = _norm(rls_sql)
    assert "function analytics.ingest_event" in norm
    assert "security definer" in norm
