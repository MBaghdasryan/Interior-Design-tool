"""Generic connector for sources that publish schema.org Product JSON-LD on product
pages and list categories in a sitemap (Domus today; VLV/Vega/Nor Tun after audit).
Discovery path: categories sitemap → matching category page → product links →
product page JSON-LD. Site search endpoints are never used (disallowed by robots)."""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

from ..net import FetchBlocked, SafeFetcher
from ..normalize import classify, detect_unit, is_accessory, normalize_availability, parse_dimensions, parse_package_coverage, parse_price, to_amd, validate
from ..schema import Dimensions, FieldProvenance, NormalizedExternalProduct
from .base import ConnectorHealth, ExternalCatalogConnector, NeedQuery, SearchFilters

# English URL-slug hints per normalised category (category pages use English slugs)
SLUG_HINTS: dict[str, list[str]] = {
    "spot_light": ["led-panel", "spot", "downlight", "recessed"],
    "pendant_light": ["pendant", "chandelier", "hanging"],
    "wall_light": ["wall-light", "sconce"],
    "led_strip": ["led-strip", "led-tape"],
    "floor_tile": ["porcelain", "floor-tile", "granite"],
    "wall_tile": ["wall-tile", "mosaic", "ceramic"],
    "floor_laminate": ["laminate"],
    "floor_parquet": ["parquet", "engineered"],
    "wall_paint": ["paint"],
    "putty": ["putty", "plaster"],
    "tile_adhesive": ["adhesive", "glue"],
    "toilet": ["toilet", "wc"],
    "installation": ["installation", "frame"],
    "vanity": ["washbasin", "sink", "vanity", "basin"],
    "bathtub": ["bathtub", "bath-tub", "baths"],
    "shower": ["shower"],
    "faucet": ["mixer", "faucet", "tap"],
    "towel_dryer": ["towel"],
    "fridge": ["refrigerator", "fridge"],
    "washer": ["washing-machine", "washer"],
    "dishwasher": ["dishwasher"],
    "cooktop": ["hob", "cooktop"],
    "oven": ["oven"],
    "hood": ["hood", "extractor"],
    "tv": ["tv", "television"],
    "sofa": ["sofa", "couch"],
    "armchair": ["armchair"],
    "bed": ["bed"],
    "wardrobe": ["wardrobe"],
    "dining_table": ["dining-table", "tables"],
    "dining_chair": ["chair"],
    "door_interior": ["interior-door", "doors"],
}

LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")
LDJSON_RE = re.compile(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", re.S | re.I)
PRODUCT_LINK_RE = re.compile(r'href="([^"]*/product/[^"#?]+)"')


def _iter_jsonld(html: str):
    for m in LDJSON_RE.finditer(html):
        try:
            data = json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            x = stack.pop(0)
            if isinstance(x, dict):
                if "@graph" in x:
                    stack.extend(x["@graph"])
                yield x


def parse_product_page(html: str, url: str, source: dict, parser_version: str, now: datetime | None = None) -> NormalizedExternalProduct | None:
    now = now or datetime.now(timezone.utc)
    product = next((x for x in _iter_jsonld(html) if str(x.get("@type", "")).lower() == "product"), None)
    if not product:
        return None
    crumbs = next((x for x in _iter_jsonld(html) if x.get("@type") == "BreadcrumbList"), None)
    crumb_names = [i.get("name", "") for i in (crumbs or {}).get("itemListElement", [])]
    category = crumb_names[-2] if len(crumb_names) >= 2 else None

    offers = product.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    price_raw = offers.get("price") or offers.get("lowPrice")
    price, cur_from_text = parse_price(price_raw)
    currency = (offers.get("priceCurrency") or cur_from_text or None)
    name = product.get("name", "").strip()
    desc = (product.get("description") or "").strip()
    brand = product.get("brand", {})
    brand = brand.get("name") if isinstance(brand, dict) else (brand or None)
    dims = parse_dimensions(" ".join([name, desc]))
    avail_raw = offers.get("availability")
    images = product.get("image") or []
    images = [images] if isinstance(images, str) else list(images)
    warnings: list[str] = []
    # Template artefacts seen during audit: logo used as product image
    real_images = [i for i in images if not re.search(r"/logo\.(png|svg|jpg)$", i, re.I)]
    if images and not real_images:
        warnings.append("Изображение в разметке — логотип сайта; фото товара не получено")

    delivery = {}
    ship = offers.get("shippingDetails") or {}
    dt = (ship.get("deliveryTime") or {}) if isinstance(ship, dict) else {}
    if dt:
        h, t = dt.get("handlingTime", {}), dt.get("transitTime", {})
        delivery = {
            "days_min": (h.get("minValue") or 0) + (t.get("minValue") or 0),
            "days_max": (h.get("maxValue") or 0) + (t.get("maxValue") or 0),
            "country": (ship.get("shippingDestination") or {}).get("addressCountry"),
        }

    prov = [FieldProvenance(field=f, url=url, method="jsonld", value=str(v)) for f, v in
            (("name", name), ("sku", product.get("sku")), ("price", price_raw), ("currency", currency), ("availability", avail_raw)) if v is not None]
    p = NormalizedExternalProduct(
        external_source_id=source["id"],
        source_key=source["key"],
        external_product_id=product.get("sku") or product.get("productID"),
        canonical_url=offers.get("url") or url,
        name=name,
        brand=brand,
        sku=product.get("sku"),
        mpn=product.get("mpn"),
        category=category,
        normalized_category=classify(name, category, desc),
        description_summary=desc[:400] or None,
        dimensions=Dimensions(**dims),
        color=product.get("color"),
        material=product.get("material"),
        price_value=price,
        original_currency=currency,
        price_amd=to_amd(price, currency),
        price_valid_until=offers.get("priceValidUntil"),
        unit_of_sale=detect_unit(name, desc, str(offers.get("priceSpecification", ""))),
        package_coverage_m2=parse_package_coverage(desc),
        availability_status=normalize_availability(avail_raw),
        # availability from markup is weak evidence (template fields were observed); flagged below
        availability_evidence=f"schema.org offers.availability={avail_raw}" if avail_raw else None,
        delivery=delivery,
        main_image_url=real_images[0] if real_images else None,
        image_urls=real_images,
        source_language=(re.search(r'og:locale" content="([a-z]{2})', html) or [None, None])[1],
        retrieved_at=now,
        price_checked_at=now if price is not None else None,
        availability_checked_at=now if avail_raw else None,
        parser_version=parser_version,
        provenance=prov,
        validation_warnings=warnings,
    )
    p = validate(p)
    if avail_raw and p.availability_status == "in_stock":
        # markup-only stock claims are not trusted for ordering
        p.validation_warnings.append("Наличие указано только в разметке — подтвердить перед заказом")
        p.confidence = round(max(0.0, p.confidence - 0.05), 2)
    return p


class JsonLdSitemapConnector(ExternalCatalogConnector):
    parser_version = "jsonld-1.1"
    MAX_CATEGORY_PAGES = 1
    MAX_PRODUCTS_PER_NEED = 4

    def __init__(self, source: dict, fetcher: SafeFetcher | None = None, live: bool = False, cache_lookup=None):
        super().__init__(source)
        self.fetcher = fetcher or SafeFetcher()
        self.live = live
        self.cache_lookup = cache_lookup  # callable(source_id, category) -> list[NormalizedExternalProduct]
        self._category_urls: list[str] | None = None

    def _get(self, url: str) -> str:
        r = self.fetcher.fetch(url, self.source["allowed_hosts"], rate_limit_s=self.source.get("rate_limit_s", 3.0))
        return r.text

    def category_urls(self) -> list[str]:
        if self._category_urls is None:
            urls: list[str] = []
            for sm in self.source.get("policy", {}).get("sitemaps", []):
                if "categor" not in sm:
                    continue
                urls.extend(LOC_RE.findall(self._get(sm)))
            self._category_urls = urls
        return self._category_urls

    def search_products(self, need: NeedQuery, filters: SearchFilters) -> list[NormalizedExternalProduct]:
        cached = list(self.cache_lookup(self.source["id"], need.category)) if self.cache_lookup else []
        results = cached
        if self.live and len(cached) < filters.limit:
            hints = SLUG_HINTS.get(need.category, [])
            try:
                cats = [u for u in self.category_urls() if any(h in u.lower() for h in hints)][: self.MAX_CATEGORY_PAGES]
            except FetchBlocked:
                cats = []
            seen = {p.canonical_url for p in cached}
            for cu in cats:
                try:
                    html = self._get(cu)
                except FetchBlocked:
                    break
                links = list(dict.fromkeys(urljoin(cu, m) for m in PRODUCT_LINK_RE.findall(html)))
                for link in links[: self.MAX_PRODUCTS_PER_NEED]:
                    if link in seen:
                        continue
                    try:
                        p = parse_product_page(self._get(link), link, self.source, self.parser_version)
                    except FetchBlocked:
                        continue
                    if p and is_accessory(p.name):
                        seen.add(link)
                        continue
                    if p:
                        # never infer the category from the page we came from: unrecognised
                        # items go to the manual review queue instead of into a design
                        results.append(p)
                        seen.add(link)
        return filter_candidates(results, need, filters)

    def get_product(self, url_or_id: str) -> NormalizedExternalProduct | None:
        if not self.live:
            return None
        url = url_or_id if url_or_id.startswith("http") else urljoin(self.source["domain"], f"/product/{url_or_id}")
        return parse_product_page(self._get(url), url, self.source, self.parser_version)

    def get_connector_health(self) -> ConnectorHealth:
        if not self.live:
            return ConnectorHealth(status=self.source.get("connector_status", "needs_audit"), message="Live-запросы выключены (EXTERNAL_FETCH_LIVE=false) — работа из кэша")
        t = time.time()
        try:
            n = len(self.category_urls())
            return ConnectorHealth(status="ok" if n else "degraded", message=f"{n} категорий в sitemap", latency_ms=int((time.time() - t) * 1000))
        except FetchBlocked as e:
            return ConnectorHealth(status="blocked", message=str(e), latency_ms=int((time.time() - t) * 1000))


def filter_candidates(items: list[NormalizedExternalProduct], need: NeedQuery, f: SearchFilters) -> list[NormalizedExternalProduct]:
    out = []
    for p in items:
        if p.normalized_category != need.category:
            continue
        if f.only_priced and p.price_amd is None:
            continue
        if f.only_available and p.availability_status != "in_stock":
            continue
        if not f.allow_quote and p.quote_required:
            continue
        if f.max_price_amd and p.price_amd and p.price_amd > f.max_price_amd:
            continue
        if f.min_price_amd and p.price_amd and p.price_amd < f.min_price_amd:
            continue
        if need.max_width_mm and p.dimensions.width_mm and p.dimensions.width_mm > need.max_width_mm:
            continue
        out.append(p)
    return out[: f.limit]
