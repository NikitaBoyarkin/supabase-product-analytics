# PRD: Supabase Product Analytics + A/B Experiments

**Автор:** Nikita Boyarkin
**Дата:** 2026-09-15
**Статус:** In Review
**Версия:** 1.0

---

## 1. Executive Summary

Full-stack портфолио-платформа продуктовой аналитики: Streamlit-дашборд читает живые данные из Supabase Postgres через Row Level Security, приём событий идёт через Edge Function (Deno) по API-ключу, а funnel/retention/MRR/DAU/конверсия считаются SQL-вьюхами в БД — не в pandas. Включает завершённый A/B эксперимент (pricing page redesign) с конверсией, посчитанной в SQL, и χ²-тестом значимости. Цель PRD — зафиксировать as-is платформу как единый источник истины для портфолио и наметить 3 следующих аппетита.

## 2. Problem Statement

### Текущая ситуация
До этого проекта портфолио состояло преимущественно из pandas/ноутбучной аналитики. Отсутствовал full-stack/backend-сигнал: работа с реальной БД, безопасность (RLS, hashed API-ключи), серверный код (Edge Functions), бэкенд-сторонняя аналитика.

### Влияние на пользователя
- **Кто затронут:** рекрутеры и интервьюеры, оценивающие продуктового аналитика; демо-пользователи дашборда.
- **Как затронут:** без backend-кейса кандидат выглядит однобоко — только анализ, без понимания инженерии данных и безопасности.
- **Серьёзность:** High — конкуренция за аналитические роли требует доказанного full-stack скилла.

### Бизнес-влияние
- **Стоимость проблемы:** потерянные офферы на аналитические роли из-за слабого технического сигнала в портфолио.
- **Стратегическая важность:** флагманский проект по направлению «карьера» (MOC Career & GitHub Portfolio).

### Почему решать сейчас
Рынок смещается к аналитикам, которые умеют работать с SQL-хранилищами и self-serve пайплайнами. Платформа закрывает этот пробел: аналитика в БД, безопасный инжest, мультитенантность.

## 3. Goals & Success Metrics

### Goal 1: Доказать full-stack аналитический скилл
- **Описание:** продемонстрировать проектирование схемы, RLS, Edge Functions, аналитику в БД.
- **Метрика:** кол-во реализованных SQL-вьюх аналитики в БД.
- **Baseline:** 0 (только pandas-аналитика в портфолио).
- **Target:** 8+ SQL-вьюх (funnel, retention, MRR, DAU, conversion, v_results и др.).
- **Срок:** 2026-08-13 (достигнуто).
- **Метод измерения:** `sql/002_views.sql` + `sql/003_experiments.sql`.

### Goal 2: Безопасность как доказуемое свойство, а не декларация
- **Описание:** RLS-изоляция организаций + API-ключи только в виде SHA-256 hash.
- **Метрика:** кол-во строк, видимых анонимом.
- **Baseline:** n/a (в проектах без RLS не измерялось).
- **Target:** 0 строк для анонима; аутентифицированный юзер видит только свою организацию.
- **Срок:** 2026-08-14 (верифицировано).
- **Метод измерения:** проверка `select` от анонимного и demo-пользователя.

### Goal 3: Полный цикл A/B эксперимента
- **Описание:** от назначения вариантов до статистически значимого вывода.
- **Метрика:** p-value χ²-теста.
- **Baseline:** n/a.
- **Target:** p < 0.05 с понятной интерпретацией.
- **Срок:** 2026-08-14 → 2026-09-15 (достигнуто: control 29.6% vs treatment 40.7%, p ≈ 1.7e-10).
- **Метод измерения:** χ² на таблице конверсий `experiments.v_results`.

## 4. User Stories

### Story 1: Демо-пользователь
**As a** демо-пользователь, **I want to** залогиниться и видеть метрики своей организации, **So that I can** оценить аналитический дашборд без настройки.

