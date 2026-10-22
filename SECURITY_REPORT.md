# SECURITY_REPORT — 2026-10-22

Секреты нигде не печатались. Значения из `.env` в отчётах, логах и коммитах не приводятся. `.env.example` не содержит значений ключей.

## Что есть и чем подтверждено

| Контроль | Реализация | Доказательство | Статус |
|---|---|---|---|
| RBAC + tenant isolation | `project_access()` на каждом ресурсе проекта, чужой проект → 404; права ролей в `security.ROLE_PERMISSIONS` | `test_tenant_isolation`, `test_admin_sources_and_permissions` | PARTIAL: нет перебора всех эндпоинтов и jobs |
| Подписанные URL файлов | HMAC + срок жизни, защита от path traversal | тест подмены подписи → 403 | VERIFIED |
| Проверка загрузок | расширение + сигнатура (magic bytes), лимит 500 МБ, sha256-дедупликация, хук `scan_for_malware` (EICAR) | `test_full_flow` (PDF с PNG-содержимым → 415) | PARTIAL: ClamAV не подключён |
| SSRF при внешнем каталоге | `SafeFetcher` (подробности ниже) | 30 тестов в `test_catalog_units.py` | VERIFIED |
| Аудит | `AuditEvent` на вход, изменения, approval, RFQ, sign-off, отметки N99 | API-тесты | VERIFIED |
| Sign-off специалиста | только verifier / bureau_admin / platform | `test_i18n_trust.py` | VERIFIED |
| Ключи провайдеров | только env сервера; браузер получает лишь APS-токен `viewables:read` | код | IMPLEMENTED |
| Логи AI | ошибка провайдера обрезается до 200 символов, есть trace id; промпты с данными клиента не логируются | код `ai/orchestrator.py` | IMPLEMENTED |
| Security headers | nginx: `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`; **CSP в режиме Report-Only** | `curl -I localhost:8085` | PARTIAL: CSP не enforce |

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
| S4 | Нет MFA (TOTP) для бюро и админов | средний | backend dev | 2026-12-15 | P1 |
| S5 | Email-верификация, сброс пароля, сессии и revoke — **сделано** (P0-1/P0-2); MFA — см. S4 | — | backend dev | закрыто частично | PARTIAL |
| S6 | ClamAV / карантин загрузок не подключён (есть только хук) | средний | devops | 2026-11-30 | P1 |
| S7 | CSP только Report-Only; нужна проверка APS Viewer под enforce | средний | frontend dev | 2026-11-30 | P1 |
| S8 | Нет полного автотеста tenant isolation по всем эндпоинтам и jobs | средний | QA | 2026-11-30 | P1 |
| S9 | Нет экспорта/удаления данных клиента, записей согласий, политики хранения фото (закон РА о ПД) | средний | product + legal | 2026-12-31 | P1 |
| S10 | Нет скана зависимостей и контейнеров (pip-audit, npm audit, trivy) — CI отсутствует | средний | devops | 2026-11-30 | P1 |
| S11 | Хранилище: **сделано** — драйвер S3 (presigned GET/PUT, приватный бакет, карантин `incoming/`), prod-профиль на SeaweedFS с шифрованием томов (проверено: исходных байтов на диске нет); на AWS S3 — SSE AES256 | — | devops | закрыто | ✔ VERIFIED (prod-стенд) |
| S12 | Нет политики retention для журнала аудита, нет чек-листа pentest | низкий | security owner | 2027-01-31 | P2 |
| S13 | Демо-аккаунты: при `ENV=production` вход `@forma.local` и `/auth/demo-accounts` запрещены; старт с шаблонным `SECRET_KEY`, `SEED_DEMO=true` или `COOKIE_SECURE=false` блокируется (`production_guard`) | — | devops | закрыто | ✔ VERIFIED |
| S14 | Ключи в `.env` переданы через чат и рабочую папку — **рекомендуется ротация** OpenAI, Gemini и APS после пилота | средний | владелец аккаунтов | 2026-11-01 | P1 |

## Проверить перед любым публичным деплоем

`ENV=production`, `SEED_DEMO=false`, свой `SECRET_KEY`, закрыты S1–S3 и S13, HTTPS на reverse-proxy, бэкап Postgres.
