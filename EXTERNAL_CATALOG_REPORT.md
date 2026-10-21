# EXTERNAL_CATALOG_REPORT — 2026-10-22

## Seed восьми источников (идемпотентный)

Команда:

```bash
docker compose exec api python -m app.seed_sources
```

Свойства seed:
- upsert по `canonical_domain` (на нём стоит UNIQUE-ограничение в БД, миграция `0002`);
- решения админа (enabled/live) сохраняются, заполняются только отсутствующие поля;
- тот же seed вызывается при старте API.

Вывод второго запуска (без изменений):

```
EXTERNAL_FETCH_LIVE=True  rows=8
key          canonical_domain     connector       enabled  live  policy    health       seed
domus        domus.am             jsonld_sitemap  True     True  approved  ok           unchanged
effectgroup  effectgroup.am       feed            False    False pending   disabled     unchanged
idealsystem  idealsystem.am       feed            False    False pending   disabled     unchanged
lideria      lideria.am           feed            False    False pending   disabled     unchanged
nortun       nortun.am            jsonld_sitemap  False    False pending   disabled     unchanged
profal       profalgroup.com      rfq             True     False approved  rfq_only     unchanged
vega         vega.am              jsonld_sitemap  False    False pending   disabled     unchanged
vlv          vlv.am               jsonld_sitemap  False    False pending   disabled     unchanged
```

Правила:
- **Domus** — единственный live-источник по умолчанию.
- **Profal** — только RFQ (без fetch).
- Остальные шесть источников — `disabled / pending` до получения официального фида или разрешения.

Тест: `test_source_seed_is_idempotent_and_domus_only_live` — 8 строк, повтор не создаёт дублей и сохраняет флаги админа.

## Глобальный переключатель live

- **Default в коде и `.env.example`: `EXTERNAL_FETCH_LIVE=false`.**
- В вашем `.env` стоит `true`. Даже так live-запросы идут только к источнику с `live_enabled=true`, то есть только к Domus: `build_connector` требует оба флага.

## Живой прогон Domus (compose, реальная сеть)

| Шаг | Результат |
|---|---|
| Бюджет | 40 HTTP-запросов на прогон (`EXTERNAL_DISCOVERY_MAX_REQUESTS`); robots.txt соблюдён; 3 с между запросами |
| Найдено | 20 карточек товаров (sitemap → JSON-LD) |
| Первая классификация | ошибки: бокалы → «кровать», панель для ванны → «ванна», винный шкаф → «холодильник» |
| Исправление | стоп-слова `CATEGORY_EXCLUDE`, расширенный `ACCESSORY_WORDS`, `is_accessory()`, убран fallback «категория по странице» |
| Переклассификация сохранённого | `python -m app.reclassify_external`: 11 переклассифицировано, 2 отклонено |
| В смету попали реальные SKU | Sanita Luxe — унитаз `ER-00035599`; Comforty Geneva — тумба `ER-00052000`; Teka NFL 320 — холодильник `ER-00073366` |
| Остальные потребности | закрыты DEMO-каталогом с явной пометкой `DEMO` в смете, альбоме и Client Viewer |

Ограничения:
- Наличие на складе берётся только из разметки магазина. В интерфейсе написано «перед заказом требуется перепроверка».
- Цена хранится с `fetched_at`, TTL (24 ч), confidence и canonical URL. После истечения TTL цена помечается как устаревшая.
- 20 найденных товаров на прогон — мало для полноценного grounding. Нужен официальный фид (P0 бизнес-задача).

## Защиты (тесты в `test_catalog_units.py`)

| Защита | Проверяется |
|---|---|
| Allowlist доменов из БД | ✔ |
| Блок private / loopback / link-local IP | ✔ |
| Проверка IP пира после соединения (DNS-rebinding) | ✔ |
| Проверка каждого редиректа | ✔ |
| robots.txt (кэш) | ✔ |
| Rate limit на хост | ✔ |
| Circuit breaker | ✔ |
| Content-type allowlist | ✔ |
| Лимит размера ответа | ✔ |
| Бюджет запросов на прогон | ✔ |
| Не обходим 401 / 403 / CAPTCHA / логин | ✔ |
| User-Agent с контактом: `FormaAI-CatalogBot/0.1 (+https://cubeappmaker.agency/bot)` | ✔ |

## Статусы

| Функция | Статус |
|---|---|
| Seed / registry / админ-панель источников | VERIFIED |
| Domus live discovery | VERIFIED live (ограниченный объём) |
| Profal RFQ | VERIFIED (API, без реальной отправки письма) |
| Фиды Ideal System / Nor Tun / VLV / Effect Group / Lideria / Vega | BLOCKED_BY_EXTERNAL_DEPENDENCY (нет фидов и разрешений) |
| Импорт PIM CSV/XLSX | IMPLEMENTED (тесты защиты импорта) |
