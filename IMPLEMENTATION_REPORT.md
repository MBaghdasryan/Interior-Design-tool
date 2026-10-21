# IMPLEMENTATION_REPORT — итерация «аудит + P0 локализация + достоверность»

Статусы:
- `VERIFIED` — доказано тестом, артефактом или E2E;
- `IMPLEMENTED_NOT_LIVE_VERIFIED` — код есть, но живой проверки не было;
- `PARTIAL`;
- `STUB/DEMO`;
- `NOT IMPLEMENTED`;
- `BLOCKED_BY_EXTERNAL_DEPENDENCY`.

## Phase B — локализация (P0) — VERIFIED

Подробности — в `LOCALIZATION_REPORT.md`.

| Что | Файлы |
|---|---|
| Движок i18n | `apps/web/src/i18n/index.ts` |
| Словари | `apps/web/src/i18n/dict/*.ts` (932 ключа) |
| Переведены все страницы и компоненты | `apps/web/src/pages/*`, `apps/web/src/components/*` |
| Форматирование по локали | `src/lib/format.ts` |
| Перевод сообщений сервера | `src/lib/messages.ts` |
| Коды ошибок API | `apps/api/app/errors.py` (`ApiError(status, code, **params)`, единый формат ответа) |
| Язык в профиле | `PATCH /auth/me` |
| Коды и параметры | правила (`scene/rules.py`), шаги задач (`jobs/runner.py`, `pipeline.py`, `documents.py`), уведомления сметы (`estimate/estimator.py`) |
| Альбом hy/en без русской лексики | `app/album/i18n.py` (`TX`, `shared()`, `line_name`, `rule_text`, `elec_note`), `app/album/sheets.py` |
| Общий словарь UI ↔ документы | `apps/web/scripts/export-server-dict.mjs` → `apps/api/app/i18n_shared.json` |
| Стабильный ключ заметки у розеток | `Electrical.note_key` (`scene/model.py`, `scene/layout.py`) |
| Проверки | `apps/web/scripts/i18n-check.mjs`, `apps/web/e2e/i18n_e2e.py` |

## Phase C — три уровня достоверности — VERIFIED (API, UI)

- `app/trust.py`: уровни, чек-листы перехода, экспорты по уровням, ограничения, provenance.
- Эндпоинты:
  - `GET /projects/{pid}/trust`;
  - `POST /projects/{pid}/trust/signoff` — только verifier / bureau_admin / platform;
  - `POST /projects/{pid}/trust/advance`.
- DWG/DXF заблокированы на уровне Concept (409). Заказ изделий по размерам — только на Production Ready.
- UI: `TrustPanel.tsx` на экранах геометрии и результатов.
- Статусы roadmap заменены честными метками.

## Phase D — External catalog — VERIFIED

Подробности — в `EXTERNAL_CATALOG_REPORT.md`.

- **Миграция `0002_i18n_sources`:**
  - `canonical_domain` UNIQUE;
  - `connector_type`, `live_enabled`, `policy_status`, `health_status`;
  - `generation_steps.params`.
- **Seed:**
  - `seed_external_sources()` с идемпотентным upsert;
  - CLI `app/seed_sources.py`;
  - `SEED_POLICY`: Domus — live, Profal — RFQ, остальные — disabled.
- **`SafeFetcher`:** проверка IP пира, content-type и размера, бюджет запросов.
- **Live:** включается только при `EXTERNAL_FETCH_LIVE` **и** `source.live_enabled`.
- **Классификатор:** стоп-слова и аксессуары; `app/reclassify_external.py`.

## Phase E — AI — PARTIAL

| Что | Статус |
|---|---|
| Абстракция провайдеров (OpenAI Responses / Anthropic tool-use / Gemini `responseJsonSchema` / stub), версии промптов, валидация схемы, fallback, кэш, учёт токенов | IMPLEMENTED |
| Новое: экспоненциальный backoff между повторами (429/503), circuit breaker на провайдера (3 ошибки → пауза 5 мин), trace id в логах, обрезка ошибок в логах | VERIFIED (тесты оркестратора) |
| Gemini `gemini-3-flash-preview` — живой `change_command` | VERIFIED live |
| OpenAI `gpt-5.5` | BLOCKED_BY_EXTERNAL_DEPENDENCY: 429 `credit_balance_exhausted` |
| Gemini Pro и image-модели | BLOCKED_BY_EXTERNAL_DEPENDENCY: квота free tier = 0 |
| Фотореалистичный рендер, маски, регенерация зоны, product-grounding score | NOT IMPLEMENTED (граница интеграции есть: шаг `visuals` честно пишет «провайдер изображений не подключён») |
| Evaluation dataset и harness | NOT IMPLEMENTED (P1) |
| Квоты на тенанта и лимиты стоимости | NOT IMPLEMENTED (usage пишется в `AIUsage`) |

