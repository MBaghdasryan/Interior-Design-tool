# MASTER PROMPT ДЛЯ CLAUDE CODE

## FORMA — аудит репозитория, полная локализация, исправление архитектуры и доведение MVP до проверяемого состояния

Ты работаешь как principal software architect, AI/CV engineer, BIM/CAD engineer, product designer, QA lead, DevOps/SRE и security engineer. Работай непосредственно с исходным репозиторием FORMA. Не ограничивайся документами и не повторяй прежние заявления о готовности без доказательств.

Главный принцип этой итерации: **repository truth over documentation**. Истиной считаются только код, схема БД, миграции, реально выполненные команды, тесты, собранные артефакты и проверенные пользовательские сценарии.

Не задавай вопросы, ответ на которые можно получить исследованием репозитория. Запрашивай у владельца только отсутствующие секреты, внешние учётные данные, юридические разрешения или необратимые продуктовые решения. Не удаляй существующую функциональность и не переписывай работающие модули без необходимости. Все изменения должны быть обратимыми, миграции — идемпотентными, а конфигурация — безопасной по умолчанию.

---

## 1. Сначала проведи независимый технический аудит

До реализации изменений:

1. Изучи весь репозиторий, `README`, `PRODUCT`, `ARCHITECTURE`, `ROADMAP`, `GAPS`, `ALBUM`, `APS`, `EXTERNAL-CATALOG`, Docker-файлы, CI, миграции, тесты и env-примеры.
2. Определи реальный стек, package manager, структуру monorepo, точки входа frontend/backend/workers.
3. Создай матрицу `Claim → Evidence → Status → Gap → Action`.
4. Отдельно проверь расхождение: ранее заявлялось 48 тестов, а в README — 47. Покажи фактическое число collected/passed/skipped/failed тестов.
5. Ничего не помечай `Done`, если это не подтверждено командой, тестом, скриншотом, созданным артефактом или end-to-end сценарием.

Проверь фактически:

- запуск Docker Compose с чистого окружения;
- health/readiness всех сервисов;
- production build frontend и backend;
- соответствие frontend API-контрактам;
- существование всех заявленных UI-маршрутов;
- работоспособность основных кнопок и форм;
- tenant isolation на всех endpoints и фоновых задачах;
- генерацию фактического A3 PDF на 41 лист;
- открытие DXF валидатором/совместимым приложением;
- валидность GLB и состав сцены;
- сохранение и сравнение версий редактора;
- RFQ end-to-end;
- восстановление SSE после разрыва;
- внешний каталог и Domus live-fetch;
- импорт/просмотр Autodesk APS только в пределах реально поддерживаемых возможностей.

Статусы roadmap замени на честные:

- `Architecture complete`;
- `MVP implemented`;
- `Integration pending`;
- `Production hardening pending`;
- `Real-world validation pending`.

Не используй общий символ `✓` для неподтверждённых фаз.

---

## 2. P0: полностью исправь локализацию интерфейса

Сейчас в публичном интерфейсе необходимо добавить армянский и русский языки. В dashboard при смене языка переводится только меню, а содержимое страниц остаётся на русском. Это критический дефект. Исправь локализацию целиком.

### Обязательные языки

- армянский — `hy`, полноценный профессиональный перевод;
- русский — `ru`;
- английский — `en`.

Армянский должен использовать армянский алфавит и профессиональную терминологию архитектуры, интерьера, строительства, смет и комплектации. Не используй машинную транслитерацию.

### Что должно переводиться

Локализуй не только sidebar/header, но весь пользовательский контент:

- публичный сайт, landing и onboarding;
- login, registration, password reset, email verification;
- dashboard и все кабинеты;
- названия страниц, tabs, breadcrumbs, cards, KPI;
- заголовки таблиц, filters, sort, pagination;
- формы, labels, placeholders, helper text;
- кнопки, dropdown, modals, confirmations;
- empty/loading/error/success states;
- validation messages и API errors;
- tooltips, notifications, toasts;
- редактор 2D/3D, панели инструментов, properties inspector;
- AI Autopilot, варианты, статус генерации и план изменений;
- каталог, карточки товаров, поставщики, аналоги, корзина;
- смета, RFQ, коммерческое предложение;
- кабинеты бюро, клиента, поставщика и platform admin;
- версии, сравнение и согласование;
- emails, системные уведомления и экспортируемые документы;
- PDF A3, XLSX/CSV и пользовательские подписи в DXF/GLB metadata;
- статусы, enum-значения, названия ролей и permissions.

