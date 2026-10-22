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

| Фаза | Содержание | Статус (2026-10-22) |
|---|---|---|
| 0 Discovery | аудит образца альбома и магазинов, архитектура, ERD, ADR-001…011 | Architecture complete |
| 1 Foundation | API, БД, Alembic 0001–0012, RBAC/tenants (тест по всем маршрутам), Redis/RQ, S3, CI/CD, MFA, ClamAV, CSP, персональные данные | MVP implemented · Integration pending (VPS/домен/SMTP) |
| 2 Intake | загрузка, контрольные размеры, DXF, APS, IFC импорт/экспорт, RoomPlan, фото-обследование | MVP implemented · Real-world validation pending (RVT, реальный скан) |
| 3 AI Autopilot | провайдеры, бюджеты по организациям, оценки, фото-рендер с grounding | MVP implemented · Integration pending (кредиты AI) |
| 4 Catalog | PIM, фиды с защитой, Domus live, VLV индекс по расписанию, TTL, алерты, онбординг поставщиков, ассеты, поиск и аналоги | MVP implemented · Integration pending (официальные фиды, нейропоиск) |
| 5 Spec & estimate | смета, альбом A3 hy/ru/en, DXF/XLSX/CSV/GLB/JSON/IFC, DWG через APS | MVP implemented · Real-world validation pending (вычитка) |
| 6 Refinement | редактор, AI-команды, версии, уведомления | MVP implemented |
| 7 Pilot N99 | workspace, отчёт пилота | Real-world validation pending |
| 8 Commerce | корзина → заказ → ledger двойной записи, комиссии, выплаты, тарифы, выручка | MVP implemented · Integration pending (платёжный провайдер) |
| 9 Custom furniture | конфигуратор модулей, раскрой, DXF/PDF, заказ на Production Ready | MVP implemented · Integration pending (производитель-партнёр) |

## Backlog

| P | Задача | Owner | Зависимость |
|---|---|---|---|
| P0 | Пилот N99 end-to-end (включая RoomPlan-скан) | product + бюро + verifier | материалы владельца |
| P0 | Пополнить Gemini/OpenAI → повтор оценок, нейропоиск | владелец аккаунтов → AI dev | биллинг |
| P0 | VPS + домен + SMTP → staging по тегу | devops | владелец |
| P1 | Официальный фид второго магазина | бизнес | договор |
| P1 | Договор с платёжным провайдером АМ → адаптер Idram/ArCa/Ameriabank | backend + бизнес | договор, документация API |
| P1 | Вычитка армянской терминологии (комплект готов) | архитектор | — |
| P1 | Производитель-партнёр: ставки, ограничения, проверка чертежей | CAD dev + производитель | партнёр |
| P2 | pgvector на новом кластере, нейроэмбеддинги | backend | рост каталога, кредиты |
| P2 | BCF-обмен замечаниями (после стабильного IFC с бюро) | CAD/BIM dev | бюро с BIM |
| P2 | vite 8 / react-router 7 | frontend dev | — |
| P2 | Внешний пентест | security owner | бюджет |