## Лендинг «до / после» — VERIFIED (скриншот)

- Сторона «после» — реалистичный кукольный домик на Three.js в режиме высокого качества:
  - PBR-текстуры (ёлочка, плитка, ткань, шпон);
  - RoomEnvironment, GTAO;
  - скруглённая мебель, рамы окон, приоткрытые двери, шторы, подвесы со светом.
- Код: `src/lib/scene3d.ts`, `src/lib/textures.ts`, `src/components/Scene3D.tsx`.
- Фото-рендер ИИ не используется: он заблокирован квотой (см. выше).

## Phase F — hardening — PARTIAL

| Что | Статус |
|---|---|
| Alembic вместо `create_all`: `0001_baseline`, `0002`; `app/migrate.py` штампует старую БД и делает upgrade; Dockerfile запускает миграции перед uvicorn | VERIFIED (Postgres перенесён) |
| Security headers (nginx), CSP Report-Only | PARTIAL |
| Ключ идемпотентности альбома включает `RENDERER_VERSION` (иначе после исправлений отдавался старый PDF) | VERIFIED |
| Redis-очередь, отдельные workers, S3/MinIO, OpenTelemetry, бэкапы, CI/CD, staging | NOT IMPLEMENTED (`docs/GAPS.md`, P1) |
| Cookies/CSRF/MFA/rate limit | NOT IMPLEMENTED (`SECURITY_REPORT.md` S1–S5) |

## Phase G — артефакты и N99

- **Артефакты** — VERIFIED (`TEST_REPORT.md`):
  - 41 лист A3 на hy/ru/en;
  - DXF audit без ошибок;
  - GLB, XLSX, CSV, JSON;
  - живой DWG.
- **N99** — workspace, манифест, API и UI созданы; пилот **не пройден** (`N99_VALIDATION_REPORT.md`).

## Изменённые и новые файлы

**Backend (`apps/api`)**
- `alembic/` (новые миграции)
- `app/migrate.py`, `app/errors.py`, `app/trust.py`, `app/pilot.py`, `app/pilot_n99.py`, `app/seed_sources.py`, `app/reclassify_external.py`, `app/i18n_shared.json`
- `app/config.py`, `app/main.py`, `app/models.py`, `app/seed.py`
- `app/catalog/{sources,net,normalize,discovery}.py`, `app/catalog/connectors/{others,jsonld}.py`
- `app/scene/{rules,layout,model}.py`, `app/estimate/estimator.py`
- `app/jobs/{runner,pipeline,documents}.py`
- `app/album/{i18n,sheets,builder}.py`
- `app/exports/files.py`, `app/ai/orchestrator.py`
- `app/routers/{projects,auth,documents,admin}.py`
- `Dockerfile`
- `tests/test_artifacts.py`, `tests/test_i18n_trust.py` (новые) и правки остальных тестов

**Frontend (`apps/web`)**
- `src/i18n/**`
- `src/lib/{api,format,messages,scene3d,textures}.ts`
- все `src/pages/*`
- `src/components/{AppShell,ui,EstimateView,CommandDrawer,AlternativesDrawer,PlanView,BeforeAfter,ApsViewer,Scene3D,TrustPanel,PilotPanel}.tsx`
- `scripts/{i18n-check,export-server-dict}.mjs`, `e2e/{i18n_e2e,routes_smoke}.py`
- `nginx.conf`

**Корень репозитория**
- `.env.example`, `README.md`
- `docs/{ROADMAP,GAPS,APS,SECURITY}.md`
- `samples/*`, `docs/screenshots/*`
- `*_REPORT.md`

## Миграции

| Ревизия | Содержание |
|---|---|
| `0001_baseline` | схема на момент аудита (для существующих БД — `stamp`) |
| `0002_i18n_sources` | колонки `external_sources` + UNIQUE `canonical_domain`; `generation_steps.params`. Есть `downgrade()` |

Поле `Electrical.note_key` хранится в JSON сцены, поэтому миграция для него не нужна.