### Архитектура i18n

1. Найди и вынеси все захардкоженные пользовательские строки из компонентов.
2. Используй единый i18n framework, соответствующий текущему стеку; не создавай второй параллельный механизм.
3. Раздели словари по доменам: `common`, `auth`, `dashboard`, `projects`, `editor`, `catalog`, `estimate`, `rfq`, `supplier`, `client`, `admin`, `errors`, `album`.
4. Добавь fallback `hy → en` или выбранную централизованную стратегию; отсутствующий ключ не должен показывать raw key пользователю в production.
5. Сохраняй язык в профиле пользователя; для гостя — cookie/local preference и browser locale. При login синхронизируй выбор без визуального скачка.
6. Форматируй даты, числа, площади, размеры, проценты и валюту через locale-aware utilities. Валюта по умолчанию — AMD, но хранить суммы нужно численно, не строками.
7. Backend должен возвращать стабильные error codes, а frontend — переводить их. Не возвращай русские сообщения как единственный API-контракт.
8. Для сущностей каталога поддержи локализованные поля/переводы, но не дублируй SKU, цены и технические числа.
9. Добавь dev-проверку missing keys и duplicate/orphan keys.

### Acceptance criteria локализации

- На каждом основном route переключение `hy/ru/en` меняет весь UI без reload.
- После reload и нового login язык сохраняется.
- На армянском и английском нет оставшихся русских UI-строк, кроме пользовательского контента и официальных названий.
- Нет overflow/обрезания ключевых кнопок и таблиц.
- Созданы automated tests для locale switch, persistence, API errors и минимум одного полного проекта.
- Созданы скриншоты одинаковых экранов на `hy`, `ru`, `en`: dashboard, project editor, catalog, estimate, client approval.
- Добавлен отчёт о найденных hardcoded strings до и после исправления.

---

## 3. Исправь продуктовую достоверность: три уровня проекта

Введи в доменную модель, UI, API, экспорт и audit trail три уровня достоверности:

1. **Concept Estimate** — ориентировочная концепция по фотографиям. Нельзя обещать точную геометрию, финальную смету и производственные чертежи.
2. **Verified Design** — проект на основании плана и контрольных размеров; пригоден для детальной проработки после проверки специалистом.
3. **Production Ready** — подтверждённые профессиональные обмеры или LiDAR, проверка специалистом и обязательные approvals.

Для каждого уровня реализуй:

- requirements и недостающие входные данные;
- badge/status и объяснение ограничений;
- доступные/заблокированные exports;
- предупреждения в AI-результатах, смете и альбоме;
- переход на следующий уровень с checklist и ответственным лицом;
- provenance данных: фото, план, размеры, LiDAR, ручные корректировки;
- audit record подтверждения архитектором/инженером.

Автоматические планы розеток, света, сантехники, вентиляции и отопления всегда обозначай как preliminary proposal, пока их не проверил профильный специалист. Не позиционируй их как финальный инженерный проект. Предусмотри будущие поля для норм, нагрузок, автоматов/УЗО, сечений кабеля, уклонов канализации, давления воды, отопительных расчётов и мокрых зон.

---

## 4. Ядро продукта и правильный пользовательский путь

Платформа соединяет четыре стороны:

- владельцы квартир;
- дизайнеры и интерьерные бюро;
- производители мебели и материалов;
- магазины и поставщики.

Главная цепочка:

`план/фото → распознавание → варианты дизайна → реальные товары → ручная редакция → проверка → смета → согласование → заказ → производство/доставка/монтаж`.

Сохрани и доведи три связанных интерфейса:

1. **Кабинет интерьерного бюро** — проекты, клиенты, бюджеты, поставщики, задачи, спецификации и коммерческие показатели.
2. **Профессиональный редактор** — ядро платформы: 2D/3D, размеры, стены/окна/двери, мебель, материалы, освещение, реальные товары, переключатель `Концепция / Реальные товары`, бюджет и смета.
3. **Мобильный кабинет клиента** — визуализации, этапы, кликабельные товары, замена на аналоги, утверждение спецификации, доставки и монтажа.

Следующие обязательные слои:

- кабинет поставщика/производителя;
- PIM и параметрическая карточка продукта;
- загрузка и распознавание плана;
- AI-генерация нескольких вариантов;
- редактор мебели made-to-order;
- коммерческое предложение;
- транзакции, комиссии и settlement ledger;
- производство, доставка, монтаж, отмена и dispute flow.

Каждый объект на визуализации должен иметь устойчивую связь с product/variant SKU либо явно маркироваться как conceptual/custom-made. Карточка продукта должна включать производителя, модель, размеры, цвет, материал, цену, наличие, срок доставки/изготовления, canonical URL, аналоги, источник цены и комиссию платформы.

---

## 5. Исправь бизнес-модель и коммерческий контур

Не моделируй продукт только как SaaS-подписку. Основной долгосрочный денежный поток — транзакции, комплектация, собственная мебель и производство.

Добавь конфигурируемые revenue streams:

| Направление | Кто платит | Модель |
|---|---|---|
| Подписка бюро | дизайнер/бюро | месячный/годовой тариф |
| AI-проект | клиент или бюро | за помещение, м² или проект |
| AI-визуализации | дизайнер | generation credits/packages |
| Продажа собственных продуктов | клиент | торговая/производственная маржа |
| Продажа партнёрских товаров | поставщик | комиссия с заказа |
| Комплектация | клиент | процент от бюджета/фиксированная услуга |
| Каталог/PIM | производитель | подписка или плата за SKU |
| Qualified leads | поставщик | плата за подтверждённый лид |
| White label | девелопер/бюро | setup + license |
| Production exports | бюро/мастер | оплата за CAD/BIM/чертежи |

Спроектируй ledger, но не имитируй реальный payment processing без провайдера. Поддержи:

- platform commission;
- designer/bureau commission;
- supplier payable;
- discounts и promo funding;
- taxes/fees как конфигурируемые поля;
- refund/cancellation/dispute states;
- order confirmation;
- delivery, installation и production milestones;
- immutable financial audit trail;
- idempotency keys для денежных операций;
- reconciliation и экспорт отчётов.

Если платежи ещё не подключены, UI должен честно показывать `Integration pending`, а не успешную оплату-заглушку.

---

## 6. AI Autopilot: заменить имитацию на provider-based архитектуру

Существующий rules/stub режим сохрани как fallback и ясно маркируй `Deterministic demo mode`. Создай provider abstraction и capability registry:

- LLM/vision: GPT, Gemini; Claude для длинной документации при наличии интеграции;
- OCR/plan parsing;
- image generation: Gemini Image, OpenAI Image, FLUX/Stable Diffusion;
- geometry control: depth, segmentation, ControlNet или аналог;
- rendering: Blender/Cycles как отдельный production renderer;
- CV/geometry: OpenCV, segmentation, depth estimation;
- web 3D: Three.js/Babylon.js, glTF/GLB.

Не хардкодь провайдера. Добавь env/config, provider health, timeout, retry, circuit breaker, cost limits, per-tenant quota и usage ledger.

Structured output должен проходить schema validation. Ошибочный ответ модели не должен портить проект. Добавь versioned prompts, reproducibility metadata, trace id и safe retry.

Создай evaluation dataset и test harness минимум для:

- планов разного качества;
- фото нескольких комнат;
- стен, дверей и окон;
- сохранения геометрии;
- проходов и конфликтов мебели;
- соответствия product dimensions;
- количества материалов;
- grounding визуализированного объекта на SKU.

