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

---

## P0-3 (2026-10-22): второй live-источник — VLV Centre

### Policy- и технический аудит (не более 6 запросов на сайт, UA `RenovaraCatalogBot`)

| Проверка | VLV (vlv.am) | Nor Tun (nortun.am) |
|---|---|---|
| robots.txt | `User-agent: *`, **Crawl-delay: 3**; запрещены `/search`, `/filter`, `/ajax-search-product`, `/price/ajax`, корзина, `/archives`; карточки `/Product/{id}` **разрешены** | запрещены только `search/index.php?q=` и `personal/` |
| Sitemap | `sitemap.xml` 8.5 МБ: 13 288 карточек `/Product/{id}`, 693 категории, 870 брендов | 4 sitemap-iblock; в iblock-24 — 3 116 URL каталога |
| Разметка карточки | schema.org `Product`: name, sku, brand, category (hy), `offers.price` AMD, availability, image | не проверялась (выбран VLV) |
| Страницы категорий | собираются скриптом из **запрещённого** `/filter` — в серверном HTML нет ссылок на товары | — |
| Условия использования | отдельной страницы в sitemap не найдено; рекомендуется уведомить магазин и запросить фид | — |

**Решение:** включить VLV как второй live-источник через **фоновый индекс**. Поиск, `/filter` и AJAX не используются. Индексатор (`app/catalog/indexer.py`) идёт по `/Product/{id}` из sitemap порциями с паузой ≥3 с, сохраняет курсор и кэширует sitemap на 24 ч. Повторный проход обновляет цены. В индекс попадают только товары, которые классифицируются как интерьерные; аксессуары отсекаются. Проект при генерации читает только индекс — запуск проекта никогда не вызывает живой обход.

- Тип коннектора `jsonld_index` (`IndexedConnector`).
- Миграция `0004_vlv_index_source` включает VLV в существующей базе; downgrade возвращает `disabled/pending`.
- Запуск: `docker compose exec api python -m app.index_source vlv --batch 60` или кнопка «Индексировать» в «Платформа → Источники». Задача `source_index` пишет `ExternalConnectorRun(kind=index)`.

### Живой прогон

| Метрика | Значение |
|---|---|
| Пройдено карточек | 80 за 4 мин 05 с (пауза 3 с соблюдена) |
| Индексировано | 13 → после исправления классификатора 9 верных, 4 аксессуара отклонены, 1 на ручную проверку |
| Не для интерьера | 67 (электроника, посуда, батарейки) |
| Без JSON-LD / заблокировано | 0 / 0 |
| Курсор | 80 / 13 288 (полный проход ≈ 11 ч в фоне; расписание — P1-7) |

**Ошибки классификатора, найденные на реальных данных и исправленные** (регрессионные тесты в `test_vlv_index.py`):

| Товар (категория магазина) | Было | Стало |
|---|---|---|
| Встроенная раковина («Ներկառուցվող լվացարաններ») | spot_light | vanity — «встроенный» больше не означает «светильник» |
| Встроенная духовка | wall_paint | oven — «ներկ» (краска) — это начало слова «ներկառուցվող» |
| Подставка под ТВ | tv | tv_unit |
| Кронштейн ТВ, AV-разветвитель, фильтр вытяжки | tv / wall_paint / wardrobe | отклонено как аксессуар (проверяется и категория магазина) |
| Набор посуды | dishwasher | ручная проверка |

**Сквозная проверка вживую** (демо-проект, источники Domus + VLV + Profal): 48 потребностей, 17 найденных товаров. В смете есть позиции с подтверждённой ценой и ссылками на оба магазина:
- Domus: унитаз `ER-00035599`, тумба `ER-00052000`;
- VLV: холодильник Samsung RB31FERNDWW `vlv.am/hy/Product/1021`, 319 900 AMD.

На фикстурах без сети то же проверяет `test_two_sources_shortlist_variant_estimate_with_links`.

**Статус:** второй источник — **VERIFIED live**, с ограничениями:
- индекс пока покрывает 0,6% каталога VLV;
- наличие берётся только из разметки магазина;
- письменного разрешения магазина нет — рекомендуется запросить официальный фид.

## 2026-10-23 — универсальный парсинг отмеченных ресурсов (временно, до официальных фидов)

Текущая логика не изменена: Domus и VLV работают по своей аудированной политике (sitemap + JSON-LD). Добавлено:

- **Многоуровневое извлечение:** JSON-LD → microdata → OpenGraph → HTML-эвристика (заголовок, цена с валютой, фото, артикул). Товары, найденные не через JSON-LD, попадают в очередь проверки и используются в дизайне только после одобрения.
- **Поиск ссылок на товары без ручной настройки:** Sitemap из robots.txt → /sitemap.xml → «товарные» дочерние sitemap → типичные шаблоны URL → листья дерева каталога → ограниченный обход сайта. Лимит sitemap — 50 МБ (по протоколу), страниц — 5 МБ.
- **Защиты:** CAPTCHA и анти-бот страницы распознаются и не обходятся; шаблонные товары конструкторов сайтов («I'm a product») отсеиваются; robots.txt, паузы, SSRF-защита — как раньше.
- **Админка → Внешние источники:** переключатель «Парсить каталог» (выключение возвращает ресурс в прежнее состояние) и «Тест-скан» — пробный запуск без записи в каталог.

Живой тест-скан (только чтение, до 8 страниц):

| Ресурс | Ссылок на товары | Метод | Итог |
|---|---|---|---|
| Vega | 16 587 (sitemap-products-*.xml) | JSON-LD | работает (например, Bosch GWS 12-125 S — 58 300 ֏) |
| Nor Tun | 3 069 (листья каталога Bitrix) | microdata | работает (например, дверная ручка F515 — 1 560 ֏) |
| Ideal System | 15 | JSON-LD | реальных позиций мало; в магазине Wix лежат шаблонные товары — отсеиваются |
| Effect Group | 307 | — | на страницах нет цен (производитель) → нужен фид / RFQ |
| Lideria | 0 | — | сайт не отвечает |
