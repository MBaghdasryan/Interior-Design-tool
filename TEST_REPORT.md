# TEST_REPORT — 2026-10-22 (итерация P0–P2)

Все команды запускались через Docker (в WSL нет node и pip). Отчёт предыдущей итерации — в истории git.

## Сводка

| Проверка | Команда | Результат |
|---|---|---|
| Lint backend | `docker run --rm -v $PWD/apps:/apps -w /apps/api forma-api-dev ruff check app tests evals` | без замечаний |
| Unit + integration backend | `… forma-api-dev python -m pytest -q -p no:cacheprovider` | **155 passed**, 0 failed, 0 skipped (≈2 мин) |
| Миграции | `alembic downgrade <prev> && alembic upgrade head` на Postgres для каждой новой ревизии 0003–0012; в CI — `upgrade → downgrade 0001 → upgrade` | все зелёные; триггер ledger на Postgres блокирует `UPDATE` |
| OpenAPI | `python -m app.openapi_export ../web/openapi.json --check` | актуален (168 путей) |
| i18n | `node scripts/i18n-check.mjs` | `keys=1501 incomplete=0 missing=0 orphans=0 hardcoded=0` |
| Контракт API | `npm run api:check` | 175 вызовов фронтенда, отсутствующих в API — 0 |
| Типы | `npm run api:types && npx tsc --noEmit -p .` | без ошибок |
| Сборка | `npx vite build` | собрано |
| pip-audit | `pip-audit -r requirements.txt` | найдено `opentelemetry-api 1.44.0` (GHSA-xcq7-p3pf-p88h) → обновлено до 1.45.1 / 0.66b1; повтор: уязвимостей нет |
| CI GitHub Actions | push в `main` | зелёный на коммитах P1-8…P2-4 (P1-7 один раз упал на `apt-get update` в раннере, не на коде) |

## E2E (Playwright, против локального compose)

| Сценарий | Файл | Результат |
|---|---|---|
| Визуальная регрессия публичных страниц hy/ru/en (12 эталонов) + axe-core WCAG A/AA на 17 маршрутах | `visual_a11y_e2e.py` | ALL PASS (0 % расхождений, 0 серьёзных/критичных нарушений) |
| Регистрация → письмо → подтверждение → онбординг → сброс пароля | `auth_e2e.py` | 0 failures |
| Локализация: нет русских слов в hy/en, `<html lang>`, сохранение | `i18n_e2e.py` | 0 failures |
| 22 маршрута × 5 ролей без JS-ошибок и 5xx | `routes_smoke.py` | 22/22 |
| Уведомления: событие → колокольчик на 3 языках → переход → настройки | `notifications_e2e.py` | ALL PASS |
| История коннектора, фид поставщика (только https) | `catalog_ops_e2e.py` | ALL PASS |
| Финансы: сверка ledger, «Integration pending», тарифы; кабинет поставщика; закупки | `commerce_e2e.py` | ALL PASS |
| Онбординг поставщика, загрузка GLB с 3D-превью, отказ переименованного файла | `supplier_onboarding_e2e.py` | ALL PASS |
| Умный поиск по-армянски, честная метка режима, аналоги | `search_e2e.py` | ALL PASS |
| Мебель на заказ: диапазоны, «по запросу», версии, PDF, запрет заказа без Production Ready | `custom_furniture_e2e.py` | ALL PASS |
| IFC-экспорт, RoomPlan, манифест PWA и service worker | `bim_pwa_e2e.py` | ALL PASS |
| CSP: 0 нарушений на страницах, включая APS Viewer | `csp_check.py` | 0 нарушений |

## Новые тестовые файлы backend

| Файл | Что покрывает |
|---|---|
| `test_auth.py` | регистрация, письма hy/ru/en, одноразовые токены, cookie + CSRF, сессии, rate limits, prod-guard |
| `test_queue.py`, `test_infra.py` | RQ: ретраи, dead letter, восстановление; S3 (moto), presign, retention, OTel |
| `test_privacy_mfa.py` | TOTP, резервные коды, экспорт ZIP, удаление с ожиданием, согласия |
| `test_ai_budget.py` | бюджеты организаций, отказ интерактивным вызовам, детерминированный fallback; склейка многочастного JSON Gemini |
| `test_render.py` | манифест SKU, grounding (ΔE), регенерация зоны без изменения пикселей вне маски |
| `test_notifications.py` | события → уведомления, прочитано, настройки, дайджест раз в сутки |
| `test_catalog_maintenance.py` | алерты (падение результатов, парсер, circuit), батчи индекса, TTL цен, фиды с защитой |
| `test_tenant_isolation.py` | все параметризованные маршруты OpenAPI от имени чужого бюро |
| `test_pagination.py` | курсорная пагинация без дублей и пропусков при вставках |
| `test_commerce.py` | корзина → перепроверка → заказ → подтверждение → оплата по подписанному webhook → проводки → возврат → выплата → сверка; тарифы и лимит |
| `test_supplier_partner.py` | онбординг до верификации, скрытие непроверенных, ассеты по содержимому, справочники |
| `test_search.py` | кросс-языковые векторы, индекс, аналоги, поиск по фото, fallback Gemini |
| `test_custom_furniture.py` | ограничения, раскрой, цена только по ставкам, версии, DXF/PDF, Production Ready |
| `test_bim.py` | IFC круговой тест (стены/помещения/проёмы до 1 мм), импорт через проект, RoomPlan |

## Оценка AI
См. `EVAL_REPORT.md` — с примечаниями о недостоверности метрик планов в этом прогоне и о блокировке повтора (кредиты).
