# Renovara — AI renovation & sourcing tool (Armenia)

[![CI](https://github.com/MBaghdasryan/Interior-Design-tool/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/MBaghdasryan/Interior-Design-tool/actions/workflows/ci.yml)

Платформа превращает фото/видео/план пустой квартиры в реализуемый дизайн-проект из **реальных товаров**
с детерминированной сметой, поставщиками, RFQ и **рабочим альбомом A3** (по образцу
`Պարույր_Սևակ_5_Բնակարանի_դիզայն_նախագիծ.pdf`) + DXF/DWG (Autodesk APS), XLSX, GLB, JSON.

> Бренд — **Renovara** («AI renovation & sourcing tool»), рабочее имя ранее — FORMA AI. Имя задаётся `BRAND_NAME`, знак — `Logo` в `apps/web/src/components/AppShell.tsx` и `apps/web/public/logo.svg`, палитра брендбука — токены в `apps/web/src/styles.css`. Внутренние идентификаторы (`forma-api-dev`, ключи `forma.*` в localStorage, демо-почты `@forma.local`) намеренно не переименованы, чтобы не сбрасывать сессии и данные.

## Быстрый старт

```bash
cp .env.example .env
docker compose up --build
```

Откройте <http://localhost:8085> → «Войти» → любой демо-аккаунт (пароль `demo1234`, только dev).
Демо-проект «Демо-квартира · 3 комнаты» уже содержит подтверждённую геометрию — нажмите
«Найти товары и создать дизайн».

### Разработка без Compose

```bash
# API (Python 3.12)
cd apps/api && pip install -r requirements-dev.txt && uvicorn app.main:app --reload
# Web (Node 22)
cd apps/web && npm install && npm run dev      # http://localhost:5173 (проксирует /api → :8000)
```

### Проверки

Всё запускается в Docker (локально нужны только Docker и curl):

```bash
docker build -t forma-api-dev --build-arg DEV=1 apps/api
docker run --rm -v $PWD/apps:/apps -w /apps/api forma-api-dev sh -c "ruff check app tests evals && python -m pytest -q"   # 155 тестов
docker run --rm -v $PWD/apps:/apps -w /apps/web node:22-alpine sh -c "npm ci && node scripts/i18n-check.mjs && npm run -s api:check && npx tsc --noEmit -p . && npx vite build"
docker run --rm -v $PWD/apps:/apps -w /apps/web node:22-alpine node --experimental-strip-types scripts/export-server-dict.mjs --check
# E2E против запущенного compose (http://localhost:8085)
docker run --rm --network host -v $PWD/apps/web/e2e:/e2e mcr.microsoft.com/playwright/python:v1.49.0-jammy \
  sh -c "pip install -q playwright==1.49.0 axe-playwright-python==0.1.4 pillow==11.0.0 && for s in visual_a11y_e2e i18n_e2e routes_smoke notifications_e2e commerce_e2e search_e2e custom_furniture_e2e bim_pwa_e2e; do python /e2e/\$s.py || exit 1; done"
```

Служебные команды в стеке:

```bash
docker compose exec api alembic current            # миграции (применяются автоматически при старте)
docker compose exec api python -m app.seed_sources # идемпотентный seed 8 внешних источников
docker compose exec api python -m app.pilot_n99    # workspace и чек-лист пилота N99
docker compose exec api alembic downgrade -1       # откат последней миграции (каждая имеет downgrade)
docker compose exec api python -m evals.run --providers gemini,stub --suite all   # оценка AI → EVAL_REPORT.md
docker compose exec api python -m app.album.glossary export /tmp/terms.xlsx       # термины альбома для вычитки
```

## CI/CD

`.github/workflows/ci.yml` запускается на каждый push и PR:

| Задача | Что делает |
|---|---|
| backend | ruff; pytest (unit + integration, SQLite / fakeredis / moto); валидация артефактов (PDF, DXF, GLB, XLSX, CSV, JSON) |
| migrations | upgrade → downgrade → upgrade на Postgres |
| frontend | i18n-check; синхронность словаря для сервера; tsc; vite build; `npm audit` (prod, high) |
| security | pip-audit; trivy по образам api и web (critical, для которых есть исправление) |
| backend (доп.) | синхронность `openapi.json` с API |
| frontend (доп.) | сгенерированные TS-типы OpenAPI актуальны; контракт: каждый вызов фронтенда существует в API |
| e2e | `docker compose` с нуля → seed → Playwright: визуальная регрессия, axe (WCAG A/AA), регистрация, локализация, 22 маршрута, уведомления, каталог, коммерция, онбординг поставщика, поиск, мебель на заказ |
| images | публикация образов в GHCR при push в main и по тегам |
| deploy-staging | по тегу `v*`; нужны секреты `STAGING_HOST` / `STAGING_SSH_KEY`, пока не заданы |

## Честный статус

Платформа — **MVP на демо-данных**, не production. Статусы по каждой функции: [AUDIT_REPORT.md](AUDIT_REPORT.md),
[IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md), [TEST_REPORT.md](TEST_REPORT.md), [LOCALIZATION_REPORT.md](LOCALIZATION_REPORT.md),
[SECURITY_REPORT.md](SECURITY_REPORT.md), [EXTERNAL_CATALOG_REPORT.md](EXTERNAL_CATALOG_REPORT.md), [N99_VALIDATION_REPORT.md](N99_VALIDATION_REPORT.md).
Живьём проверены: Autodesk APS (DXF→DWG), Gemini (тексты, зрение, фото-рендер 2K — до исчерпания предоплаты 2026-10-22),
Domus и VLV (фоновый индекс). OpenAI — нет кредитов, Gemini — предоплата исчерпана; онлайн-оплата — ждёт договора
с провайдером (UI пишет «Integration pending»); пилот N99 — ждёт исходники. Итоги: [EVAL_REPORT.md](EVAL_REPORT.md).

## Что внутри

| Слой | Где | Кратко |
|---|---|---|
| Сцена (BuildingGraph, мм) | `apps/api/app/scene` | стены/проёмы/помещения/инженерия/объекты, правила эргономики, авто-расстановка, электрика, свет, камеры |
| AI | `apps/api/app/ai` | провайдеры OpenAI / Anthropic / Gemini / stub, версии промптов, structured outputs, fallback, учёт токенов |
| Каталог | `apps/api/app/catalog` | PIM, External Catalog Discovery (allowlist 8 магазинов АМ), SSRF/robots/rate-limit, снимок каталога проекта |
| Смета | `apps/api/app/estimate` | детерминированный расчёт, `Q=⌈A·(1+w)/A_pkg⌉`, статусы цен, диапазон бюджета |
| Альбом | `apps/api/app/album` | 41 лист A3 на hy/ru/en: ДН1 инженерный, ДН2 отделка, ДН3 развёртки, ДН4 визуализация, ДН5 спецификация/смета/утверждение |
| Autodesk APS | `apps/api/app/aps` | OAuth, OSS, Model Derivative (DWG/RVT/IFC→SVF2 + помещения), Design Automation (DXF→DWG), Viewer |
| Коммерция | `apps/api/app/commerce` | корзина → перепроверка цен → заказ → подтверждение поставщиком → доставка/монтаж; ledger двойной записи (только добавление), выплаты, тарифы, выручка; платёжный адаптер |
| Поиск | `apps/api/app/search` | эмбеддинги за интерфейсом (локальный многоязычный / Gemini), «похожие по фото», аналоги с разбором |
| Мебель на заказ | `apps/api/app/custom` | модули кухонь/шкафов/гардеробных/ТВ, ограничения производства, раскрой, цена по ставкам производителя, DXF/PDF |
| BIM | `apps/api/app/bim` | IFC4 экспорт и импорт (IfcOpenShell), Apple RoomPlan |
| Web | `apps/web` | маршруты hy/ru/en, PWA: лендинг, загрузка, геометрия, генерация, результаты, редактор 2D/3D, документы, закупки, мебель на заказ, каталог, кабинеты бюро и поставщика, админка с финансами |

Документация: [docs/](docs/) — продукт, архитектура, ERD, AI-пайплайн, безопасность, дорожная карта, ADR,
APS, альбом, внешний каталог и [список того, что было добавлено сверх ТЗ](docs/GAPS.md).