**Acceptance Criteria:**
- [ ] Вход по `demo@acme-saas.dev` / `demo-password-123` открывает дашборд
- [ ] Данные ограничены организацией demo-юзера (RLS)
- [ ] Все 6 страниц (overview, funnel, retention, revenue, segments, experiments) доступны

**Dependencies:** REQ-002, REQ-003, REQ-005, REQ-007

### Story 2: Клиент, отправляющий события
**As a** клиентский сервер, **I want to** слать события по HTTP с API-ключом, **So that I can** наполнять аналитику без прямого доступа к БД.

**Acceptance Criteria:**
- [ ] `POST /functions/v1/ingest` с `x-api-key` возвращает `202` и `event_id`
- [ ] Невалидный ключ → `401`, пустой body → `400`, не-POST → `405`
- [ ] Событие попадает в `analytics.events` без service-role ключа у клиента

**Dependencies:** REQ-001, REQ-002, REQ-003

### Story 3: Интервьюер
**As a** интервьюер, **I want to** быстро понять архитектуру и безопасность, **So that I can** оценить уровень кандидата.

**Acceptance Criteria:**
- [ ] README описывает схему, RLS-модель и миграции
- [ ] Repo layout однозначно читается (app, data, pages, sql, functions, scripts)
- [ ] Демо воспроизводимо: `uv sync` → seed → `streamlit run`

**Dependencies:** REQ-007, REQ-008

## 5. Functional Requirements

### Must Have (P0) — ядро платформы as-is

#### REQ-001: Ingest API (Edge Function + security definer)
**Описание:** Приём событий через `POST /functions/v1/ingest` (Deno, supabase-js). Функция хэширует API-ключ (SHA-256) и вызывает `analytics.ingest_event(...)` — `security definer`, который валидирует ключ и пишет событие. Никакого service-role ключа в рантайме клиента.

**Acceptance Criteria:**
- [ ] Запрос с валидным `x-api-key` и body `{user_id, event_name}` → HTTP `202` + `event_id`
- [ ] Невалидный/отсутствующий ключ → `401`; отсутствующий `user_id`/`event_name` → `400`; не-JSON body → `400`
- [ ] Non-POST метод → `405`; OPTIONS → CORS-заголовки, `200`
- [ ] Событие появляется в `analytics.events` с корректным `organization_id`, определённым по `key_hash`
- [ ] Повторный `user_id` не создаёт дубликат юзера (upsert по `(organization_id, external_id)`), properties мержатся
- [ ] Ошибка `invalid api key` в БД маппится на `401` в Edge Function

**Техническая спецификация:**
```
POST {url}/functions/v1/ingest
Header: x-api-key: sb_analytics_<key>
Body:   { "user_id": "u00001", "event_name": "signup", "properties": {"channel": "organic"} }

analytics.ingest_event(p_key_hash, p_external_id, p_event_name, p_properties, p_event_time)
→ insert/upsert users → insert events → return event id
```

**Task Breakdown:**
- Edge Function (Deno, SHA-256, RPC): Medium (4-8h)
- `ingest_event()` security definer: Medium (4-8h)
- Тесты (curl: 202/401/400/405): Small (2-4h)

**Dependencies:** REQ-002 (схема), REQ-003 (grants/RLS)

#### REQ-002: Мультитенантная модель данных
**Описание:** Схема `analytics` (organizations, api_keys, users, events, subscriptions, org_members) и `experiments` (experiments, variants, assignments, metrics). Пользователи продукта (`analytics.users`) отделены от Supabase Auth юзеров (`auth.users`, связь через `org_members`).

**Acceptance Criteria:**
- [ ] Каждая строка событий/юзеров/подписок привязана к `organization_id` с FK cascade
- [ ] API-ключи хранятся только как `key_hash` (SHA-256, `unique`) — plaintext нигде не персистится
- [ ] `unique(organization_id, external_id)` на юзерах — внешний ID уникален внутри организации
- [ ] Индексы по `(organization_id, event_name, event_time)` и `(organization_id, user_id)`
- [ ] Миграции идемпотентны (`create table if not exists`) и запускаются по порядку 001–008

