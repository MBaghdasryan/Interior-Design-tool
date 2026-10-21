# TEST_REPORT — 2026-10-22

Все команды запускались через Docker: в WSL нет node и pip.

## Сводка

| Проверка | Команда | Результат |
|---|---|---|
| Lint backend | `docker run --rm -v $PWD/apps:/apps -w /apps/api forma-api-dev ruff check app tests` | `All checks passed!` |
| Unit и integration backend | `… forma-api-dev python -m pytest -q` | **66 passed, 0 skipped, 0 failed** (12.5 s) |
| Изоляция тестов | запуск каждого `tests/test_*.py` отдельно | 6/6 файлов зелёные |
| Миграции | `docker compose exec api alembic current` | `0002_i18n_sources (head)`; Postgres перенесён с `create_all` (stamp 0001 → upgrade) |
| Typecheck frontend | `docker run --rm -v $PWD/apps/web:/w -w /w node:22-alpine npx tsc --noEmit -p .` | без ошибок |
| Build frontend | `… npx vite build` | `✓ built`; бандл 1.04 МБ, gzip 295 КБ (warning о размере чанка) |
| i18n coverage | `… node scripts/i18n-check.mjs` | `keys=932 incomplete=0 missing=0 orphans=0 hardcoded=0` |
| Словарь для сервера | `… node --experimental-strip-types scripts/export-server-dict.mjs --check` | `i18n_shared.json up to date (97 keys)` |
| E2E локализации | Playwright `apps/web/e2e/i18n_e2e.py` против compose | **22/22 PASS** |
| E2E маршрутов | Playwright `apps/web/e2e/routes_smoke.py` | **20/20 PASS** (designer, bureau_admin, supplier, platform_admin, аноним) |
| Валидация артефактов | `samples/` + pymupdf/ezdxf/openpyxl | см. ниже |
| Health | `curl localhost:8000/api/health` | `{"status":"ok"}` |

## Backend по файлам

| Файл | Тестов | Что покрывает |
|---|---|---|
| `test_api_flow.py` | 4 | критический путь: intake → геометрия → pipeline (external) → 3 варианта → AI-команда → правка → approval-snapshot → RFQ → альбом и экспорты; tenant isolation; права админки |
| `test_aps.py` | 5 | APS mock-транспорт: кэш токена, upload, translate, workitem, URN, извлечение помещений |
| `test_artifacts.py` | 8 | PDF (A3, число страниц, текст, встроенные шрифты, коды листов); DXF (audit, слои, единицы); GLB (структура, инвентарь); XLSX (hy/ru/en, суммы); CSV (BOM, `;`); JSON (схема); альбом hy/en без русского UI-текста |
| `test_catalog_units.py` | 30 | нормализация, классификатор и аксессуары, SSRF (private IP, redirect, DNS-rebinding, content-type, размер), robots, rate limit, breaker, бюджет запросов, идемпотентность seed |
| `test_design_core.py` | 12 | layout, правила, смета, оркестратор (fallback, валидация схемы, backoff без sleep) |
| `test_i18n_trust.py` | 7 | коды ошибок API, `PATCH /auth/me` locale, коды правил и шагов, уровни доверия и sign-off, DWG заблокирован на concept, общий словарь покрывает коды сервера, N99 workspace |

## Артефакты (`samples/`)

| Файл | Проверка | Результат |
|---|---|---|
| `demo_album_hy.pdf`, `_ru`, `_en` | страницы, размер, шрифты, штамп | 41 стр.; все A3 альбомные (1190.55×841.89 pt); 0 невстроенных шрифтов; штамп `ԴՆx.y` и `/41` на 39/39 листах; 0 текстовых блоков за полем страницы; 0 пустых листов |
| `demo_album_hy.pdf`, `_en` | кириллица | остались только данные: имя дизайнера, адрес, названия поставщиков DEMO |
| `demo_model.dxf` | `ezdxf.readfile` + `audit()` | AC1032, 0 ошибок, 243 сущности, 15 слоёв |
| `demo_model.glb` | заголовок и чанки | glTF v2, длина совпадает |
| `demo_estimate.xlsx` | структура | листы `Estimate`, `Sections`; 89 строк; заголовки на языке задания (en) |
| `demo_estimate.csv` | кодировка и разделитель | UTF-8 BOM, `;`, 74 строки |
| `demo_project.forma.json` | схема | `forma-project v1`, 28 объектов, 7 помещений |
| `demo_aps.dwg` | заголовок | `AC1032`, получен живым WorkItem Autodesk DA |

Скриншоты: `docs/screenshots/{dashboard,project,editor,catalog,client}_{hy,ru,en}.png`, `docs/screenshots/n99_pilot_{hy,en}.png`.

## Не покрыто (честно)

- Нет CI: всё запускалось вручную.
- Нет тестов миграций в CI. Upgrade проверен вручную на Postgres; downgrade `0002` написан, но не запускался.
- Нет нагрузочных тестов, нет тестов восстановления SSE.
- Нет перебора tenant isolation по всем эндпоинтам и фоновым задачам.
- glTF Validator (Khronos) и открытие DXF в AutoCAD вручную не выполнялись.
- Нет eval-набора для AI (распознавание планов, команды, grounding).
