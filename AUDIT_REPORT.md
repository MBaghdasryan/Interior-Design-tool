# AUDIT_REPORT — Renovara (аудит 2026-10-22)

Аудит сделан по `FORMA_CLAUDE_CODE_MASTER_AUDIT_IMPLEMENTATION_PROMPT_RU.md`, Phase A.
Правило отчёта: статус `VERIFIED` ставится только при наличии одного из доказательств — команды, теста, артефакта или E2E.

## 1. Обнаруженный стек

| Часть | Факт |
|---|---|
| Monorepo | `apps/api`, `apps/web`, `docs/`, `samples/`, `docker-compose.yml`; package manager — pip и npm (`package-lock.json`) |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic (с этой итерации), Pydantic 2 |
| Хранение и PDF | ReportLab (PDF), ezdxf (DXF), openpyxl (XLSX), собственный GLB-writer |
| Точки входа backend | `app.main:app` (uvicorn); `python -m app.migrate`; CLI `app.seed_sources`, `app.reclassify_external`, `app.pilot_n99` |
| Workers | отдельного worker-процесса нет: задачи выполняются в `ThreadPoolExecutor(max_workers=2)` внутри API (`app/jobs/runner.py`) |
| Frontend | React 18, Vite, TypeScript, Three.js; nginx отдаёт статику и проксирует `/api` |
| БД | PostgreSQL 16 в compose; SQLite в тестах |
| CI | **отсутствует** (нет `.github/`, нет pipeline) |
| Миграции | до аудита — `create_all`; теперь Alembic `0001_baseline` → `0002_i18n_sources` (head) |

## 2. Сверка числа тестов (47 / 48 → 66)

| Момент | Число | Источник | Объяснение |
|---|---|---|---|
| README до аудита | 47 | строка в README | число записано при первой сдаче |
| Первый отчёт в чате | 48 | вывод `pytest` | после README добавлен тест классификатора аксессуаров (`test_catalog_units.py`); README не обновили — отсюда расхождение |
| Сейчас | **66 collected / 66 passed / 0 skipped / 0 failed** | `docker run … forma-api-dev python -m pytest -q` → `66 passed in 12.51s` | +18 новых тестов: артефакты, i18n и trust, seed, SSRF content-type, N99, общий словарь, альбом без русского текста |

Разбивка по файлам (`pytest --co`):

| Файл | Тестов |
|---|---|
| `test_api_flow.py` | 4 |
| `test_aps.py` | 5 |
| `test_artifacts.py` | 8 |
| `test_catalog_units.py` | 30 |
| `test_design_core.py` | 12 |
| `test_i18n_trust.py` | 7 |

Каждый файл также проходит при отдельном запуске. Найдена и исправлена зависимость `test_rules_and_steps_carry_codes` от порядка запуска.

## 3. Матрица Claim → Evidence → Status → Gap → Action