**Техническая спецификация:**
```
analytics.organizations (id, name, created_at)
analytics.api_keys     (id, organization_id, key_hash unique, name, created_at)
analytics.users        (id, organization_id, external_id, properties jsonb, created_at)
analytics.events       (id, organization_id, user_id, event_name, properties, event_time)
analytics.subscriptions(id, organization_id, user_id, plan, mrr check >=0, start_date, churn_date)
analytics.org_members  (user_id uuid→auth.users, organization_id, role, PK(user_id, org))
```

**Task Breakdown:**
- `001_schema.sql`: Medium (4-8h)
- Индексы + FK: Small (2-4h)
- Валидация миграций в Supabase SQL Editor: Small (2-4h)

**Dependencies:** None

#### REQ-003: RLS-изоляция организаций
**Описание:** Row Level Security включена на всех таблицах. Политики разрешают `select` только для строк организаций из `analytics.my_orgs()` (по `auth.uid()`). `api_keys` без политик — deny по умолчанию.

**Acceptance Criteria:**
- [ ] Аноним (нет сессии) видит 0 строк во всех таблицах (верифицировано)
- [ ] Аутентифицированный юзер видит только строки своей организации
- [ ] Вьюхи с `security_invoker = on` наследуют RLS базовых таблиц
- [ ] Инжest через `ingest_event()` (security definer) обходит RLS, но гейтится по `key_hash` — прямой записи из клиента нет
- [ ] Service-role (seed) имеет полный доступ только через `005_service_role_grants`

**Техническая спецификация:**
```
create policy "org scoped select" on analytics.events
  for select using (organization_id in (select analytics.my_orgs()));
-- api_keys: RLS on, no policies → default deny
```

**Task Breakdown:**
- `004_rls.sql` политики + `my_orgs()`: Medium (4-8h)
- Верификация (anon 0 строк, demo-юзер своя орг.): Medium (4-8h)
- Grants для anon/authenticated: Small (2-4h)

**Dependencies:** REQ-002

#### REQ-004: Аналитика в БД (SQL-вьюхи)
**Описание:** Слои агрегации в Postgres, а не в Python: `v_events`, `v_subscriptions`, `v_funnel`, `v_retention_raw`, `v_cohort_sizes`, `v_mrr`, `v_conversion_channel`, `v_dau`. Дашборд лишь решейпит данные.

**Acceptance Criteria:**
- [ ] `v_funnel` возвращает distinct users по каждому шагу (app_open → signup → activate → start_trial → subscribe)
- [ ] `v_mrr` считает месячный MRR (общий и по планам pro/business/enterprise) с учётом churn_date
- [ ] `v_retention_raw` + `v_cohort_sizes` дают знаменатель и числитель когортной ретенции
- [ ] `v_conversion_channel` считает signup→paid конверсию по каналу (users/paid/conversion, 4 знака)
- [ ] `v_dau` возвращает по дням distinct active юзеров
- [ ] Все вьюхи `security_invoker = on` — RLS-безопасны

**Техническая спецификация:**
```
create or replace view analytics.v_mrr with (security_invoker = on) as
  ... generate_series(month) join subscriptions
  where date_trunc('month', s.start_date) <= m.m
    and (s.churn_date is null or date_trunc('month', s.churn_date) > m.m)
```

**Task Breakdown:**
- `002_views.sql` (8 вьюх): Large (8-12h)
- Проверка на seed-данных против ожиданий: Medium (4-8h)

**Dependencies:** REQ-002, REQ-007 (данные для проверки)

#### REQ-005: Дашборд Streamlit (6 страниц)
**Описание:** `app.py` — auth-gate + `st.navigation` (overview, funnel, retention, revenue, segments, experiments). Data-слой `supabase_client.query` (paginated, RLS-scoped) + `data.py` (pure-pandas решейперы, API-совместимый с `streamlit-app`). Кэш `st.cache_data(ttl=300)`.

