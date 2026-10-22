# RUNBOOK — эксплуатация Renovara

## 1. Окружения

| Профиль | Команда | Что внутри |
|---|---|---|
| dev | `docker compose up -d --build` | db, redis, api, worker, web (`:8085`); демо-данные; локальное хранилище; письма — `.eml` в томе `storage:/data/mail` |
| production | `docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod up -d --build` | см. ниже |

Состав production-профиля:
- **Caddy:** TLS (Let's Encrypt; для `*.localhost` — внутренний CA). Наружу открыты только порты 80/443.
- **SeaweedFS:** S3, шифрование данных на диске (`-filer.encryptVolumeData`).
- **API и worker:** `ENV=production`, без демо-данных, JSON-логи.

Подготовка production:
1. Скопируйте `.env.prod.example` → `.env.prod` и заполните секреты. Генерация: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
2. Направьте DNS `DOMAIN` и `FILES_DOMAIN` на сервер.
3. API **не стартует**, если:
   - `SECRET_KEY` — шаблонный или короче 32 символов;
   - `SEED_DEMO=true`;
   - `COOKIE_SECURE=false`.

   Проверка `production_guard` выполняется при старте.

Проверено 2026-10-22 на временном стенде `renovara-prodtest` (DOMAIN=localhost, после проверки удалён):
- `/api/ready` → `db/redis/storage ok`;
- демо-вход → 403 `auth.demo_disabled`;
- cookie с `Secure; HttpOnly; SameSite=Lax`;
- presigned PUT в объектное хранилище → проверка файла → скачивание по 302, файл совпал побайтно;
- исходных байтов файла нет ни в одном из 14 файлов томов (шифрование на диске);
- старт с шаблонным `SECRET_KEY` → `RuntimeError`, код выхода 1.

## 2. Проверки состояния

| Endpoint | Назначение |
|---|---|
| `GET /api/live` | liveness: процесс отвечает; зависимости не проверяются |
| `GET /api/ready` | readiness: БД, Redis (если задан), хранилище; при сбое — 503 и `checks` |
| `GET /api/health` | простой ping, его использует healthcheck compose |

## 3. Логи, трассировка, ошибки

- **Логи:** `LOG_FORMAT=json` — одна JSON-строка на событие. Поля: `ts`, `level`, `logger`, `msg`, `request_id`, `trace_id`.
- **Request id:** приходит в заголовке `X-Request-ID` (если корректный) или генерируется, и возвращается в ответе.
- **OpenTelemetry:** задайте `OTEL_EXPORTER_OTLP_ENDPOINT` (например, `http://otel-collector:4318`). Трассируются FastAPI, SQLAlchemy и исходящие httpx-запросы (AI, APS, сайты каталогов).
- **Sentry:** `SENTRY_DSN`. Используется `send_default_pii=False`, 10% трассировок.
- **Что не логируется:** секреты, токены, тела запросов, текст писем.

## 4. Очередь задач

- Worker: `docker compose logs -f worker`.
- Упавшие задачи: в БД `generation_jobs.status='failed'`. После 3 попыток — `counters.dead_letter=true`, задача хранится в RQ FailedJobRegistry 7 дней.
- Перезапуск упавшей задачи из интерфейса: «Повторить» (`POST /projects/{pid}/jobs/{jid}/retry`).
- Задачи `queued`/`running` без живого worker'а перезапускаются автоматически: при старте worker'а и раз в минуту.
- Остановка: `docker compose stop worker` (warm shutdown — текущая задача дорабатывает, `stop_grace_period: 2m`).

## 5. Резервное копирование и восстановление

```bash
scripts/backup.sh
```

Скрипт создаёт `backups/<UTC>/db.dump` (pg_dump -Fc), `objects.tar.gz` (все объекты хранилища с манифестом sha256) и `SHA256SUMS`.

Для production: `COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod" scripts/backup.sh`.

**Расписание (рекомендуется):**
- cron на хосте каждые 6 ч: `scripts/backup.sh` и копирование папки off-site (другой регион или бакет);
- хранение: 7 ежедневных, 4 еженедельных, 12 ежемесячных копий.

**Учения по восстановлению** (ежемесячно; рабочие данные не затрагиваются):

```bash
scripts/restore.sh backups/<ts>
```

Скрипт проверяет контрольные суммы, восстанавливает БД в отдельную базу `restore_check`, сверяет число строк в ключевых таблицах и целостность архива объектов, затем удаляет `restore_check`.

Выполнено 2026-10-22:
- dev: 17 объектов, `corrupt=0`; users / projects / versions / documents / external records / audit — совпадают;
- prod-профиль (S3): 1 объект, `corrupt=0`, таблицы совпадают.

**Аварийное восстановление** (заменяет живую БД):

```bash
scripts/restore.sh backups/<ts> --apply
```

Порядок: останавливаются api и worker → база пересоздаётся → `pg_restore` → api и worker запускаются → объекты дозагружаются.

## 6. Политика хранения файлов (retention)

Задача `retention` выполняется в worker'е раз в сутки (`app/retention.py`).

| Данные | Срок | Параметр |
|---|---|---|
| `incoming/` — начатые, но не завершённые presigned-загрузки | 1 день | `RETENTION_INCOMING_DAYS` |
| Копии исходящих писем (console backend) | 30 дней | `RETENTION_MAIL_DAYS` |
| Объекты под `projects/`, на которые не ссылается ни один файл или документ | 7 дней | `RETENTION_ORPHAN_DAYS` |
| Исходники проекта, документы, утверждённые снимки | **не удаляются автоматически** | удаление — явное действие пользователя с записью в аудит (P1-4) |

Каждый запуск пишет `AuditEvent(action="retention.run")` со счётчиками.

## 7. Безопасность учётных записей и загрузок

**MFA (TOTP)**
- Обязательна для `bureau_admin`, `platform_admin`, `platform_ops` в production.
- Состав ролей задаёт `MFA_REQUIRED_ROLES`, принудительное включение вне production — `MFA_ENFORCE=true`.
- Пользователь без MFA видит только раздел «Аккаунт → Двухфакторная аутентификация».
- Если потерян и телефон, и резервные коды: администратор платформы сбрасывает в БД поля `mfa_secret_enc`, `mfa_enabled_at` и `mfa_backup_codes` у пользователя и делает запись в журнал аудита.

**ClamAV**
- Production: сервис `clamav` всегда включён, `CLAMAV_REQUIRED=true` — пока сканер недоступен, загрузки отклоняются с кодом 503.
- Dev: `CLAMAV_HOST=clamav docker compose --profile av up -d`.
- Карантин: «Платформа → Карантин». Объекты лежат в `quarantine/` и удаляются через 30 дней.

**Персональные данные**
- Экспорт: «Аккаунт → Мои данные».
- Удаление: 14 дней ожидания (`PRIVACY_DELETION_GRACE_DAYS`), затем ежедневная задача `retention` обезличивает аккаунт.

## 8. Ротация секретов

| Секрет | Как ротировать | Последствие |
|---|---|---|
| `SECRET_KEY` | заменить, перезапустить api и worker | все сессии и подписанные ссылки на файлы станут недействительны; **секреты MFA зашифрованы ключом, производным от `SECRET_KEY`** — пользователям с MFA нужно заново подключить приложение (или перешифруйте секреты скриптом до смены ключа) |
| ключи AI и APS | заменить в `.env.prod`, перезапустить | — |
| `OBJECTSTORE_SECRET_KEY` | заменить, перезапустить objectstore, api и worker | — |
| `POSTGRES_PASSWORD` | `ALTER USER`, затем заменить в `.env.prod` | — |

Ключи OpenAI, Gemini и APS из рабочей папки разработки **рекомендуется сменить перед публичным запуском** (SECURITY_REPORT S14).