Фотореалистичный pipeline должен поддерживать сохранение камеры/геометрии, маску зоны, повторную генерацию отдельной области, high-resolution export и product-grounding score. Если точное соответствие SKU невозможно — помечай объект как визуальный аналог.

---

## 7. Каталог, PIM и External Catalog Discovery

Основной каталог должен поддерживать official feeds/API/CSV/XLSX/manual import и только затем осторожный публичный discovery. Для каждой цены/наличия храни source, fetched_at, TTL, confidence и canonical URL. Цена с истёкшим TTL должна быть явно помечена и повторно подтверждаться перед заказом.

### Идемпотентный seed восьми источников

External Catalog Discovery включён через environment variables, но необходимо проверить и применить идемпотентный seed `ExternalSource` для:

- Domus — `domus.am`;
- Ideal System — `idealsystem.am`;
- Nor Tun — `nortun.am`;
- Effect Group / Shen — `effectgroup.am`;
- Lideria — `lideria.am`;
- Profal — `profalgroup.com`;
- VLV — `vlv.am`;
- Vega — `vega.am`.

Требования:

1. Не создавай дубликаты при повторном запуске.
2. Используй normalized canonical domain как уникальное поле и DB unique constraint.
3. По умолчанию включи `live-fetch` только для Domus.
4. Profal настрой как `RFQ connector`.
5. Остальные источники оставь `pending/disabled` до официального feed/API или завершения policy audit.
6. Не обходи `robots.txt`, CAPTCHA, login, anti-bot или paywall.
7. Allowlist хранится в БД; live fetching opt-in.
8. Поддержи sitemap/product-page strategy только там, где это разрешено.

Проверь/добавь переменные:

```env
EXTERNAL_CATALOG_ENABLED=true
EXTERNAL_FETCH_LIVE=false
EXTERNAL_FETCH_USER_AGENT=FormaAI-CatalogBot/0.1 (+https://cubeappmaker.agency/bot)
EXTERNAL_PRICE_TTL_H=24
EXTERNAL_AVAILABILITY_TTL_H=12
EXTERNAL_FETCH_TIMEOUT_S=15
EXTERNAL_FETCH_MAX_RETRIES=2
EXTERNAL_FETCH_RATE_LIMIT_S=3
EXTERNAL_FETCH_MAX_REDIRECTS=3
EXTERNAL_FETCH_CONCURRENCY=1
EXTERNAL_CACHE_ENABLED=true
EXTERNAL_ROBOTS_ENFORCED=true
EXTERNAL_SSRF_PROTECTION=true
```

`EXTERNAL_FETCH_LIVE=false` должен оставаться безопасным default. Включение live-fetch не должно автоматически включать все источники.

Реализуй SSRF-защиту: запрет private/link-local/loopback IP, DNS rebinding checks, redirect revalidation, ограничение протоколов HTTP/HTTPS, лимиты размера/времени и content-type validation.

После seed обязательно покажи:

1. точную команду применения;
2. список записей в БД;
3. connector type;
4. enabled/live status;
5. policy status;
6. health status;
7. доказательство повторного запуска без дублей.

Минимальная рыночная проверка каталога: 200–500 качественных SKU с изображениями, размерами, вариантами, ценой/статусом и частью 3D-моделей. Демо-SKU должны быть явно отделены от live/verified данных.

---

## 8. Production hardening

Проверь текущий стек и внедряй эквивалентные инструменты без бессмысленной смены технологий:

- Alembic или штатные versioned production migrations вместо `create_all`;
- PostgreSQL для staging/production;
- Redis + Celery/RQ/Temporal или существующая надёжная очередь вместо ThreadPool;
- S3/MinIO abstraction вместо локального production storage;
- background workers и горизонтальное scaling;
- CI/CD с lint, types, unit, integration, E2E, migration test, build и artifact validation;
- centralized structured logs;
- OpenTelemetry traces/metrics;
- health, readiness, liveness;
- backups, restore test и disaster-recovery runbook;
- staging environment;
- secrets management и rotation guidance;
- AI cost budgets/quotas;
- file retention/purge policy;
- graceful shutdown и idempotent jobs.

