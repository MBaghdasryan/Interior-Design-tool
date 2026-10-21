# Безопасность

| Требование | Реализация | Статус |
|---|---|---|
| Аутентификация | PBKDF2-SHA256 (240k), подписанные HMAC токены с TTL 12 ч | ✓ MVP |
| RBAC / tenant isolation | `security.ROLE_PERMISSIONS`, `project_access()` на каждом ресурсе проекта, чужие проекты → 404 | ✓, тест `test_tenant_isolation` |
| Аудит | `AuditEvent` на создание/изменение/утверждение/RFQ/импорт/вход | ✓ |
| Подписанный доступ к медиа | `/api/v1/files/{key}?exp&sig` (HMAC, срок жизни), запрет path traversal | ✓, тест на подмену подписи |
| Проверка загрузок | расширение + сигнатура содержимого, лимит 500 МБ, хук антивируса (`scan_for_malware`, EICAR), дедупликация sha256 | ✓ (ClamAV — подключить) |
| SSRF / внешние сайты | allowlist хостов, только публичные IP, проверка каждого редиректа, robots.txt, rate limit, circuit breaker, без обхода 401/403/CAPTCHA | ✓, тесты |
| Ключи API | только в env на сервере; браузер получает лишь APS `viewables:read` | ✓ |
| Секреты в репозитории | `.env` в `.gitignore`, `.env.example` без значений | ✓ |
| Неизменяемость утверждённого | замороженная версия + `EstimateSnapshot` | ✓ |
| DEMO-изоляция | DEMO-поставщикам RFQ/заказы не отправляются (409) | ✓ |

## До production

* Перенести токен из `localStorage` в httpOnly Secure SameSite cookie + CSRF-токен; MFA (TOTP) для бюро и админов.
* Rate limiting API (например, slowapi/nginx `limit_req`), блокировка перебора паролей.
* ClamAV (clamd INSTREAM) в `scan_for_malware`; S3 с SSE и presigned URL.
* Alembic-миграции, резервное копирование Postgres, OpenTelemetry/Sentry.
* Политика персональных данных РА: согласия, экспорт/удаление данных клиента, срок хранения фото квартир.
* Отключить демо-аккаунты: `ENV=production` скрывает `/auth/demo-accounts`; `SEED_DEMO=false`.

Актуальный реестр разрывов с owner и сроками — в [SECURITY_REPORT.md](../SECURITY_REPORT.md). Security headers добавлены в `apps/web/nginx.conf` (CSP пока в режиме Report-Only).
