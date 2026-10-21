# External Catalog Discovery — аудит источников и устройство

## Технический / policy-аудит (2026-10-21)

Проверено без обхода ограничений: `robots.txt`, `sitemap.xml`, одна карточка товара на источник. Поисковые эндпоинты не вызывались.

| Источник | Категории | Публичная цена | SKU / размеры / наличие | API / feed / JSON-LD / sitemap | robots / ограничения | Метод | Риск | MVP |
|---|---|---|---|---|---|---|---|---|
| **Domus** domus.am | отделка, сантехника, свет, мебель, техника | да (AMD в JSON-LD) | SKU ✓, MPN ✓, бренд ✓; наличие только в разметке; размеры — в названии | sitemap-products / categories ✓, **JSON-LD Product ✓** | `/search`, `/cart`, `/checkout`, `/profile` запрещены | sitemap → категория → карточка (JSON-LD) | средний: шаблонные поля (image=логотип, review) | **коннектор №1** |
| **Ideal System** idealsystem.am | плитка, сантехника, отопление | ? | ? | store-products-sitemap ✓; Wix, JSON-LD в HTML нет | разрешено | CSV/XLSX-фид поставщика | высокий для парсинга | после фида |
| **Nor Tun** nortun.am | стройматериалы, плитка, сантехника | ? | ? | sitemap-iblock-* ✓ (1C-Bitrix) | `search/index.php?q=`, `personal/` запрещены | sitemap + аудит карточки | средний | коннектор №2 (кандидат) |
| **Effect Group** effectgroup.am | краски, смеси, клей | ? | ? | sitemap не найден (WordPress) | `/wp-admin/` | прайс-лист производителя | высокий | ручной импорт |
| **Lideria** lideria.am | плитка, мозаика, сантехника | — | — | сайт не ответил | — | фид / ручной | высокий | ручной импорт |
| **Profal** profalgroup.com | двери, окна, перегородки, душевые | **нет** (индивидуально) | — | sitemap ✓, llms.txt ✓ | разрешено | **RFQ** (`quote_required`) | — | RFQ |
| **VLV Centre** vlv.am | техника, мебель, сантехника | ? | ? | sitemap ✓ (каталог) | Crawl-delay 3; ajax-поиск и ценовые AJAX запрещены | sitemap + аудит карточки | средний | коннектор №2 (кандидат) |
| **Vega** vega.am | техника, мебель, дом | ? | ? | sitemap пуст (OpenCart) | `*search=`, `*filter_*`, `*sort=` запрещены | фид / аудит | высокий | позже |

**Рекомендация:** первые коннекторы — Domus (JSON-LD уже подтверждён) и VLV **или** Nor Tun (после аудита карточки).
У Ideal System, Effect Group, Lideria, Vega — официально запросить фид (поля: SKU, название HY/RU, категория, размеры, цена AMD,
единица продажи, площадь упаковки, остаток, срок, URL, фото с правом использования).

## Устройство (`apps/api/app/catalog`)

* `sources.py` — реестр allowlist (в БД, вкл/выкл без деплоя, статус коннектора, policy, TTL, заметки аудита).
* `net.SafeFetcher` — allowlist хостов, SSRF (только публичные IP), проверка каждого редиректа, `robots.txt`,
  rate limit на домен, exponential backoff, circuit breaker; 401/403 → `FetchBlocked` (не обходим).
* `connectors/` — контракт `ExternalCatalogConnector` (`search_products`, `get_product`, `refresh_product`, `check_availability`,
  `get_connector_health`, `get_policy_status`); `JsonLdSitemapConnector`, `FeedConnector`, `RfqConnector`.
* `normalize.py` — цены (`2 790 ֏`, `1.240.000 драм`, `$1,299.50`), валюты (без курса — не конвертируем), единицы
  (шт/м²/упак/кг/л/пог.м), площадь упаковки, размеры, наличие, классификатор категорий HY/RU/EN, fingerprint, валидация.
* `discovery.run_discovery` — Product Need List → маршрутизация категорий по источникам → кандидаты → скоринг
  (категория, габарит, стиль, бюджет, наличие, свежесть, надёжность, полнота) → **Project Catalog Snapshot**
  (`discovered/validated/selected/rejected/stale/unavailable/quote_required`), TTL, provenance полей.
* Противоречивые данные → `disputed_fields` + ручная проверка (PIM → очередь проверки).

## Режимы работы

* `EXTERNAL_FETCH_LIVE=false` (по умолчанию): никакой сетевой нагрузки — используются кэш и фиды; недостающие позиции
  берутся из DEMO-каталога и **помечаются** в UI, смете и альбоме.
* `EXTERNAL_FETCH_LIVE=true`: live-discovery включается только для источников со статусом `ok` (сейчас Domus),
  с rate limit ≥ 3 с и уважением robots.

Тесты: `tests/test_catalog_units.py` — цены/единицы/упаковки, фикстура JSON-LD Domus, allowlist, SSRF, редирект на чужой хост,
robots, отказ доступа, rate limit, спорные поля, quote_required.