Не вводи Redis/S3 как обязательные зависимости для простого local dev, но production profile должен использовать production-grade компоненты.

---

## 9. Security и privacy

Закрой или явно зарегистрируй с owner/date следующие gaps:

- убрать auth tokens из `localStorage`;
- secure `HttpOnly`, `Secure`, `SameSite` cookies;
- CSRF protection;
- MFA-ready архитектура;
- email verification и password reset;
- session/device management и revoke;
- API rate limiting;
- RBAC + tenant authorization на каждом endpoint и job;
- tenant isolation automated tests;
- antivirus/quarantine pipeline для uploads;
- MIME/signature validation и size limits;
- signed URLs;
- data export/delete и consent records;
- audit retention;
- security headers и CSP;
- dependency/container scan;
- penetration-test checklist.

Никогда не логируй секреты, токены, полные персональные данные или содержимое приватных файлов.

---

## 10. Autodesk, CAD/BIM и профессиональные интеграции

Не называй IFC/RVT импорт полным, если реализован только APS viewer и извлечение помещений/площадей. В UI и документации раздели:

- `View/translate supported`;
- `Metadata extraction supported`;
- `Editable semantic import pending`;
- `Export pending`.

Проверь реальную Autodesk APS интеграцию только при наличии ключей; без ключей используй contract tests/emulator и ясно пометь это. DWG-кнопка должна быть disabled с объяснением, а не создавать пустой файл.

В backlog с явными статусами оставь:

- полноценный IFC export;
- Revit automation;
- Archicad connector;
- BCF;
- OpenUSD;
- LiDAR/Apple RoomPlan;
- мобильное приложение для обмера;
- параметрическую custom-made мебель;
- производственные чертежи кухонь/шкафов;
- интеграции SketchUp/3ds Max.

---

## 11. Пилот N99 — обязательная реальная валидация

Создай pilot workspace `N99`. Если исходные материалы отсутствуют, подготовь UI/checklist загрузки и import manifest, но не заявляй Phase 7 выполненной.

Входные данные:

- архитектурный план и контрольные размеры;
- фото/видео всех помещений;
- высота потолков;
- окна/двери;
- инженерные коммуникации;
- семья и сценарии;
- стили и бюджет;
- список помещений;
- существующие сохраняемые товары;
- Variant 4 и прежние материалы проекта.

Полный проход:

`upload → recognition → confidence review → variants → manual edit → real products → estimate → client approval → album → specialist QA`.

Результат:

- обмерный план;
- демонтаж/монтаж;
- расстановка мебели;
- свет;
- розетки/выключатели;
- пол/потолок;
- развёртки;
- фотореалистичные визуализации;
- материалы;
- мебель/оборудование;
- бюджет и ссылки;
- варианты замены;
- список допущений, рисков и approvals.

---

## 12. Проверка A3-альбома и экспортов

Сгенерируй реальный sample PDF и проверь каждый из 41 листа, а не только число страниц:

- формат A3 и печатные поля;
- армянские/русские/английские тексты;
- шрифты и embedded fonts;
- штамп и нумерация вида `ԴՆ1.1 /41`;
- масштабы и scale bars;
- размерные цепочки;
- условные обозначения;
- читаемость и переносы;
- таблицы и спецификации;
- планы, развёртки и инженерные схемы;
- соответствие единой модели квартиры;
- отсутствие clipping/overlap;
- print preflight.

Добавь artifact-level tests:

- PDF page size/count/text/font checks;
- DXF parse/open test;
- GLB validation и scene inventory;
- XLSX formula/value test;
- CSV encoding/delimiter test;
- JSON schema validation.

Скорость генерации менее секунды является метрикой производительности, но не доказательством профессионального качества.

---

## 13. Порядок выполнения

Работай небольшими проверяемыми вертикальными срезами:

### Phase A — Repository audit and baseline

- inventory;
- команды запуска;
- test count reconciliation;
- claim/evidence matrix;
- baseline build/test report.

