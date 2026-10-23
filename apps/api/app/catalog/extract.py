"""Product extraction from any public product page — layered, most reliable first:

1. JSON-LD schema.org Product  — `parse_product_page` (unchanged; Domus, VLV and most shops)
2. microdata (itemscope Product / itemprop name, price, priceCurrency, image, sku)
3. OpenGraph / product meta tags (og:title, og:image, product:price:amount / :currency)
4. HTML heuristics: <h1> + the first price with a currency (֏ AMD դր драм руб ₽ $ €) + og/main image

Methods 2–4 are weaker evidence: products from them are flagged for manual confirmation, so they
reach the review queue first and never enter a design unchecked. Nothing is invented — a field
that is not on the page stays empty. Pages with CAPTCHA / anti-bot challenges are reported
(`detect_restriction`) and never bypassed."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urljoin

from .connectors.jsonld import parse_product_page
from .normalize import classify, detect_unit, normalize_availability, parse_dimensions, parse_price, to_amd, validate
from .schema import Dimensions, FieldProvenance, NormalizedExternalProduct

PARSER_VERSION = "layered-1.0"
_NUM = r"\d{1,3}(?:[ \u00a0.,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
PRICE_RE = re.compile(rf"(?:[$€₽]\s?(?:{_NUM})|(?<![\d.,])(?:{_NUM})\s?(?:֏|AMD|դր\.?|драм|руб\.?|₽|USD|EUR|\$|€))", re.I)
RESTRICTION_MARKERS = (("g-recaptcha", "captcha"), ("h-captcha", "captcha"), ("hcaptcha.com", "captcha"), ("cf-challenge", "anti-bot challenge"),
                       ("challenges.cloudflare.com", "anti-bot challenge"), ("just a moment...", "anti-bot challenge"), ("attention required! | cloudflare", "anti-bot challenge"),
                       ("ddos-guard", "anti-bot challenge"), ("are you a robot", "captcha"), ("verify you are human", "captcha"))


# demo items that site builders ship with a new store (Wix «I'm a product», WooCommerce samples) — never real products
PLACEHOLDER_RE = re.compile(r"^\s*(i'?m a product|sample product|product name|lorem ipsum|test product|товар \d+|demo product)\b", re.I)


def is_placeholder(name: str | None) -> bool:
    return bool(PLACEHOLDER_RE.search(name or ""))


def detect_restriction(html: str) -> str | None:
    low = html[:20000].lower()
    return next((kind for marker, kind in RESTRICTION_MARKERS if marker in low), None)


def _soup(html: str):
    from bs4 import BeautifulSoup

    return BeautifulSoup(html, "lxml")


def _meta(soup, *names: str) -> str | None:
    for n in names:
        tag = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n}) or soup.find("meta", attrs={"itemprop": n})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _build(source: dict, url: str, method: str, *, name: str, price_raw=None, currency=None, image=None, sku=None, brand=None, category=None,
           description=None, availability=None, now: datetime | None = None) -> NormalizedExternalProduct | None:
    name = _clean(name)
    if not name or len(name) < 3:
        return None
    now = now or datetime.now(timezone.utc)
    price, cur = parse_price(price_raw) if price_raw not in (None, "") else (None, None)
    currency = (currency or cur or None)
    currency = currency.upper() if currency else None
    desc = _clean(description)[:400] or None
    img = urljoin(url, image) if image else None
    prov = [FieldProvenance(field=f, url=url, method=method, value=str(v)[:200]) for f, v in (("name", name), ("price", price_raw), ("currency", currency), ("image", img)) if v]
    p = NormalizedExternalProduct(
        external_source_id=source["id"], source_key=source["key"], external_product_id=sku, canonical_url=url, name=name[:300], brand=brand, sku=sku,
        category=category, normalized_category=classify(name, category, desc or ""), description_summary=desc,
        dimensions=Dimensions(**parse_dimensions(" ".join([name, desc or ""]))), price_value=price, original_currency=currency,
        price_amd=to_amd(price, currency), unit_of_sale=detect_unit(name, desc or ""), availability_status=normalize_availability(availability),
        availability_evidence=f"{method}: {availability}" if availability else None, main_image_url=img, image_urls=[img] if img else [],
        retrieved_at=now, price_checked_at=now if price is not None else None, parser_version=f"{PARSER_VERSION}:{method}", provenance=prov,
        validation_warnings=[f"Извлечено методом «{method}» (без JSON-LD) — требуется проверка"])
    p = validate(p)
    p.manual_confirmation_required = True  # weaker evidence than JSON-LD: review before use in a design
    p.confidence = round(min(p.confidence, {"microdata": 0.75, "opengraph": 0.65, "html": 0.55}[method]), 2)
    return p


def _microdata(soup, url: str, source: dict) -> NormalizedExternalProduct | None:
    scope = soup.find(attrs={"itemtype": re.compile(r"schema\.org/Product", re.I)})
    if not scope:
        return None

    def prop(name):
        el = scope.find(attrs={"itemprop": name})
        if not el:
            return None
        return el.get("content") or el.get("src") or el.get("href") or _clean(el.get_text(" "))
    return _build(source, url, "microdata", name=prop("name") or "", price_raw=prop("price") or prop("lowPrice"), currency=prop("priceCurrency"),
                  image=prop("image"), sku=prop("sku") or prop("productID"), brand=prop("brand"), category=prop("category"), description=prop("description"),
                  availability=prop("availability"))


def _opengraph(soup, url: str, source: dict) -> NormalizedExternalProduct | None:
    price = _meta(soup, "product:price:amount", "og:price:amount", "price")
    title = _meta(soup, "og:title")
    if not (title and price):  # og:title alone is any page — require a product price tag
        return None
    return _build(source, url, "opengraph", name=title, price_raw=price, currency=_meta(soup, "product:price:currency", "og:price:currency", "priceCurrency"),
                  image=_meta(soup, "og:image"), sku=_meta(soup, "product:retailer_item_id", "sku"), brand=_meta(soup, "product:brand"),
                  description=_meta(soup, "og:description", "description"), availability=_meta(soup, "product:availability", "og:availability"))


def _heuristic(soup, url: str, source: dict) -> NormalizedExternalProduct | None:
    h1 = soup.find("h1")
    if not h1:
        return None
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    title = h1.get_text(" ")
    h1.clear()  # model numbers in the title («Nord 160») must not merge with the price
    # the price nearest to the title: search the title's container first, then the page
    box = h1
    for _ in range(4):
        if box.parent is None:
            break
        box = box.parent
        if PRICE_RE.search(box.get_text(" ")):
            break
    m = PRICE_RE.search(box.get_text(" ")) or PRICE_RE.search(soup.get_text(" "))
    if not m:
        return None
    img = _meta(soup, "og:image")
    if not img:
        im = (box.find("img") if box else None) or soup.find("img", src=re.compile(r"product|upload|catalog|media", re.I))
        img = (im.get("data-src") or im.get("src")) if im else None
    sku = None
    sm = re.search(r"(?:Артикул|SKU|Код|Կոդ|Արտիկուլ)\s*[:#]?\s*([A-Za-z0-9\-_.\/]{3,40})", soup.get_text(" "), re.I)
    if sm:
        sku = sm.group(1)
    return _build(source, url, "html", name=title, price_raw=m.group(0), image=img, sku=sku, description=_meta(soup, "description", "og:description"))


def extract_product(html: str, url: str, source: dict) -> tuple[NormalizedExternalProduct | None, str | None]:
    """→ (product, method) — method is jsonld | microdata | opengraph | html, or None when nothing product-like was found."""
    try:
        p = parse_product_page(html, url, source, "jsonld-index-1.0")
    except Exception:  # noqa: BLE001 - malformed / unusual JSON-LD: fall through to the other methods
        p = None
    if p:
        return (None, "placeholder") if is_placeholder(p.name) else (p, "jsonld")
    try:
        soup = _soup(html)
    except Exception:  # noqa: BLE001 - unparsable markup: nothing to extract
        return None, None
    for fn, name in ((_microdata, "microdata"), (_opengraph, "opengraph"), (_heuristic, "html")):
        p = fn(soup, url, source)
        if p:
            return (None, "placeholder") if is_placeholder(p.name) else (p, name)
    return None, None
