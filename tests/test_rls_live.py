"""Live proof of the RLS boundary against the real Supabase project.

``tests/test_rls_invariants.py`` only reads the migration SQL as text; it can
prove that RLS is *declared*, never that the deployed database enforces it.
The README's claim "anonymous sees 0 rows" therefore had no mechanism behind
it. This module supplies that mechanism: it sends real PostgREST requests
signed with the public anon key and requires every RLS-protected table in the
exposed schemas to yield zero rows — or to reject the read outright.

The suite skips (does not fail) when credentials are absent, so ``uv run
pytest`` stays green in CI. It never reads, prints or asserts on key values;
only table names, HTTP status codes and row counts appear in output.

Endpoint shape verified against the hosted project (PostgREST)::

    GET  {SUPABASE_URL}/rest/v1/{table}?select=*&limit=1
         apikey: <anon>            # always
         Authorization: Bearer <anon>   # only for legacy JWT keys (eyJ...)
         Accept-Profile: analytics | experiments

    POST {SUPABASE_URL}/rest/v1/rpc/ingest_event   (control: bogus key hash)
"""

from __future__ import annotations

import json
import os
import secrets
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
TIMEOUT = 20

# Every table where ``sql/004_rls.sql`` enables row level security, with the
# schema that exposes it through PostgREST (``supabase/config.toml`` [api]).
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

# A read is a pass when it is either empty or explicitly forbidden.
REJECTED = {401, 403}


def _load_dotenv(path: Path) -> None:
    """Populate ``os.environ`` from a ``KEY=VALUE`` file without logging values."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv(ENV_PATH)

MISSING = [name for name in ("SUPABASE_URL", "SUPABASE_ANON_KEY") if not os.environ.get(name)]

pytestmark = pytest.mark.skipif(
    bool(MISSING),
    reason=(
        f"live RLS test needs {'+'.join(MISSING)} in the environment or {ENV_PATH.name}"
        " — skipping instead of failing so credential-free runs stay green"
    ),
)


def _headers(schema: str, key: str) -> dict[str, str]:
    headers = {
        "apikey": key,
        "Accept": "application/json",
        "Accept-Profile": schema,
        "Content-Profile": schema,
    }
    # Legacy Supabase keys are JWTs and belong in Authorization; newer
    # publishable keys are not JWTs and must travel only in ``apikey``.
    if key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


class Unreachable(RuntimeError):
    """The endpoint could not be contacted at all (DNS, TLS, timeout)."""


def _request(
    method: str, path: str, headers: dict[str, str], payload: dict | None
) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    if data is not None:
        headers = {**headers, "Content-Type": "application/json"}
    req = urllib.request.Request(
        f"{os.environ['SUPABASE_URL'].rstrip('/')}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except urllib.error.URLError as exc:
        raise Unreachable(str(exc.reason)) from exc


def _request_or_fail(
    method: str, path: str, schema: str, payload: dict | None = None
) -> tuple[int, str]:
    """Call the endpoint, turning a transport failure into a readable test failure."""
    try:
        return _request(method, path, _headers(schema, os.environ["SUPABASE_ANON_KEY"]), payload)
    except Unreachable as exc:
        pytest.fail(
            f"cannot reach SUPABASE_URL host ({exc}) — the live RLS check needs a "
            "resolvable Supabase project; this is a failure, not a pass"
        )


def _is_forbidden(status: int, body: str) -> bool:
    if status in REJECTED:
        return True
    lowered = body.lower()
    return "42501" in body or "permission denied" in lowered


@pytest.mark.parametrize(("schema", "table"), RLS_TABLES, ids=[f"{s}.{t}" for s, t in RLS_TABLES])
def test_anon_select_is_empty_or_forbidden(schema: str, table: str) -> None:
    """Anon must see no rows of any RLS table in an exposed schema."""
    status, body = _request_or_fail("GET", f"/rest/v1/{table}?select=*&limit=1", schema)

    if status == 200:
        try:
            rows = json.loads(body)
        except json.JSONDecodeError:
            pytest.fail(f"{schema}.{table}: HTTP 200 with a non-JSON body: {body[:200]}")
        print(f"{schema}.{table}: status=200 rows={len(rows)}")
        assert rows == [], (
            f"{schema}.{table}: anon read returned {len(rows)} row(s) — "
            "RLS is not enforcing the anon boundary"
        )
        return

    print(f"{schema}.{table}: status={status} rejected={_is_forbidden(status, body)}")
    assert _is_forbidden(status, body), (
        f"{schema}.{table}: unexpected anon response HTTP {status}: {body[:200]}"
    )


def test_anon_cannot_ingest_without_a_valid_key() -> None:
    """Control: the key-gated ingestion RPC must reject a bogus key hash.

    The RPC raises ``invalid api key`` before touching any table, so this probe
    can never write. It proves the endpoint is reachable *and* refusing, i.e.
    the empty reads above are not an artefact of a dead connection.
    """
    status, body = _request_or_fail(
        "POST",
        "/rest/v1/rpc/ingest_event",
        "analytics",
        {
            "p_key_hash": secrets.token_hex(32),
            "p_external_id": "rls-live-probe",
            "p_event_name": "rls_live_probe",
        },
    )

    print(f"ingest_event control: status={status} rejected={_is_forbidden(status, body)}")
    lowered = body.lower()
    assert _is_forbidden(status, body) or "invalid api key" in lowered, (
        f"ingest_event accepted a bogus key — unexpected HTTP {status}: {body[:200]}"
    )