### Phase B — P0 localization

- полноценные `hy/ru/en`;
- hardcoded string elimination;
- API error codes;
- locale persistence;
- screenshots и tests.

### Phase C — Trust model and domain corrections

- три уровня достоверности;
- limitations/approvals/provenance;
- честные roadmap/status labels.

### Phase D — External catalog and PIM

- schema/migration;
- идемпотентный seed восьми источников;
- Domus-only live default;
- Profal RFQ;
- SSRF/robots/rate-limit/cache;
- verification output.

### Phase E — AI/render architecture

- providers;
- structured outputs;
- evaluation harness;
- geometry/product grounding;
- photorealistic pipeline или честно работающий integration boundary.

### Phase F — Production/security hardening

- migrations, queue, storage, observability, CI/CD, backup;
- auth/privacy/tenant isolation.

### Phase G — N99 and professional artifact validation

- end-to-end pilot;
- A3/DXF/GLB/XLSX/CSV/JSON evidence.

Не пытайся имитировать завершение всех фаз за одну сессию. Завершай максимально возможный цельный slice, оставляй репозиторий запускаемым и предоставляй точный backlog.

---

## 14. Обязательный финальный отчёт Claude Code

В конце создай/обнови:

- `AUDIT_REPORT.md`;
- `IMPLEMENTATION_REPORT.md`;
- `TEST_REPORT.md`;
- `LOCALIZATION_REPORT.md`;
- `SECURITY_REPORT.md`;
- `EXTERNAL_CATALOG_REPORT.md`;
- `N99_VALIDATION_REPORT.md`;
- `.env.example` без секретов;
- актуальные `README`, `ROADMAP`, `GAPS`.

Финальный ответ должен содержать:

1. что было подтверждено до изменений;
2. что оказалось только stub/demo/documentation claim;
3. какие файлы и миграции изменены;
4. какие команды реально выполнены;
5. полный результат lint/typecheck/unit/integration/E2E/build;
6. фактическое число тестов и объяснение расхождения 47/48;
7. какие routes проверены;
8. localization coverage по `hy/ru/en`;
9. результат seed ExternalSource;
10. ссылки/пути на PDF, DXF, GLB, XLSX, CSV, JSON и screenshots;
11. какие интеграции проверены live, какие только mocked/contract-tested;
12. что осталось, с приоритетом `P0/P1/P2`, owner type и dependency;
13. точные команды локального запуска через Docker;
14. точные команды production-like проверки;
15. rollback notes.

Для каждой крупной функции используй один из статусов:

- `VERIFIED` — доказано тестом/артефактом/E2E;
- `IMPLEMENTED_NOT_LIVE_VERIFIED` — код есть, внешние ключи/среда отсутствуют;
- `PARTIAL`;
- `STUB/DEMO`;
- `NOT IMPLEMENTED`;
- `BLOCKED_BY_EXTERNAL_DEPENDENCY`.

Запрещено писать «платформа готова», если настоящий AI, каталоги, production infrastructure, security и реальный N99 pilot не прошли validation.

---

## 15. Definition of Done текущей итерации

Минимально допустимый результат этой итерации:

- репозиторий реально запускается по документированной команде;
- тесты и build проходят либо каждый failure честно зафиксирован;
- устранён дефект частичного перевода dashboard;
- весь основной UI работает на армянском, русском и английском;
- язык сохраняется;
- создан i18n coverage report и screenshots;
- введены уровни Concept Estimate / Verified Design / Production Ready;
- применён идемпотентный ExternalSource seed без дублей;
- Domus — единственный разрешённый live source по умолчанию, Profal — RFQ;
- live global default остаётся `false`;
- roadmap и claims приведены в соответствие с доказанным состоянием;
- сформирован точный следующий backlog без маркетинговых преувеличений.

Начни с Phase A. Сначала покажи краткий план и обнаруженный стек, затем выполняй команды и изменения. Не останавливайся после анализа: реализуй Phase B и Phase D как первоочередные рабочие изменения, если репозиторий доступен и не существует объективного блокера.