**Acceptance Criteria:**
- [ ] Без сессии показывается форма входа; после входа — дашборд
- [ ] Все 6 страниц рендерятся из SQL-данных (не in-memory генератора)
- [ ] Логин невалидный → ошибка, состояние не меняется
- [ ] Данные кэшируются 300 сек (повторный рендер не бьёт БД на каждый rerun)
- [ ] AppTest проходит 6/6 страниц

**Техническая спецификация:**
```
app.py: st.set_page_config(wide) → if not is_authenticated(): login form, st.stop()
        → st.Page(...) × 6 → st.navigation(...) → pg.run()
data.py: get_data() @st.cache_data(ttl=300) → query("analytics", "users|v_events|v_subscriptions")
```

**Task Breakdown:**
- `supabase_client.py` (paginated query layer): Medium (4-8h)
- `data.py` решейперы: Medium (4-8h)
- `pages/*` 6 страниц: Medium (6-10h)
- AppTest + smoke: Small (2-4h)

**Dependencies:** REQ-003, REQ-004

#### REQ-006: A/B эксперимент end-to-end
**Описание:** Схема `experiments` (эксперименты, варианты, назначения, метрики). `v_results` считает per-variant assigned/converted/conversion в SQL; дашборд поверх делает χ²-тест и lift.

**Acceptance Criteria:**
- [ ] `v_results` возвращает для каждого варианта: assigned, converted, conversion (round 4)
- [ ] conversion считается как `count(metrics where metric_name='conversion' and value>0) / count(distinct assignments)`
- [ ] Страница Experiments показывает таблицу вариантов + Lift vs control + p-value (χ²)
- [ ] p < 0.05 → «Статистически значимо»; иначе — «Не значимо» (в тесте: control 29.6%, treatment 40.7%, p ≈ 1.7e-10)
- [ ] Эксперименты изолированы по организации через RLS (v_results + таблицы)

**Техническая спецификация:**
```
experiments.v_results: group by x.id, x.name, x.status, v.key
  assigned   = count(distinct a.id)
  converted  = count(distinct m.assignment_id) filter (where m.metric_name='conversion' and m.value>0)
  conversion = converted / assigned
```

**Task Breakdown:**
- `003_experiments.sql` + `v_results`: Medium (4-8h)
- `pages/experiments.py` (χ², lift): Small (2-4h)
- Проверка значимости на seed: Small (2-4h)

**Dependencies:** REQ-002, REQ-003, REQ-007

### Should Have (P1)

#### REQ-007: Детерминированный seed-датасет
**Описание:** `scripts/seed_events.py` генерирует воспроизводимый датасет (seed=42): 8 000 юзеров, 82 301 событие, 1 086 подписок, 1 завершённый A/B эксперимент, demo-юзер.

**Acceptance Criteria:**
- [ ] Повторный запуск с тем же seed даёт идентичные числа (8 000 / 82 301 / 1 086)
- [ ] Создаётся demo-юзер `demo@acme-saas.dev` / `demo-password-123` с членством в организации
- [ ] Генерируется A/B эксперимент pricing-page с двумя вариантами и метриками conversion
- [ ] Использует service-role ключ только для записи seed-данных (не в рантайме дашборда)

**Task Breakdown:**
- Генератор (users/events/subs): Large (8-12h)
- Эксперимент + assignments/metrics: Medium (4-8h)
- Demo-auth: Small (2-4h)

**Dependencies:** REQ-001 (ingest-путь можно обойти напрямую), REQ-002, REQ-003

#### REQ-008: Переиспользование UI (API-совместимый data-слой)
**Описание:** UI унаследован из standalone `streamlit-app`; изменился только data-слой (in-memory → Supabase). `data.py` сохраняет API исходного приложения.

