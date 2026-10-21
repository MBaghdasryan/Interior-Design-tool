"""Initial allowlist of external sources (addon prompt §3) with the results of the
technical/policy audit performed on 2026-10-21 (robots.txt + one product page per
source, no search endpoints touched). The registry is seeded into the DB; Super
Admin toggles sources at runtime without a deployment."""
from __future__ import annotations

AUDIT_DATE = "2026-10-21"

# Seed policy (master audit prompt §7): only Domus may live-fetch by default, Profal is
# an RFQ connector, the rest stay pending/disabled until an official feed or policy audit.
SEED_POLICY = {
    "domus": {"enabled": True, "live_enabled": True, "connector_type": "jsonld_sitemap", "policy_status": "approved"},
    "profal": {"enabled": True, "live_enabled": False, "connector_type": "rfq", "policy_status": "approved"},
}
DEFAULT_POLICY = {"enabled": False, "live_enabled": False, "policy_status": "pending"}


def canonical_domain(url: str) -> str:
    from urllib.parse import urlparse

    host = (urlparse(url if "://" in url else f"https://{url}").hostname or "").lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host

SOURCES: list[dict] = [
    {
        "key": "domus", "name": "Domus", "domain": "https://domus.am",
        "allowed_hosts": ["domus.am", "www.domus.am"],
        "categories": ["finishing", "plumbing", "furniture", "lighting", "appliances"],
        "languages": ["hy", "ru", "en"], "method": "jsonld_sitemap", "connector_status": "ok",
        "rate_limit_s": 3.0,
        "policy": {
            "robots": "allowed", "search_disallowed": True, "disallow": ["/search", "/cart", "/checkout", "/profile"],
            "sitemaps": ["https://domus.am/sitemap-products.xml", "https://domus.am/sitemap-categories.xml"],
            "jsonld_product": True,
            "terms_reviewed": False,
            "audit": AUDIT_DATE,
        },
        "notes": "Карточки содержат schema.org Product: sku, mpn, brand, offers.price (AMD), availability, deliveryTime. "
                 "Обнаружены шаблонные поля: image = логотип сайта, review/aggregateRating — шаблон. Изображения и отзывы НЕ использовать; "
                 "availability принимать с пониженной уверенностью до подтверждения. Поиск /search запрещён robots.txt — discovery только через sitemap.",
        "priority": "high",
    },
    {
        "key": "idealsystem", "name": "Ideal System", "domain": "https://www.idealsystem.am",
        "allowed_hosts": ["idealsystem.am", "www.idealsystem.am"],
        "categories": ["finishing", "plumbing"], "languages": ["hy", "ru"], "method": "feed", "connector_status": "needs_feed",
        "rate_limit_s": 5.0,
        "policy": {"robots": "allowed", "search_disallowed": False, "sitemaps": ["https://www.idealsystem.am/store-products-sitemap.xml"],
                   "jsonld_product": False, "platform": "Wix", "terms_reviewed": False, "audit": AUDIT_DATE},
        "notes": "Сайт на Wix: в серверном HTML нет JSON-LD Product. Рекомендуется официальный CSV/XLSX-фид от поставщика.",
        "priority": "high",
    },
    {
        "key": "nortun", "name": "Nor Tun", "domain": "https://nortun.am",
        "allowed_hosts": ["nortun.am", "www.nortun.am"],
        "categories": ["finishing", "plumbing"], "languages": ["hy", "ru"], "method": "jsonld_sitemap", "connector_status": "needs_audit",
        "rate_limit_s": 3.0,
        "policy": {"robots": "allowed", "search_disallowed": True, "disallow": ["search/index.php?q=", "personal/"],
                   "sitemaps": ["https://nortun.am/sitemap.xml"], "jsonld_product": None, "platform": "1C-Bitrix", "terms_reviewed": False, "audit": AUDIT_DATE},
        "notes": "1C-Bitrix, несколько sitemap-iblock. Структура карточек не проверена — нужен аудит перед включением.",
        "priority": "high",
    },
    {
        "key": "effectgroup", "name": "Shen / Effect Group", "domain": "https://effectgroup.am",
        "allowed_hosts": ["effectgroup.am", "www.effectgroup.am"],
        "categories": ["finishing"], "languages": ["hy", "ru"], "method": "manual", "connector_status": "needs_feed",
        "rate_limit_s": 5.0,
        "policy": {"robots": "allowed", "search_disallowed": False, "sitemaps": [], "jsonld_product": None, "platform": "WordPress", "terms_reviewed": False, "audit": AUDIT_DATE},
        "notes": "WordPress, sitemap.xml не найден. Краски/смеси — запросить прайс-лист у производителя.",
        "priority": "high",
    },
    {
        "key": "lideria", "name": "Lideria", "domain": "https://lideria.am",
        "allowed_hosts": ["lideria.am", "www.lideria.am"],
        "categories": ["finishing", "plumbing"], "languages": ["hy", "ru"], "method": "manual", "connector_status": "unreachable",
        "rate_limit_s": 5.0,
        "policy": {"robots": "unknown", "jsonld_product": None, "terms_reviewed": False, "audit": AUDIT_DATE},
        "notes": "Сайт не ответил при аудите (timeout). Использовать ручной импорт/фид.",
        "priority": "high",
    },
    {
        "key": "profal", "name": "Profal", "domain": "https://profalgroup.com",
        "allowed_hosts": ["profalgroup.com", "www.profalgroup.com"],
        "categories": ["doors"], "languages": ["hy", "ru", "en"], "method": "rfq", "connector_status": "rfq_only",
        "rate_limit_s": 5.0,
        "policy": {"robots": "allowed", "llms_txt": "http://profalgroup.com/llms.txt", "sitemaps": ["http://profalgroup.com/sitemap.xml"], "public_prices": False, "terms_reviewed": False, "audit": AUDIT_DATE},
        "notes": "Индивидуальные алюминиевые системы без публичных цен — только quote_required и RFQ.",
        "priority": "medium",
    },
    {
        "key": "vlv", "name": "VLV Centre", "domain": "https://vlv.am",
        "allowed_hosts": ["vlv.am", "www.vlv.am"],
        "categories": ["appliances", "furniture", "plumbing", "decor"], "languages": ["hy", "ru", "en"], "method": "jsonld_sitemap", "connector_status": "needs_audit",
        "rate_limit_s": 3.0,
        "policy": {"robots": "allowed", "crawl_delay_s": 3, "search_disallowed": True, "disallow": ["/ajax-search-product", "/price/ajax", "/cart/*"],
                   "sitemaps": ["https://vlv.am/sitemap.xml"], "jsonld_product": None, "terms_reviewed": False, "audit": AUDIT_DATE},
        "notes": "Crawl-delay 3 с; поиск и ценовые AJAX-эндпоинты запрещены. Discovery — только через sitemap/каталог.",
        "priority": "high",
    },
    {
        "key": "vega", "name": "Vega", "domain": "https://vega.am",
        "allowed_hosts": ["vega.am", "www.vega.am"],
        "categories": ["appliances", "furniture", "decor"], "languages": ["hy", "ru", "en"], "method": "jsonld_sitemap", "connector_status": "needs_audit",
        "rate_limit_s": 3.0,
        "policy": {"robots": "allowed", "search_disallowed": True, "disallow": ["/*search=", "/*filter_name=", "/*sort="], "sitemaps": [], "platform": "OpenCart",
                   "jsonld_product": None, "terms_reviewed": False, "audit": AUDIT_DATE},
        "notes": "OpenCart; sitemap.xml пуст. Параметры search/filter запрещены robots.txt.",
        "priority": "high",
    },
]
