# Product Analytics + A/B Experiments (Supabase)

A full-stack product analytics platform: a Streamlit dashboard that reads live
data from **Supabase Postgres** through **Row Level Security**, plus an
**Edge Function** ingest API that accepts events by API key. Includes a
concluded **A/B experiment** with SQL-computed conversion and a χ²
significance test.

The dashboard UI is reused from a standalone `streamlit-app` — only the data
layer changed, from an in-memory generator to RLS-scoped Postgres queries.

## Architecture

```
┌─────────────┐   POST /functions/v1/ingest (x-api-key)   ┌─────────────────┐
│ Client/seed │ ────────────────────────────────────────► │ Edge Function   │
└─────────────┘                                           │ (Deno, supabase)│
                                                          └────────┬────────┘
┌─────────────┐   email/password auth + SQL (RLS-scoped)  ┌────────▼────────┐
│ Streamlit   │ ◄────────────────────────────────────────► │ Supabase Postgres│
│ dashboard   │   (supabase-py, anon key)                  │ analytics +      │
└─────────────┘                                           │ experiments      │
                                                          └─────────────────┘
```

- **Schemas**: `analytics` (organizations, api_keys, users, events,
  subscriptions, org_members) and `experiments` (experiments, variants,
  assignments, metrics).
- **Analytics in the DB**: SQL views compute funnel, cohort retention, MRR,
  DAU, and channel conversion (`sql/002_views.sql`) — the dashboard reshapes,
  it doesn't aggregate.
- **A/B result in the DB**: `experiments.v_results` computes per-variant
  assigned/converted/conversion; the dashboard runs the χ² test on top.
- **Ingest**: `supabase/functions/ingest` validates an API key (stored as a
  SHA-256 hash, never plaintext) and inserts the event via a
  `security definer` function.

## Security model (RLS)

Every table has Row Level Security enabled. A user only ever sees rows of
their own organization:

```sql
-- analytics.my_orgs() resolves the caller's orgs from auth.uid()
create policy "org scoped select" on analytics.events
  for select using (organization_id in (select analytics.my_orgs()));
```

- **Anonymous** (no session): sees **0 rows** — verified.
- **Authenticated demo user**: sees only their org's rows.
- **Ingest**: the Edge Function calls `analytics.ingest_event(...)`, a
  `security definer` function that checks the API-key hash and inserts the
  event — no direct table access from the client.
- **Service role** (admin, seed only): full access via `005_service_role_grants`.

## Schema (migrations)

| Migration | Contents |
|---|---|
| `001_schema.sql` | `analytics` tables: organizations, api_keys (key_hash), users, events, subscriptions, org_members |
| `002_views.sql` | `v_events`, `v_subscriptions`, `v_funnel`, `v_retention_raw`, `v_cohort_sizes`, `v_mrr`, `v_conversion_channel`, `v_dau` |
| `003_experiments.sql` | `experiments` tables + `v_results` (SQL-computed conversion) |
| `004_rls.sql` | RLS policies, `my_orgs()` helper, `ingest_event()` security definer |
| `005_service_role_grants.sql` | Grants for the seed script (service role) |
| `006_expose_schemas.sql` | Expose `analytics` + `experiments` to PostgREST (`pgrst.db_schemas`) |
| `007_expose_schemas_clean.sql` | Same, comma-separated without spaces (PostgREST parse safety) |
| `008_authenticator_grants.sql` | `USAGE` on custom schemas for the `authenticator` role |

Schemas are also declared in `supabase/config.toml` → `[api].schemas` (managed via
`supabase config push`); migrations are symlinked into `supabase/migrations/` so
`supabase db push` applies them in order on a fresh project.

## Setup

```bash
# 1. Install deps
uv sync

# 2. Configure .env (see .env.example)
#    SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY (dashboard → Settings → API)

# 3. Seed the demo dataset (8k users, ~82k events, 1 A/B experiment, demo user)
uv run python scripts/seed_events.py

# 4. Run the dashboard
uv run streamlit run app.py
```

Demo login (created by the seed): `demo@acme-saas.dev` / `demo-password-123`.

## Ingest API

```bash
curl -X POST "https://feqhphmtldgjocjrydek.supabase.co/functions/v1/ingest" \
  -H "x-api-key: sb_analytics_<your_key>" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u00001","event_name":"signup","properties":{"channel":"organic"}}'
```

Returns `202` on success, `401` on a bad key, `400` on an invalid body.

## What to show in a portfolio

1. **Full-stack signal**: Postgres schema design, RLS, Edge Functions, Auth —
   not just pandas.
2. **Analytics in the DB**: funnel/retention/MRR as SQL views, not Python.
3. **A/B experiment end-to-end**: assignments → metrics → `v_results` →
   χ² significance (control 29.6% vs treatment 40.7%, **p ≈ 1.7e-10**).
   Deterministic seed: assignment fetch is ordered by id so re-seeds reproduce
   the same numbers.
4. **Security**: API keys stored as hashes, RLS verified (anon sees 0 rows),
   `security definer` ingest.
5. **Reuse**: the dashboard UI was reused from an existing Streamlit app —
   only the data layer changed.
6. **Phase 4 extras**: funnel breakdown by segment/channel/country/device,
   CSV export on every table, and an Events page that sends custom events
   through the same ingest API (needs `INGEST_API_KEY`).

## Repo layout

```
├── app.py                    # auth gate + st.navigation (7 pages)
├── supabase_client.py       # RLS-scoped query layer (paginated) + ingest client
├── data.py                  # SQL-backed data layer, API-compatible with streamlit-app
├── pages/                   # overview, funnel, retention, revenue, segments, experiments, events
├── sql/                     # migrations 001–005
├── supabase/functions/ingest/  # Edge Function (Deno)
└── scripts/seed_events.py   # deterministic synthetic dataset + A/B experiment
```