**Acceptance Criteria:**
- [ ] Страницы вызывают те же функции/формы, что и `streamlit-app/data.py`
- [ ] Переход не потребовал переписывания `pages/*` под новый источник данных
- [ ] Одинаковые данные из SQL-вьюх и из прежнего in-memory генератора дают совпадающие метрики

**Task Breakdown:**
- Адаптация data.py под SQL-вьюхи: Medium (4-8h)
- Регрессия метрик на идентичных данных: Small (2-4h)

**Dependencies:** REQ-004, REQ-005

### Nice to Have (P2) — аппетиты на следующий цикл

#### REQ-009: Funnel по сегментам
**Описание:** Разбивка воронки по channel/country/device/segment, чтобы находить сегментные drop-off.

**Acceptance Criteria:**
- [x] На странице Funnel выбирается сегмент (segment, channel, country, device)
- [x] Воронка пересчитывается только по юзерам выбранного сегмента
- [x] Для пустого сегмента показывается пустое состояние, а не ошибка
- [x] Реализовано: `funnel_by_dimension()` (pandas, параметризованный запрос по уже загруженным users/events) + таблица с overall conversion + групповой бар-чарт

**Dependencies:** REQ-004

#### REQ-010: Экспорт отчётов (CSV)
**Описание:** Выгрузка текущих таблиц/метрик каждой страницы в CSV одним кликом.

**Acceptance Criteria:**
- [x] Кнопка «Скачать CSV» на всех страницах с табличными данными (funnel, retention, segments, revenue, experiments, events, overview)
- [x] Файл содержит те же колонки и строки, что и отображаемая таблица
- [x] Файл назван по шаблону `<page>_<dimension/date>.csv` / `<page>_<id>.csv`
- [x] Экспорт работает с текущим RLS-скоупом (не шире видимой выборки)

**Dependencies:** REQ-005

#### REQ-011: Custom events (ad-hoc витрина)
**Описание:** Вкладка для регистрации произвольных событий через ingest и просмотра их в дашборде без новой миграции.

**Acceptance Criteria:**
- [x] Валидное событие с произвольным `event_name` попадает в `analytics.events` через ingest
- [x] Новые события появляются на страницах дашборда сразу после отправки (кэш очищается + rerun)
- [x] Невалидный `event_name` (пустой) отклоняется в форме; не-JSON properties → ошибка, вызов не происходит
- [x] Частота событий по `event_name` видна на странице Events и в expander на Overview
- [x] Реализовано: `pages/events.py` + `send_ingest_event()` (server-side POST в Edge Function, urllib, без новых зависимостей)

**Dependencies:** REQ-001, REQ-004

## 6. Non-Functional Requirements

### Performance
- Дашборд: загрузка данных < 2s p95 при кэше 300s (повторные рендеры — из кэша)
- Ingest: ответ Edge Function < 200ms p95 на один POST
- Пропускная способность: ≥ 50 событий/с (верхняя граница не целилась — портфолио-масштаб)

### Security
- Аутентификация: Supabase email/password (JWT)
- API-ключи: SHA-256 hash в БД, plaintext нигде не хранится; ingest-ключ не в рантайме дашборда
- Изоляция: RLS на всех таблицах; аноним — 0 строк; demo-юзер — только своя организация
- Запись: только через `security definer` ingest_event (гейт по key_hash) или service-role seed
- Secrets: `.env` в `.gitignore`; ingest-ключ в репо заменён плейсхолдером

### Scalability
- Пользователей: демо-масштаб (8k юзеров, ~82k событий); схема рассчитана на организации
- Рост данных: индексы на ключевых фильтрах; pagination в `supabase_client`
- География: single-region (портфолио)

### Reliability
- SLA: n/a (портфолио, не продакшн)
- Кэш данных: 300s TTL с обработкой пустых DataFrame (все ветки возвращают колонки)
- Error handling: пустые сегменты/данные → `st.info`, не краш

## 7. Technical Considerations

### Архитектура
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

