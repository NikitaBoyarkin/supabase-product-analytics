"""Seed the Supabase project with a synthetic SaaS dataset + one A/B experiment.

Requires ``SUPABASE_SERVICE_ROLE_KEY`` in ``.env`` (dashboard → Settings → API).
Run: ``uv run python scripts/seed_events.py``

The synthetic generator mirrors ``streamlit-app/data.py`` (seed = 42) so the
dashboard shows the same familiar dataset — but now served from Postgres.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from supabase_client import SUPABASE_SERVICE_ROLE_KEY, get_service_client

# --- Synthetic dataset config (mirrors streamlit-app/data.py) ---------------
RNG_SEED = 42
PERIOD_START = pd.Timestamp("2024-01-01")
PERIOD_END = pd.Timestamp("2025-06-30")
N_USERS = 8000

CHANNELS = ["organic", "paid_search", "social", "referral", "email"]
CHANNEL_P = [0.40, 0.25, 0.15, 0.12, 0.08]
COUNTRIES = ["US", "RU", "DE", "GB", "BR", "IN", "FR", "Other"]
COUNTRY_P = [0.35, 0.20, 0.10, 0.08, 0.07, 0.06, 0.05, 0.09]
DEVICES = ["mobile", "desktop"]
DEVICE_P = [0.60, 0.40]
SEGMENTS = ["smb", "mid", "enterprise"]
SEGMENT_P = [0.70, 0.23, 0.07]
PLAN_MRR = {"pro": 49, "business": 199, "enterprise": 999}
PLAN_P = {"pro": 0.80, "business": 0.15, "enterprise": 0.05}

ORG_ID = "11111111-1111-4111-8111-111111111111"
ORG_NAME = "Acme SaaS (demo)"
API_KEY_NAME = "demo-web"
DEMO_EMAIL = os.environ.get("DEMO_EMAIL", "demo@acme-saas.dev")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "demo-password-123")
INGEST_API_KEY = os.environ.get("INGEST_API_KEY", "")

BATCH = 5000


def generate() -> dict[str, pd.DataFrame]:
    """Deterministic synthetic dataset (identical to streamlit-app/data.py)."""
    rng = np.random.default_rng(RNG_SEED)
    n = N_USERS
    span = (PERIOD_END - PERIOD_START).days
    signup_day = rng.integers(0, span, size=n)
    signup_date = PERIOD_START + pd.to_timedelta(signup_day, unit="D")

    users = pd.DataFrame(
        {
            "user_id": np.array([f"u{i:05d}" for i in range(n)], dtype=object),
            "signup_date": pd.to_datetime(signup_date),
            "channel": rng.choice(CHANNELS, size=n, p=CHANNEL_P),
            "country": rng.choice(COUNTRIES, size=n, p=COUNTRY_P),
            "device": rng.choice(DEVICES, size=n, p=DEVICE_P),
            "segment": rng.choice(SEGMENTS, size=n, p=SEGMENT_P),
        }
    )

    uids = users["user_id"].to_numpy()
    sds = users["signup_date"].to_numpy()
    end_np = np.datetime64(PERIOD_END, "ns")

    parts: list[pd.DataFrame] = []
    parts.append(
        pd.DataFrame({"user_id": uids, "event_date": sds, "event_name": "app_open"})
    )
    parts.append(
        pd.DataFrame({"user_id": uids, "event_date": sds, "event_name": "signup"})
    )

    activated = rng.random(n) < 0.70
    act_dates = sds + rng.integers(1, 11, size=n) * np.timedelta64(1, "D")
    keep = activated & (act_dates <= end_np)
    parts.append(
        pd.DataFrame(
            {
                "user_id": uids[keep],
                "event_date": act_dates[keep],
                "event_name": "activate",
            }
        )
    )

    trialed = activated & (rng.random(n) < 0.55)
    trial_dates = sds + rng.integers(3, 12, size=n) * np.timedelta64(1, "D")
    keep = trialed & (trial_dates <= end_np)
    parts.append(
        pd.DataFrame(
            {
                "user_id": uids[keep],
                "event_date": trial_dates[keep],
                "event_name": "start_trial",
            }
        )
    )

    subscribed = trialed & (rng.random(n) < 0.35)
    sub_dates = trial_dates + rng.integers(2, 10, size=n) * np.timedelta64(1, "D")
    keep_sub = subscribed & (sub_dates <= end_np)
    parts.append(
        pd.DataFrame(
            {
                "user_id": uids[keep_sub],
                "event_date": sub_dates[keep_sub],
                "event_name": "subscribe",
            }
        )
    )

    max_weeks = 80
    tau = rng.exponential(scale=8.0, size=n)
    weeks = np.arange(max_weeks)
    prob = np.exp(-weeks[None, :] / tau[:, None])
    act_mat = rng.random((n, max_weeks)) < prob
    ui, wi = np.where(act_mat)
    jitter = rng.integers(0, 7, size=len(ui))
    active_dates = sds[ui] + (wi * 7 + jitter) * np.timedelta64(1, "D")
    keep = active_dates <= end_np
    parts.append(
        pd.DataFrame(
            {
                "user_id": uids[ui][keep],
                "event_date": active_dates[keep],
                "event_name": "active",
            }
        )
    )

    events = pd.concat(parts, ignore_index=True)
    events["event_date"] = pd.to_datetime(events["event_date"])
    events = events.sort_values("event_date").reset_index(drop=True)

    sub_uids = uids[keep_sub]
    sub_starts = sub_dates[keep_sub]
    plan_keys = list(PLAN_MRR)
    plans = rng.choice(plan_keys, size=len(sub_uids), p=[PLAN_P[k] for k in plan_keys])
    mrr = np.array([PLAN_MRR[p] for p in plans], dtype=float)
    churned_raw = rng.random(len(sub_uids)) < 0.30
    raw_churn_date = sub_starts + rng.integers(
        1, 7, size=len(sub_uids)
    ) * np.timedelta64(30, "D")
    final_churn = churned_raw & (raw_churn_date <= end_np)
    churn_date = np.where(final_churn, raw_churn_date, np.datetime64("NaT", "ns"))

    subscriptions = pd.DataFrame(
        {
            "user_id": sub_uids,
            "start_date": pd.to_datetime(sub_starts),
            "plan": plans,
            "mrr": mrr,
            "churn_date": pd.to_datetime(churn_date),
        }
    )
    return {"users": users, "events": events, "subscriptions": subscriptions}


def chunked(rows: list[dict], size: int = BATCH):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def seed_experiment(client, ext_to_id: dict[str, int], events: pd.DataFrame) -> None:
    """One concluded A/B test: pricing page redesign, +20% relative lift.

    Effect size is chosen so the result is statistically significant at the
    seeded sample size (n≈1500 per variant): 30% → 36% conversion.
    """
    trial_uids = sorted(
        set(events.loc[events["event_name"] == "start_trial", "user_id"])
    )
    rng = np.random.default_rng(7)
    rng.shuffle(trial_uids)
    half = len(trial_uids) // 2
    control, treatment = trial_uids[:half], trial_uids[half:]

    exp = (
        client.schema("experiments")
        .from_("experiments")
        .insert(
            {
                "organization_id": ORG_ID,
                "name": "Pricing page redesign v2",
                "hypothesis": "Новый дизайн pricing-страницы повышает конверсию в подписку "
                "среди пользователей, дошедших до триала.",
                "status": "concluded",
                "started_at": "2024-06-01T00:00:00Z",
                "ended_at": "2024-12-31T00:00:00Z",
            }
        )
        .execute()
        .data[0]
    )
    exp_id = exp["id"]

    v_control = (
        client.schema("experiments")
        .from_("variants")
        .insert({"experiment_id": exp_id, "key": "control", "traffic_weight": 0.5})
        .execute()
        .data[0]
    )
    v_treatment = (
        client.schema("experiments")
        .from_("variants")
        .insert({"experiment_id": exp_id, "key": "treatment", "traffic_weight": 0.5})
        .execute()
        .data[0]
    )

    assign_rows = [
        {
            "experiment_id": exp_id,
            "user_id": ext_to_id[uid],
            "variant_id": v_control["id"],
        }
        for uid in control
    ] + [
        {
            "experiment_id": exp_id,
            "user_id": ext_to_id[uid],
            "variant_id": v_treatment["id"],
        }
        for uid in treatment
    ]
    for batch in chunked(assign_rows):
        client.schema("experiments").from_("assignments").insert(batch).execute()

    fetched: list[dict] = []
    offset = 0
    while True:
        page = (
            client.schema("experiments")
            .from_("assignments")
            .select("id,variant_id")
            .eq("experiment_id", exp_id)
            .order("id")  # stable order — conversion draws depend on fetch order
            .range(offset, offset + 999)
            .execute()
            .data
        )
        if not page:
            break
        fetched.extend(page)
        offset += 1000
    vmap = {v_control["id"]: "control", v_treatment["id"]: "treatment"}
    base_conv, lift = 0.30, 0.20
    metrics = []
    for a in fetched:
        key = vmap[a["variant_id"]]
        conv = (
            1
            if rng.random()
            < (base_conv if key == "control" else base_conv * (1 + lift))
            else 0
        )
        metrics.append(
            {
                "experiment_id": exp_id,
                "assignment_id": a["id"],
                "metric_name": "conversion",
                "value": conv,
            }
        )
    for batch in chunked(metrics):
        client.schema("experiments").from_("metrics").insert(batch).execute()

    print(
        f"experiment: {len(control) + len(treatment)} assigned, {len(metrics)} metric rows"
    )


def main() -> None:
    if not SUPABASE_SERVICE_ROLE_KEY:
        sys.exit(
            "SUPABASE_SERVICE_ROLE_KEY missing in .env — "
            "copy from dashboard → Settings → API → service_role (secret)"
        )
    if not INGEST_API_KEY:
        sys.exit(
            "INGEST_API_KEY missing in .env — needed to register the ingest api key"
        )
    client = get_service_client()

    # 1. org + api key (idempotent)
    client.schema("analytics").from_("organizations").upsert(
        [{"id": ORG_ID, "name": ORG_NAME}], on_conflict="id"
    ).execute()
    key_hash = hashlib.sha256(INGEST_API_KEY.encode()).hexdigest()
    client.schema("analytics").from_("api_keys").upsert(
        [{"organization_id": ORG_ID, "key_hash": key_hash, "name": API_KEY_NAME}],
        on_conflict="key_hash",
    ).execute()

    # 2. reset non-idempotent tables so re-runs don't duplicate rows
    #    (sentinel differs by column type: bigint vs uuid)
    for schema, table, sentinel in [
        ("analytics", "events", 0),
        ("analytics", "subscriptions", 0),
        ("experiments", "metrics", 0),
        ("experiments", "assignments", 0),
        ("experiments", "variants", "00000000-0000-0000-0000-000000000000"),
        ("experiments", "experiments", "00000000-0000-0000-0000-000000000000"),
    ]:
        client.schema(schema).from_(table).delete().neq("id", sentinel).execute()

    # 3. synthetic data
    d = generate()
    users, events, subs = d["users"], d["events"], d["subscriptions"]

    # 3. users
    user_rows = [
        {
            "organization_id": ORG_ID,
            "external_id": r["user_id"],
            "properties": {
                "channel": r["channel"],
                "country": r["country"],
                "device": r["device"],
                "segment": r["segment"],
            },
            "created_at": r["signup_date"].isoformat(),
        }
        for _, r in users.iterrows()
    ]
    for batch in chunked(user_rows):
        client.schema("analytics").from_("users").upsert(
            batch, on_conflict="organization_id,external_id"
        ).execute()
    print(f"users: {len(user_rows)}")

    # PostgREST caps responses at 1000 rows (db-max-rows) — paginate to get all.
    inserted: list[dict] = []
    offset = 0
    while True:
        page = (
            client.schema("analytics")
            .from_("users")
            .select("id,external_id")
            .eq("organization_id", ORG_ID)
            .range(offset, offset + 999)
            .execute()
            .data
        )
        if not page:
            break
        inserted.extend(page)
        offset += 1000
    ext_to_id = {u["external_id"]: u["id"] for u in inserted}

    # 4. events
    event_rows = []
    for _, r in events.iterrows():
        uid = ext_to_id.get(r["user_id"])
        if uid is None:
            continue
        event_rows.append(
            {
                "organization_id": ORG_ID,
                "user_id": uid,
                "event_name": r["event_name"],
                "properties": {},
                "event_time": r["event_date"].isoformat(),
            }
        )
    for batch in chunked(event_rows):
        client.schema("analytics").from_("events").insert(batch).execute()
    print(f"events: {len(event_rows)}")

    # 5. subscriptions
    sub_rows = []
    for _, r in subs.iterrows():
        uid = ext_to_id.get(r["user_id"])
        if uid is None:
            continue
        sub_rows.append(
            {
                "organization_id": ORG_ID,
                "user_id": uid,
                "plan": r["plan"],
                "mrr": float(r["mrr"]),
                "start_date": r["start_date"].date().isoformat(),
                "churn_date": None
                if pd.isna(r["churn_date"])
                else r["churn_date"].date().isoformat(),
            }
        )
    for batch in chunked(sub_rows):
        client.schema("analytics").from_("subscriptions").insert(batch).execute()
    print(f"subscriptions: {len(sub_rows)}")

    # 6. demo auth user + org membership
    try:
        resp = client.auth.admin.create_user(
            {"email": DEMO_EMAIL, "password": DEMO_PASSWORD, "email_confirm": True}
        )
        demo = resp.user
    except Exception as e:  # noqa: BLE001
        print(f"auth user (may already exist): {e}")
        demo = next(
            (u for u in client.auth.admin.list_users() if u.email == DEMO_EMAIL), None
        )
    if demo:
        client.schema("analytics").from_("org_members").upsert(
            [{"user_id": demo.id, "organization_id": ORG_ID, "role": "admin"}],
            on_conflict="user_id,organization_id",
        ).execute()
        print(f"demo user: {demo.email}")

    # 7. A/B experiment
    seed_experiment(client, ext_to_id, events)

    print("done.")


if __name__ == "__main__":
    main()
