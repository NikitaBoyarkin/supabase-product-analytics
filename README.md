# Product Analytics + A/B Experiments (Supabase)

> A/B-эксперимент закрыт: контроль 29,6 %, тест 40,7 %, p ≈ 1.7e-10.
> Эксперимент живёт в базе — любой клиент, Streamlit-дашборд или
> обычный SQL, читает одни и те же числа. Платформа целиком на
> Supabase Postgres: события принимает Edge Function, доступ режет
> Row Level Security.

## Navigation
- 🌐 [Portfolio site](https://nikitaboyarkin.github.io)
- 🏦 [Flagship case: Volta neobank](https://github.com/NikitaBoyarkin/volta-banking)
- 🧪 Related: [supabase-product-analytics](https://github.com/NikitaBoyarkin/supabase-product-analytics) · [streamlit-app](https://github.com/NikitaBoyarkin/streamlit-app) · [airflow](https://github.com/NikitaBoyarkin/airflow)

**▶ [Diagram: Supabase product analytics · ingest behind RLS](docs/diagrams/supabase-product-analytics.html)** — opens in a browser, no install, no build

**On this page:** [Situation](#situation) · [Task](#task) · [Actions](#actions) · [Result](#result) · [Architecture](#architecture) · [Security model](#security-model-rls) · [Schema](#schema-migrations) · [Setup](#setup) · [Ingest API](#ingest-api) · [What to show in a portfolio](#what-to-show-in-a-portfolio) · [Repo layout](#repo-layout)

## Situation

Дашборд `streamlit-app` уже был, но данные жили в памяти генератора.
Ничего не сохранялось, доступа по организациям не было, приёма
событий и истории экспериментов тоже.

## Task

Собрать из этого полноценную платформу продуктовой аналитики: живой
Supabase Postgres, чтение через Row Level Security, Edge Function
принимает события по API-ключу, A/B-эксперимент считается в SQL.

## Actions

- Две схемы: `analytics` (organizations, api_keys, users, events,
  subscriptions, org_members) и `experiments` (experiments, variants,
  assignments, metrics);
- аналитика уехала в базу: SQL-вью считают воронку, retention по
  когортам, MRR, DAU и конверсию по каналам (`sql/002_views.sql`), а
  `experiments.v_results` считает назначенных, конвертированных и
  конверсию по вариантам;
- RLS включён на каждой таблице, рядом хелпер `analytics.my_orgs()` —
  пользователь видит только строки своей организации;
- Edge Function `supabase/functions/ingest` (Deno) проверяет API-ключ,
  хранит его как SHA-256-хеш и вставляет событие через функцию
  `security definer`;
- интерфейс дашборда переехал из `streamlit-app` без переделки —
  поменялся только слой данных: вместо генератора в памяти теперь
  запросы к Postgres через RLS;
- поверх `v_results` прогнан χ²-тест значимости.

## Result

- A/B-эксперимент закрыт: контроль 29,6 %, тест 40,7 %,
  **p ≈ 1.7e-10**. В дизайне был рост на 20 % относительно базы 30 %,
  то есть порог 36 % для теста. Фактический прогон на фиксированном
  потоке `rng(7)` дал ≈40,7 % — пересев воспроизводит те же числа.
  Значит, эффект принадлежит фиксированному потоку, а не
  спроектированному росту на 6 п. п.;
- аноним без сессии видит **0 строк** — это держит RLS на каждой
  таблице, проверка статична и лежит в `tests/`, база для неё не
  нужна;
- демо-данные: 8k пользователей, ~82k событий, 1 A/B-эксперимент,
  демо-пользователь.

**Limitations.** События для A/B сгенерированы, поэтому заметный
эффект синтетический — истории продукта за числами нет. Ценность не
в размере эффекта, а в том, что эксперимент считается в базе,
изолирован по тенантам и воспроизводится любым клиентом. Числа
совпадают с кейсом на сайте: контроль 29,6 %, тест 40,7 %,
p ≈ 1.7e-10.

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
  subscriptions, org_members) и `experiments` (experiments, variants,
  assignments, metrics).
- **Analytics in the DB**: вью считают воронку, retention по когортам,
  MRR, DAU и конверсию по каналам (`sql/002_views.sql`). Дашборд
  только перекладывает результат, сам не агрегирует.
- **A/B result in the DB**: `experiments.v_results` считает
  назначенных, конвертированных и конверсию по вариантам, χ²-тест
  дашборд запускает поверх.
- **Ingest**: `supabase/functions/ingest` сверяет API-ключ (хранится
  как SHA-256-хеш, в открытом виде — никогда) и вставляет событие
  через функцию `security definer`.

## Security model (RLS)

Row Level Security включён на каждой таблице. Пользователь видит
только строки своей организации:

```sql
-- analytics.my_orgs() resolves the caller's orgs from auth.uid()
create policy "org scoped select" on analytics.events
  for select using (organization_id in (select analytics.my_orgs()));
```

- **Anonymous** (no session): видит **0 строк** — проверено.
- **Authenticated demo user**: видит только строки своей организации.
- **Ingest**: Edge Function зовёт `analytics.ingest_event(...)` —
  функцию `security definer`, которая сверяет хеш ключа и вставляет
  событие. До таблиц клиент не достаёт.
- **Service role** (admin, только для засева): полный доступ через
  `005_service_role_grants`.

## Schema (migrations)

| Migration | Contents |
|---|---|
| `001_schema.sql` | таблицы `analytics`: organizations, api_keys (key_hash), users, events, subscriptions, org_members |
| `002_views.sql` | `v_events`, `v_subscriptions`, `v_funnel`, `v_retention_raw`, `v_cohort_sizes`, `v_mrr`, `v_conversion_channel`, `v_dau` |
| `003_experiments.sql` | таблицы `experiments` + `v_results` (конверсия считается в SQL) |
| `004_rls.sql` | политики RLS, хелпер `my_orgs()`, `ingest_event()` как `security definer` |
| `005_service_role_grants.sql` | гранты для скрипта засева (service role) |
| `006_expose_schemas.sql` | открывает `analytics` и `experiments` для PostgREST (`pgrst.db_schemas`) |
| `007_expose_schemas_clean.sql` | то же, но списком через запятую без пробелов — PostgREST парсит надёжнее |
| `008_authenticator_grants.sql` | `USAGE` на кастомные схемы для роли `authenticator` |

Схемы объявлены и в `supabase/config.toml` → `[api].schemas`
(правится через `supabase config push`). Миграции слинкованы в
`supabase/migrations/`, поэтому `supabase db push` применяет их по
порядку на новом проекте.

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

Логин демо-пользователя из засева: `demo@acme-saas.dev` /
`demo-password-123`.

## Ingest API

```bash
curl -X POST "https://feqhphmtldgjocjrydek.supabase.co/functions/v1/ingest" \
  -H "x-api-key: sb_analytics_<your_key>" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u00001","event_name":"signup","properties":{"channel":"organic"}}'
```

Успех отвечает `202`, плохой ключ — `401`, битое тело — `400`.

## What to show in a portfolio

1. **Full-stack signal**: проектирование схем Postgres, RLS, Edge
   Functions, Auth — не только pandas.
1. **Analytics in the DB**: воронка, retention и MRR живут во вью SQL, а
   не в Python.
1. **A/B experiment end-to-end**: назначения → метрики → `v_results` →
   χ²-тест (контроль 29,6 %, тест 40,7 %, **p ≈ 1.7e-10**). Засев
   детерминированный: назначения читаются по порядку id, поэтому
   пересев даёт те же числа.
1. **Security**: API-ключи лежат хешами, RLS проверен (аноним видит
   0 строк), приём идёт через `security definer`.
1. **Reuse**: интерфейс дашборда взят из готового Streamlit-приложения,
   поменялся только слой данных.
1. **Phase 4 extras**: разбивка воронки по сегменту, каналу, стране и
   устройству, выгрузка любой таблицы в CSV и страница Events —
   отправляет свои события через тот же Ingest API (нужен
   `INGEST_API_KEY`).

## Repo layout

```
├── app.py                    # auth gate + st.navigation (7 pages)
├── supabase_client.py       # RLS-scoped query layer (paginated) + ingest client
├── data.py                  # SQL-backed data layer, API-compatible with streamlit-app
├── pages/                   # overview, funnel, retention, revenue, segments, experiments, events
├── sql/                     # migrations 001–008
├── supabase/functions/ingest/  # Edge Function (Deno)
└── scripts/seed_events.py   # deterministic synthetic dataset + A/B experiment
```