### Технологический стек
- **Frontend:** Streamlit 1.61, `st.navigation`, 6 страниц
- **Backend:** Supabase Edge Functions (Deno, supabase-js), RPC `analytics.ingest_event`
- **Database:** Supabase Postgres 17; схемы `analytics` + `experiments`; 8 миграций
- **Infrastructure:** Supabase Cloud; Streamlit Community Cloud (деплой в процессе)

### Внешние зависимости
1. **Supabase (Postgres + Auth + Edge Functions):** основной сервис; ключи в `.env`
2. **Streamlit:** UI-рантайм; `st.cache_data` для кэша
3. **scipy:** χ²-тест на странице Experiments

### Миграция (для существующих систем)
1. Миграции 001–008 идемпотентны, применяются по порядку: `supabase link` → `supabase db push`
2. Данные пересоздаются детерминированно: `uv run python scripts/seed_events.py`
3. Откат: дропнуть схемы `analytics`/`experiments` и переприменить миграции
4. Деплой на Cloud: фикс ленивого чтения секретов (`1c2ca16`) уже в main

### Тестирование
- Unit: метрические решейперы в `data.py` (funnel, retention, MRR, ARPU)
- Integration: seed → запросы вьюх → числа совпадают с ожиданиями
- E2E: AppTest 7/7 страниц + smoke HTTP 200
- Security: ручная верификация RLS (anon 0 строк; demo-юзер своя орг.)
- API: curl-сценарии ingest (202/401/400/405)

## 8. Implementation Roadmap

### Phase 1: Data Platform (реализовано, 2026-08-13)
**Goal:** схема + инжest + seed.
**Tasks:**
- [x] `001_schema.sql` (REQ-002) — Medium (5h)
- [x] `004_rls.sql` + `ingest_event()` (REQ-003, REQ-001) — Medium (6h)
- [x] `scripts/seed_events.py` (REQ-007) — Large (10h)
**Validation Checkpoint:** seed = 8 000 юзеров / 82 301 событие; RLS верифицирован (anon 0 строк).

### Phase 2: Analytics + Dashboard (реализовано, 2026-08-14)
**Goal:** SQL-вьюхи и UI.
**Tasks:**
- [x] `002_views.sql` (REQ-004) — Medium (6h)
- [x] `supabase_client.py` + `data.py` + `pages/*` (REQ-005, REQ-008) — Medium (8h)
**Validation Checkpoint:** AppTest 6/6; метрики на seed совпадают с ожиданиями.

### Phase 3: Experiments + Hardening (реализовано, 2026-08-14)
**Goal:** A/B цикл и доводка безопасности.
**Tasks:**
- [x] `003_experiments.sql` + `v_results` (REQ-006) — Medium (6h)
- [x] `005_service_role_grants`, секреты в .gitignore (REQ-003) — Small (2h)
**Validation Checkpoint:** p ≈ 1.7e-10 на странице Experiments; ingest-ключ в репо — плейсхолдер.

### Phase 4: Аппетиты (реализовано, 2026-09-15)
**Goal:** сегментная воронка, экспорт, custom events.
**Tasks:**
- [x] Funnel by dimension (REQ-009) — `funnel_by_dimension()` + UI (grouped bars + overall conversion) — Medium (4h)
- [x] CSV-экспорт (REQ-010) — `csv_download()` на 7 страницах — Small (3h)
- [x] Custom events (REQ-011) — `pages/events.py` + `send_ingest_event()` — Medium (5h)
**Validation Checkpoint:** AppTest 7/7 страниц; smoke хелперов; ruff чист по новым файлам.

### Зависимости задач
```
Phase 1 → Phase 2 → Phase 3 → Phase 4
Critical Path: 001_schema → 004_rls/ingest → seed → 002_views → dashboard → experiments
```

### Оценка усилий
- Phase 1: ~21h
- Phase 2: ~14h
- Phase 3: ~8h
- Phase 4: ~12h
- **Итого (as-is):** ~43h (~1 неделя solo)
- **Итого (с аппетитами):** ~55h
- **Риск-буфер:** +20%

