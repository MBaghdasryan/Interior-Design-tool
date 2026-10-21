# Дорожная карта

Статусы — по доказательствам из `AUDIT_REPORT.md` и `TEST_REPORT.md`, а не по наличию кода.

## Метки

| Метка | Значение |
|---|---|
| Architecture complete | архитектура и модели готовы, функция не подтверждена в живой среде |
| MVP implemented | работает и подтверждено тестами, артефактом или E2E на демо-данных |
| Integration pending | зависит от внешних ключей, фидов или провайдеров |
| Production hardening pending | нужна инфраструктура и безопасность для прод |
| Real-world validation pending | не проверено на реальной квартире и с реальным специалистом |

## Фазы

| Фаза | Содержание | Статус |
|---|---|---|
| 0 Discovery | аудит образца альбома и магазинов, архитектура, ERD, ADR | Architecture complete |
| 1 Foundation | API, БД, Alembic, RBAC/tenants, хранилище, задачи, UI-kit, i18n hy/ru/en | MVP implemented · Production hardening pending (Redis, S3, CI, cookies/CSRF) |
| 2 Intake | загрузка и проверка файлов, контрольные размеры, проверка геометрии, DXF-импорт, APS-импорт | MVP implemented · Integration pending (vision-распознавание растровых планов; RVT/IFC live) |
| 3 AI Autopilot v1 | провайдеры, ТЗ, пайплайн, 3 варианта, версии промптов, usage, backoff/breaker | MVP implemented (Gemini live) · Integration pending (OpenAI credits, image-модели, eval-набор) |
| 4 Catalog grounding | PIM, CSV/XLSX, External Catalog (Domus live, Profal RFQ), снимок, аналоги | MVP implemented · Integration pending (официальные фиды 6 магазинов) |
| 5 Spec & estimate | смета, снимки, альбом A3 41 лист hy/ru/en, DXF/XLSX/CSV/GLB/JSON, DWG через APS, RFQ | MVP implemented · Real-world validation pending (проверка архитектором) |
| 6 Refinement | 2D/3D-редактор, hotspots, AI-команды, замена аналогом, версии | MVP implemented |
| C Trust levels | Concept / Verified / Production, sign-off, блокировки экспортов | MVP implemented |
| 7 Pilot N99 | workspace, манифест, чек-лист (`N99_VALIDATION_REPORT.md`) | Real-world validation pending — ждём исходники |
| Коммерция | ledger, комиссии, платежи, доставка/монтаж, споры | Architecture complete (частично) · NOT IMPLEMENTED (ledger, платежи) |

## Backlog

Колонки: приоритет, задача, ответственный (owner type), от чего зависит.

| P | Задача | Owner | Зависимость |
|---|---|---|---|
| P0 | Пройти пилот N99 end-to-end | product + дизайнер бюро + verifier | материалы владельца |
| P0 | Cookies HttpOnly + CSRF, rate limit, отключение демо-аккаунтов на прод | backend/devops | — |
| P0 | Официальный фид хотя бы одного магазина помимо Domus | бизнес | договор с магазином |
| P1 | Пополнить OpenAI / paid tier Gemini → image-провайдер, фото-рендер по SKU-манифесту | владелец аккаунтов → AI dev | биллинг |
| P1 | Eval-набор: 50 планов, команды, grounding | AI dev + дизайнеры | размеченные проекты |
| P1 | Redis + RQ workers, S3/MinIO, CI (lint/types/tests/e2e/build/migrations), бэкапы | devops | — |
| P1 | Полный тест tenant isolation, ClamAV, MFA, сброс пароля | backend/QA | — |
| P1 | Вычитка армянской терминологии альбома архитектором | дизайнер бюро | — |
| P2 | Ledger, комиссии, платёжный провайдер АМ | backend + бизнес | выбор провайдера |
| P2 | IFC-экспорт (IfcOpenShell), Revit DA, Archicad-коннектор, BCF, OpenUSD | CAD/BIM dev | APS / лицензии |
| P2 | LiDAR (RoomPlan), мобильный обмер | mobile dev | iOS-разработчик |
| P2 | Параметрическая мебель на заказ, производственные чертежи кухонь и шкафов | CAD dev + производитель | партнёр-производитель |
| P2 | SSE resume (`Last-Event-ID`), OpenTelemetry | backend | — |
