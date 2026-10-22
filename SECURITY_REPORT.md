# SECURITY_REPORT — 2026-10-22 (обновлено после итерации P0–P2)

Секреты нигде не печатались. Значения из `.env` в отчётах, логах и коммитах не приводятся. `.env.example` не содержит значений ключей.

## Что есть и чем подтверждено

| Контроль | Реализация | Доказательство | Статус |
|---|---|---|---|
| RBAC + tenant isolation | `project_access()` на каждом ресурсе проекта, проверка принадлежности дочерних объектов проекту, чужой проект → 404 | `tests/test_tenant_isolation.py`: перебор **всех** параметризованных маршрутов OpenAPI (тела запросов строятся по схеме) от имени другого бюро — под чужим и под своим проектом с чужими id | VERIFIED |
| Подписанные URL файлов | HMAC + срок жизни, защита от path traversal | тест подмены подписи → 403 | VERIFIED |
| Проверка загрузок | расширение + сигнатура, лимит 500 МБ, sha256-дедупликация, ClamAV (S6); ассеты поставщиков проверяются по содержимому (GLB-заголовок и длина, glTF 2.0, декодирование изображений, сигнатуры IFC/DWG/DXF/RVT/PDF) | `test_supplier_partner.py` (переименованный PNG → `asset.not_glb`, EICAR → 422) | VERIFIED |
| SSRF при внешнем каталоге | `SafeFetcher` (подробности ниже) | 30 тестов в `test_catalog_units.py` | VERIFIED |
| Аудит | `AuditEvent` на вход, изменения, approval, RFQ, sign-off, отметки N99 | API-тесты | VERIFIED |
| Sign-off специалиста | только verifier / bureau_admin / platform | `test_i18n_trust.py` | VERIFIED |
| Ключи провайдеров | только env сервера; браузер получает лишь APS-токен `viewables:read` | код | IMPLEMENTED |
| Логи AI | ошибка провайдера обрезается до 200 символов, есть trace id; промпты с данными клиента не логируются | код `ai/orchestrator.py` | IMPLEMENTED |
| Security headers | nginx: `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, **CSP enforce** (S7); шрифты self-hosted — Google Fonts убраны из CSP, IP посетителей не уходят третьей стороне | `e2e/csp_check.py` — 0 нарушений | VERIFIED |
| Деньги | журнал проводок только на добавление (ORM-guard + триггер Postgres, CHECK одной стороны), идемпотентные ключи, выплаты не больше задолженности, оплата фиксируется только по webhook с проверкой HMAC-подписи, окна 5 мин, однократности события и суммы | `tests/test_commerce.py`; триггер проверен на Postgres (`UPDATE` → `ledger_entries are append-only`) | VERIFIED |
| Поставщики | самозарегистрированный поставщик скрыт из каталога и дизайна до проверки платформой; модерация внешних записей — только платформенные роли | `test_supplier_partner.py`, `test_tenant_isolation.py` | VERIFIED |
| PWA | service worker не кэширует `/api/`, файлы и подписанные ссылки | `public/sw.js`, `e2e/bim_pwa_e2e.py` | VERIFIED |

`SafeFetcher` в деталях:
- allowlist доменов из БД;
- только публичные IP, проверка IP пира после соединения (защита от DNS-rebinding);
- проверка каждого редиректа (до 3);
- robots.txt, rate limit 3 с на хост, circuit breaker;
- allowlist content-type, лимит 5 МБ, бюджет 40 запросов на прогон;
- ответы 401/403/CAPTCHA не обходятся.

## Зарегистрированные разрывы

Owner — роль ответственного; срок — целевая дата.

| # | Разрыв | Риск | Owner | Срок | Приоритет |
|---|---|---|---|---|---|
| S1 | ~~Токен авторизации в `localStorage`~~ — **закрыто 2026-10-22**: HttpOnly-cookie `forma_session`, токена в JS нет (E2E `auth_e2e.py`: «no auth token in localStorage») | — | backend + frontend dev | закрыто | ✔ VERIFIED |
| S2 | ~~Нет HttpOnly/Secure/SameSite cookie и CSRF~~ — **закрыто**: `HttpOnly; Secure; SameSite=Lax` + double-submit CSRF (`X-CSRF-Token`), SSE по cookie без токена в URL (тесты `test_auth.py`) | — | backend dev | закрыто | ✔ VERIFIED |
| S3 | ~~Нет rate limiting~~ — **закрыто**: лимиты на вход (по IP и по неудачным попыткам на аккаунт), регистрацию, сброс пароля, генерацию, распознавание, AI-команды, альбом; 429 + `Retry-After`; Redis-бэкенд при `REDIS_URL` | — | backend/devops | закрыто | ✔ VERIFIED |
| S4 | MFA — **сделано**: TOTP (QR, ключ, окно ±30 с), 10 одноразовых резервных кодов (хранятся SHA-256), секрет зашифрован (Fernet), двухшаговый вход, лимит попыток; обязательна для `bureau_admin` и `platform_*` в production (`MFA_ENFORCE`), иначе API отвечает 403 `auth.mfa_enrollment_required` | — | backend dev | закрыто | ✔ VERIFIED |
| S5 | Email-верификация, сброс пароля, экран «Сессии и устройства» с отзывом — **сделано** | — | backend dev | закрыто | ✔ VERIFIED |
| S6 | ClamAV — **сделано**: clamd INSTREAM для каждой загрузки (multipart и presigned), заражённые файлы — в `quarantine/` (не отдаются, удаляются через 30 дней) + аудит + список в админке; при недоступном clamd загрузка отклоняется в production (503). Проверено живым clamd: EICAR → `Eicar-Test-Signature FOUND` → 422 | — | devops | закрыто | ✔ VERIFIED |
| S7 | CSP — **enforce**: проверено на 10 страницах, включая APS Viewer (модель отрисована) и WebGL-лендинг, 0 нарушений (`e2e/csp_check.py`); шрифты Autodesk разрешены; телеметрия APS Viewer отключена (`optOutTrackingByDefault`), Mixpanel блокируется CSP | — | frontend dev | закрыто | ✔ VERIFIED |
| S8 | ~~Нет полного автотеста tenant isolation~~ — **закрыто**: перебор всех маршрутов OpenAPI; найдены и исправлены 3 дыры (версия варианта и сравнение версий по чужому `vid`, SSE-поток чужой задачи, модерация внешних записей поставщиком) | — | QA | закрыто | ✔ VERIFIED |
| S9 | Персональные данные — **сделано**: экспорт ZIP (профиль, согласия, сессии, действия, свои проекты с файлами), удаление аккаунта с периодом ожидания 14 дней и отменой, затем обезличивание и удаление проектов организации без других участников; согласия с историей; фото квартир удаляются через 365 дней без активности проекта; журнал аудита — 730 дней. **Не сделано:** юридический текст политики и согласий (нужен юрист РА) | средний | product + legal | тексты 2026-12-31 | PARTIAL |
| S10 | Скан зависимостей и образов — **сделано**: CI (pip-audit, npm audit prod/high, trivy critical). Найдено и исправлено: pillow 11.1→13.0 (39 CVE), python-multipart →0.0.31 (6), starlette 0.41→1.5.1 через FastAPI 0.158 (7), OpenSSL в образе web (nginx 1.27→1.28 + apk upgrade), react-router-dom 6.30.6. 2026-10-22 (вечер): `opentelemetry-api` 1.44.0 (GHSA-xcq7-p3pf-p88h) → 1.45.1 вместе с SDK/экспортёром и инструментацией 0.66b1. Новые зависимости итерации: `ifcopenshell` 0.8.5 (+ shapely, lark, isodate), `numpy` закреплён. **Осталось:** vite (уязвимость только dev-сервера, в production-сборку не попадает) и умеренные уязвимости react-router 6 — нужны мажорные обновления vite 8 и react-router 7 (P2) | низкий | frontend dev | 2026-12-31 | PARTIAL |
| S11 | Хранилище: **сделано** — драйвер S3 (presigned GET/PUT, приватный бакет, карантин `incoming/`), prod-профиль на SeaweedFS с шифрованием томов (проверено: исходных байтов на диске нет); на AWS S3 — SSE AES256 | — | devops | закрыто | ✔ VERIFIED (prod-стенд) |
| S12 | Retention журнала аудита — **сделано** (730 дней, S9); нет чек-листа pentest и внешнего пентеста | низкий | security owner | 2027-01-31 | P2 |
| S15 | Платёжный провайдер: адаптер `stripe_compat` проверен на тестовом транспорте; армянские эквайеры (Idram, ArCa, Ameriabank) требуют договора и документации — до этого онлайн-оплата выключена и UI честно пишет «Integration pending» | средний | бизнес + backend | по договору | BLOCKED |
| S13 | Демо-аккаунты: при `ENV=production` вход `@forma.local` и `/auth/demo-accounts` запрещены; старт с шаблонным `SECRET_KEY`, `SEED_DEMO=true` или `COOKIE_SECURE=false` блокируется (`production_guard`) | — | devops | закрыто | ✔ VERIFIED |
| S14 | Ключи в `.env` переданы через чат и рабочую папку — **рекомендуется ротация** OpenAI, Gemini и APS после пилота | средний | владелец аккаунтов | 2026-11-01 | P1 |

## Проверить перед любым публичным деплоем

`ENV=production`, `SEED_DEMO=false`, свой `SECRET_KEY`, закрыты S1–S3 и S13, HTTPS на reverse-proxy, бэкап Postgres.