## 9. Out of Scope

1. **Реальное использование в проде (не портфолио)** — платформа демонстрационная; метрики на синтетике, SLA/SLO не применяются.
2. **Аналитический SQL-движок общего назначения** — вьюхи заточены под конкретные метрики; ad-hoc BI-слой не входит.
3. **Identity resolution / cross-device** — события без линковки анонимных/авторизованных устройств.
4. **Мультирегиональность / HA** — single-region Supabase.
5. **Расширенная статистика A/B (sequential, CUPED, SRM)** — вне цикла; калибровка — отдельный проект (см. PRD - A-B Testing Toolkit).

## 10. Open Questions & Risks

### Open Questions
#### Q1: Деплой на Streamlit Cloud
- **Статус:** проект пересоздан (`feqhphmtldgjocjrydek`, 2026-09-15): миграции 001–008 применены, seed залит, ingest задеплоен и протестирован live. Осталось: переключить/пересоздать app на Cloud с новыми секретами (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `INGEST_API_KEY`)
- **Варианты:** (A) переключить app на main → проверить логин; (B) пересоздать app; (C) не деплоить (локальная демо)
- **Владелец:** Nikita
- **Влияние:** Medium (портфолио-витрина vs локальная демо)

#### Q2: Публичность репо
- **Статус:** приватный `github.com/NikitaBoyarkin/supabase-product-analytics`
- **Варианты:** (A) оставить приватным + ссылка по запросу; (B) сделать публичным после вычистки секретов
- **Влияние:** Medium

#### Q3: Тест живого ingest — ✅ закрыт (2026-09-15)
- **Статус:** живой curl против деплоенной Edge Function: 202 (валидный ключ, event_id=82302), 401 (плохой ключ), 400 (пустой body), 400 (нет user_id), 405 (GET). Кастомное событие `feature_used` видно demo-юзером через RLS.
- **Влияние:** Low

### Risks & Mitigation

| Риск | Вероятность | Влияние | Severity | Митигация | Контингенция |
|------|-------------|---------|----------|-----------|--------------|
| Утечка service_role/anon ключа в репо | Low | High | **High** | `.env` в .gitignore; ключи проверены, ingest-ключ — плейсхолдер | Ротация ключей в Supabase Dashboard |
| RLS-регрессия при добавлении вьюх/политик | Medium | Medium | **Medium** | Новые вьюхи с `security_invoker = on`; тест anon=0 строк | Откат миграции + повторная верификация |
| Streamlit Cloud не подхватывает секреты | Medium | Medium | **Medium** | Фикс ленивого чтения `1c2ca16` в main | Переключить app на main/пересоздать |
| Seed-регрессия (дрейф чисел) | Low | Low | **Low** | Детерминизм seed=42; метрики сверяются при каждом запуске | Перегенерить и сверить контрольные числа |

## 11. Validation Checkpoints

### Checkpoint 1: Конец Phase 1 (Data Platform)
**Критерии:**
- [ ] Seed воспроизводим: 8 000 / 82 301 / 1 086
- [ ] Аноним видит 0 строк; demo-юзер видит свою организацию
- [ ] Ingest-curl: 202 (валидный ключ), 401 (плохой ключ), 400 (пустой body)
**Если провален:** починить миграцию/политику до перехода к вьюхам.

### Checkpoint 2: Конец Phase 3 (A/B)
**Критерии:**
- [ ] AppTest 6/6, smoke HTTP 200
- [ ] Experiments: контроль 29.6% vs treatment 40.7%, p ≈ 1.7e-10
- [ ] Все 8 миграций применены идемпотентно; секреты не в git
**Если провален:** зафиксировать отклонение в статусе проекта (vault-заметка), не скрывать.

---

**Конец PRD**

*Шаблон: comprehensive. Документация as-is + 3 аппетита (Phase 4).*