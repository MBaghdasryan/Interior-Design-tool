# Renovara — AI renovation & sourcing tool (Armenia)

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
docker run --rm -v $PWD/apps:/apps -w /apps/api forma-api-dev sh -c "ruff check app tests && python -m pytest -q"   # 66 тестов
docker run --rm -v $PWD/apps:/apps -w /apps/web node:22-alpine sh -c "npm ci && node scripts/i18n-check.mjs && npx tsc --noEmit -p . && npx vite build"
docker run --rm -v $PWD/apps:/apps -w /apps/web node:22-alpine node --experimental-strip-types scripts/export-server-dict.mjs --check
# E2E против запущенного compose (http://localhost:8085)
docker run --rm --network host -v $PWD/apps/web/e2e:/e2e mcr.microsoft.com/playwright/python:v1.49.0-jammy \
  sh -c "pip install -q playwright==1.49.0 && BASE=http://localhost:8085 python /e2e/i18n_e2e.py && BASE=http://localhost:8085 python /e2e/routes_smoke.py"
```

Служебные команды в стеке:

```bash
docker compose exec api alembic current            # миграции (применяются автоматически при старте)
docker compose exec api python -m app.seed_sources # идемпотентный seed 8 внешних источников
docker compose exec api python -m app.pilot_n99    # workspace и чек-лист пилота N99
```

## Честный статус

Платформа — **MVP на демо-данных**, не production. Статусы по каждой функции: [AUDIT_REPORT.md](AUDIT_REPORT.md),
[IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md), [TEST_REPORT.md](TEST_REPORT.md), [LOCALIZATION_REPORT.md](LOCALIZATION_REPORT.md),
[SECURITY_REPORT.md](SECURITY_REPORT.md), [EXTERNAL_CATALOG_REPORT.md](EXTERNAL_CATALOG_REPORT.md), [N99_VALIDATION_REPORT.md](N99_VALIDATION_REPORT.md).
Живьём проверены: Autodesk APS (DXF→DWG), Gemini (`gemini-3-flash-preview`), Domus live-каталог. OpenAI — нет кредитов;
фото-рендер ИИ — заблокирован квотой; пилот N99 — ждёт исходники.

## Что внутри

| Слой | Где | Кратко |
|---|---|---|
| Сцена (BuildingGraph, мм) | `apps/api/app/scene` | стены/проёмы/помещения/инженерия/объекты, правила эргономики, авто-расстановка, электрика, свет, камеры |
| AI | `apps/api/app/ai` | провайдеры OpenAI / Anthropic / Gemini / stub, версии промптов, structured outputs, fallback, учёт токенов |
| Каталог | `apps/api/app/catalog` | PIM, External Catalog Discovery (allowlist 8 магазинов АМ), SSRF/robots/rate-limit, снимок каталога проекта |
| Смета | `apps/api/app/estimate` | детерминированный расчёт, `Q=⌈A·(1+w)/A_pkg⌉`, статусы цен, диапазон бюджета |
| Альбом | `apps/api/app/album` | 41 лист A3 на hy/ru/en: ДН1 инженерный, ДН2 отделка, ДН3 развёртки, ДН4 визуализация, ДН5 спецификация/смета/утверждение |
| Autodesk APS | `apps/api/app/aps` | OAuth, OSS, Model Derivative (DWG/RVT/IFC→SVF2 + помещения), Design Automation (DXF→DWG), Viewer |
| Web | `apps/web` | 20 маршрутов (hy/ru/en): лендинг, загрузка, проверка геометрии, генерация, результаты, редактор 2D/3D, документы, закупки, версии, кабинеты, админка |

Документация: [docs/](docs/) — продукт, архитектура, ERD, AI-пайплайн, безопасность, дорожная карта, ADR,
APS, альбом, внешний каталог и [список того, что было добавлено сверх ТЗ](docs/GAPS.md).