| Заявление (README/ROADMAP до аудита) | Доказательство | Статус | Разрыв | Действие |
|---|---|---|---|---|
| Запуск `docker compose up --build` | стек пересобран, `api: healthy`, `/api/health → ok`, web 200 на :8085 | VERIFIED | README указывал порт 8080, compose — 8085 | README исправлен |
| i18n RU/HY/EN (Phase 1 «✓») | до аудита — **837 захардкоженных строк** в бандле, dashboard частично на русском | было STUB/DEMO → стало VERIFIED | P0-дефект | Phase B выполнена, см. `LOCALIZATION_REPORT.md` |
| Альбом A3 на 40+ листов | `samples/demo_album_{hy,ru,en}.pdf`: 41 стр. A3, шрифты встроены, штамп `/41` на 39/39 листах | VERIFIED (структура) | в hy/en альбоме были русские легенды, примечания и смета | исправлено, добавлен тест `test_album_has_no_russian_ui_text[hy,en]` |
| DXF открывается | `ezdxf.readfile` + `audit()`: 0 ошибок, 243 сущности, 15 слоёв, AC1032 | VERIFIED (валидатор ezdxf) | в AutoCAD вручную не открывали; DWG сделан из этого DXF через APS — косвенное подтверждение | — |
| DWG через Autodesk APS | живой WorkItem `success`, SVF2 manifest `success`, `samples/demo_aps.dwg` (заголовок AC1032) | VERIFIED live | — | — |
| Импорт RVT/IFC через APS | код и mock-тесты; живого RVT/IFC-файла не было | IMPLEMENTED_NOT_LIVE_VERIFIED | — | метки возможностей в `docs/APS.md` |
| GLB валиден | проверены заголовок glTF 2, длины чанков, accessors и инвентарь сцены (тест) | VERIFIED | glTF Validator (Khronos) не запускался | P2 |
| AI-провайдеры (Phase 3 «✓») | Gemini `gemini-3-flash-preview` — живой `change_command` прошёл; OpenAI — 429 `credit_balance_exhausted`; Anthropic — ключа нет | PARTIAL | eval-набора нет; генерация изображений заблокирована квотой | backoff, circuit breaker и trace id добавлены |
| Фотореалистичные визуализации | image-модели Gemini дают квоту 0, у OpenAI нет кредитов | BLOCKED_BY_EXTERNAL_DEPENDENCY | — | визуализации строятся 3D-движком из модели, это честно помечено |
| External Catalog, live Domus | 40 запросов → 20 товаров → 3 корректных реальных SKU в смете | VERIFIED live (ограниченно) | классификатор путал аксессуары | исправлено, см. `EXTERNAL_CATALOG_REPORT.md` |
| Идемпотентный seed 8 источников | 2-й запуск: все 8 строк `unchanged`; уникальный `canonical_domain` | VERIFIED | — | — |
| Tenant isolation | `test_tenant_isolation` (чужой проект → 404) и `project_access()` на эндпоинтах | PARTIAL | нет перебора всех эндпоинтов и фоновых задач | P1 |
| RFQ end-to-end | `test_full_flow`: RFQ к DEMO-поставщику → 409, к реальному → создан | VERIFIED (API) | реальная отправка поставщику (email) не реализована | P1 |
| SSE + восстановление | SSE и fallback на polling при `onerror` | PARTIAL | нет `Last-Event-ID`/resume; восстановление идёт только через polling | P2 |
| Версии редактора | версии и сравнение (`Versions.tsx`), approval замораживает версию (тест) | VERIFIED (API и маршрут) | — | — |
| Маршруты UI | `apps/web/e2e/routes_smoke.py`: 20/20 маршрутов без JS-ошибок и 5xx, 5 ролей | VERIFIED | — | — |
| Очередь задач | ThreadPool в процессе API | STUB/DEMO для production | нет Redis/RQ, задача теряется при рестарте | P1 |
| S3/MinIO | только `LocalStorage` | NOT IMPLEMENTED | — | P1 |
| CI/CD | нет | NOT IMPLEMENTED | — | P1 |
| Платежи и ledger | нет; заказ идёт через RFQ | NOT IMPLEMENTED | UI не показывает фиктивную оплату | P2 |
| Пилот N99 (Phase 7) | создан workspace и чек-лист; исходных материалов нет | NOT VALIDATED | — | см. `N99_VALIDATION_REPORT.md` |

## 4. Статусы roadmap

Галочки `✓` заменены честными метками: Architecture complete / MVP implemented / Integration pending /
Production hardening pending / Real-world validation pending. Таблица — в `docs/ROADMAP.md`.

## 5. Проверено фактически (по списку §1 промпта)

| Проверка | Результат |
|---|---|
| Docker Compose: пересборка, health/readiness | ✔ |
| Production build frontend (`tsc` и `vite build`) | ✔ |
| Сборка образа backend (`docker compose build api`) | ✔ |
| Соответствие frontend API-контрактам | ✔ `tsc` и 20 маршрутов без 5xx |
| Генерация A3 PDF на 41 лист | ✔ hy/ru/en, проверка по каждому листу (§12) |
| DXF (ezdxf audit) | ✔ |
| GLB | ✔ |
| RFQ | ✔ (API) |
| Domus live | ✔ |
| APS | ✔ live (DWG) |
| Восстановление SSE | ⚠ только polling |
| Tenant isolation на всех эндпоинтах и jobs | ⚠ частично |
