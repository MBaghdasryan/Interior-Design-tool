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
| S1 | Токен авторизации в `localStorage` (XSS → кража сессии) | высокий | backend + frontend dev | 2026-11-15 | P0 до прод |
| S2 | Нет `HttpOnly; Secure; SameSite=Lax` cookie и CSRF-токена (зависит от S1) | высокий | backend dev | 2026-11-15 | P0 до прод |
| S3 | Нет rate limiting API и блокировки перебора паролей | высокий | backend/devops | 2026-11-15 | P0 до прод |
| S4 | Нет MFA (TOTP) для бюро и админов | средний | backend dev | 2026-12-15 | P1 |
| S5 | Нет email-верификации, сброса пароля, управления сессиями/устройствами и revoke | средний | backend dev | 2026-12-15 | P1 |
| S6 | ClamAV / карантин загрузок не подключён (есть только хук) | средний | devops | 2026-11-30 | P1 |
| S7 | CSP только Report-Only; нужна проверка APS Viewer под enforce | средний | frontend dev | 2026-11-30 | P1 |
| S8 | Нет полного автотеста tenant isolation по всем эндпоинтам и jobs | средний | QA | 2026-11-30 | P1 |
| S9 | Нет экспорта/удаления данных клиента, записей согласий, политики хранения фото (закон РА о ПД) | средний | product + legal | 2026-12-31 | P1 |
| S10 | Нет скана зависимостей и контейнеров (pip-audit, npm audit, trivy) — CI отсутствует | средний | devops | 2026-11-30 | P1 |
| S11 | Локальное хранилище файлов без шифрования на диске; S3 с SSE не подключён | средний | devops | 2026-12-15 | P1 |
| S12 | Нет политики retention для журнала аудита, нет чек-листа pentest | низкий | security owner | 2027-01-31 | P2 |
| S13 | Демо-аккаунты с паролем `demo1234` (выключаются `ENV=production`, `SEED_DEMO=false`) | высокий, если забыть | devops | при деплое | P0 до прод |
| S14 | Ключи в `.env` переданы через чат и рабочую папку — **рекомендуется ротация** OpenAI, Gemini и APS после пилота | средний | владелец аккаунтов | 2026-11-01 | P1 |

## Проверить перед любым публичным деплоем

`ENV=production`, `SEED_DEMO=false`, свой `SECRET_KEY`, закрыты S1–S3 и S13, HTTPS на reverse-proxy, бэкап Postgres.
