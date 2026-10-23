"""Layered product extraction for sites without (usable) JSON-LD, generic product-link discovery,
CAPTCHA reporting, the «parse catalogue» toggle and the dry-run test scan. Local fixtures (hy/ru/en)."""
import pytest
from sqlalchemy import select

from app import models as m
from app.catalog.extract import detect_restriction, extract_product
from app.catalog.indexer import crawl_links, product_urls
from app.catalog.net import FetchBlocked
from app.db import SessionLocal

pytestmark = pytest.mark.usefixtures("client")
SRC = {"id": "s1", "key": "shop_t", "domain": "https://shop.example", "allowed_hosts": ["shop.example"], "rate_limit_s": 0, "policy": {}}

MICRODATA_HY = """<html><body><div itemscope itemtype="https://schema.org/Product">
<h1 itemprop="name">Բազմոց Միլանո, մոխրագույն</h1><img itemprop="image" src="/img/milano.jpg">
<span itemprop="sku">MIL-220</span><div itemprop="offers" itemscope itemtype="https://schema.org/Offer">
<meta itemprop="price" content="485000"><meta itemprop="priceCurrency" content="AMD"><link itemprop="availability" href="https://schema.org/InStock"></div>
</div></body></html>"""
OG_RU = """<html><head><meta property="og:title" content="Кресло Oslo, бежевое"><meta property="og:image" content="https://shop.example/oslo.jpg">
<meta property="product:price:amount" content="189 900"><meta property="product:price:currency" content="AMD"></head><body><h1>Кресло Oslo</h1></body></html>"""
HTML_EN = """<html><head><meta name="description" content="Oak dining table for 6"></head><body><nav>Home</nav>
<div class="product"><h1>Dining table Nord 160</h1><img src="/media/catalog/nord.jpg"><div class="price">245 000 ֏</div>
<p>SKU: NRD-160</p></div><footer>Delivery 3 000 ֏</footer></body></html>"""
NOTHING = "<html><body><h1>About us</h1><p>We are a family business.</p></body></html>"
CAPTCHA = "<html><head><title>Just a moment...</title></head><body><div class='cf-challenge'></div></body></html>"


def test_methods_in_order_and_flags():
    p, how = extract_product(MICRODATA_HY, "https://shop.example/p/milano", SRC)
    assert how == "microdata" and p.price_amd == 485000 and p.sku == "MIL-220" and p.normalized_category == "sofa"
    assert p.main_image_url == "https://shop.example/img/milano.jpg" and p.availability_status == "in_stock" and p.manual_confirmation_required
    p, how = extract_product(OG_RU, "https://shop.example/p/oslo", SRC)
    assert how == "opengraph" and p.price_amd == 189900 and p.normalized_category == "armchair" and p.confidence <= 0.65
    p, how = extract_product(HTML_EN, "https://shop.example/p/nord", SRC)
    assert how == "html" and p.price_amd == 245000 and p.sku == "NRD-160" and p.normalized_category == "dining_table"
    assert p.main_image_url == "https://shop.example/media/catalog/nord.jpg" and p.confidence <= 0.55
    assert extract_product(NOTHING, "https://shop.example/about", SRC) == (None, None)  # no price → not a product
    assert detect_restriction(CAPTCHA) == "anti-bot challenge" and detect_restriction(HTML_EN) is None


def test_jsonld_pages_still_use_the_jsonld_parser():
    from pathlib import Path

    html = (Path(__file__).parent / "fixtures" / "vlv_product.html").read_text(encoding="utf-8")
    p, how = extract_product(html, "https://vlv.am/Product/36469", {**SRC, "allowed_hosts": ["vlv.am"]})
    assert how == "jsonld" and not p.parser_version.startswith("layered")


class Fetcher:
    def __init__(self, pages, sitemaps=()):
        self.pages, self.sitemaps, self.calls = pages, list(sitemaps), []

    def robots_sitemaps(self, url):
        return self.sitemaps

    def fetch(self, url, hosts, rate_limit_s=None, max_bytes=None, **_):
        self.calls.append(url)
        if url not in self.pages:
            raise FetchBlocked("404")
        return type("R", (), {"text": self.pages[url]})()


def _fresh(key):
    from app.catalog.indexer import _sitemap_cache

    _sitemap_cache(key).unlink(missing_ok=True)


def test_discovery_from_robots_sitemap_and_by_crawling():
    _fresh("shop_t")
    f = Fetcher({"https://shop.example/sm.xml": "<urlset><url><loc>https://shop.example/product/a</loc></url><url><loc>https://shop.example/about</loc></url></urlset>"},
                sitemaps=["https://shop.example/sm.xml"])
    assert product_urls(SRC, f) == ["https://shop.example/product/a"]
    _fresh("shop_t")
    home = '<a href="/catalog/sofas">Sofas</a><a href="https://other.example/product/x">x</a><a href="mailto:a@b">m</a>'
    cat = '<a href="/product/milano">Milano</a><a href="/product/oslo">Oslo</a><a href="/catalog/sofas?page=2">2</a>'
    f = Fetcher({"https://shop.example": home, "https://shop.example/catalog/sofas": cat, "https://shop.example/catalog/sofas?page=2": '<a href="/product/rio">Rio</a>'})
    urls = product_urls(SRC, f)  # no robots sitemap, /sitemap.xml missing → bounded crawl, own host only
    assert urls == ["https://shop.example/product/milano", "https://shop.example/product/oslo", "https://shop.example/product/rio"]
    assert len(crawl_links(SRC, f, __import__("re").compile(r"/product/"), max_pages=1)) == 0  # bounded
    _fresh("shop_t")


def test_fallback_products_reach_designs_only_after_approval(client, admin, monkeypatch):
    from app.catalog.discovery import _cache_lookup_factory, upsert_record
    from app.config import get_settings

    with SessionLocal() as db:
        src = db.scalar(select(m.ExternalSource).where(m.ExternalSource.key == "idealsystem"))
        sd = {**SRC, "id": src.id, "key": src.key}
        p, how = extract_product(MICRODATA_HY, "https://www.idealsystem.am/product-page/milano", sd)
        rec = upsert_record(db, p)
        db.commit()
        assert rec.review_status == "pending_review"
        lookup = _cache_lookup_factory(db)
        assert not [x for x in lookup(src.id, "sofa") if x.name.startswith("Բազմոց Միլանո")]
        rid = rec.id
    assert client.post(f"/api/v1/catalog/external/review/{rid}", headers=admin, json={"decision": "approved"}).json()["ok"]
    with SessionLocal() as db:
        assert [x for x in _cache_lookup_factory(db)(src.id, "sofa") if x.name.startswith("Բազմոց Միլանո")]
        db.query(m.ExternalProductRecord).filter_by(id=rid).delete()
        db.commit()

    # toggle «parse catalogue» and dry-run test scan (nothing written)
    sid = src.id
    r = client.patch(f"/api/v1/admin/sources/{sid}", headers=admin, json={"catalog_index": True}).json()
    assert r["indexed"] and r["enabled"] and r["live_enabled"]
    profal = client.get("/api/v1/admin/sources", headers=admin).json()
    rfq = next(s for s in profal if s["key"] == "profal")
    assert client.patch(f"/api/v1/admin/sources/{rfq['id']}", headers=admin, json={"catalog_index": True}).status_code == 422
    assert client.post(f"/api/v1/admin/sources/{sid}/test-scan", headers=admin).json()["code"] == "catalog.live_disabled"
    monkeypatch.setattr(get_settings(), "external_fetch_live", True)
    pages = {"https://www.idealsystem.am/store-products-sitemap.xml": "<urlset><url><loc>https://www.idealsystem.am/product-page/milano</loc></url></urlset>",
             "https://www.idealsystem.am/product-page/milano": MICRODATA_HY}
    import app.catalog.net as net

    monkeypatch.setattr(net, "SafeFetcher", lambda *a, **k: Fetcher(pages))
    _fresh("idealsystem__scan")
    before = None
    with SessionLocal() as db:
        before = db.query(m.ExternalProductRecord).count()
    scan = client.post(f"/api/v1/admin/sources/{sid}/test-scan", headers=admin).json()
    assert scan["urls_found"] >= 1 and scan["methods"].get("microdata") == 1 and scan["sample"][0]["price_amd"] == 485000
    with SessionLocal() as db:
        assert db.query(m.ExternalProductRecord).count() == before  # dry run
    from tests.conftest import login

    assert client.post(f"/api/v1/admin/sources/{sid}/test-scan", headers=login(client)).status_code == 403
    client.patch(f"/api/v1/admin/sources/{sid}", headers=admin, json={"catalog_index": False})
    _fresh("idealsystem__scan")


def test_jsonld_image_object_and_malformed_jsonld():
    """Found live on Ideal System (Wix): image as ImageObject crashed the JSON-LD parser."""
    html = ('<script type="application/ld+json">{"@type":"Product","name":"Լվացարան Ideal 60","sku":"ID-60",'
            '"image":{"@type":"ImageObject","url":"https://www.idealsystem.am/i/60.jpg"},'
            '"offers":{"price":"52000","priceCurrency":"AMD","availability":"https://schema.org/InStock"}}</script>')
    p, how = extract_product(html, "https://www.idealsystem.am/product-page/id-60", SRC)
    assert how == "jsonld" and p.main_image_url == "https://www.idealsystem.am/i/60.jpg" and p.price_amd == 52000
    broken = '<script type="application/ld+json">{"@type":"Product","name":"X","offers":[]}</script>' + HTML_EN
    p, how = extract_product(broken, "https://shop.example/p/nord", SRC)
    assert p is not None


def test_discovery_trusts_product_sitemaps_and_finds_catalogue_leaves():
    """OpenCart-style product sitemaps (Vega) and Bitrix-style catalogue trees (Nor Tun) without product-like URLs."""
    _fresh("shop_t")
    idx = ("<sitemapindex><sitemap><loc>https://shop.example/sitemap-categories.xml</loc></sitemap>"
           "<sitemap><loc>https://shop.example/sitemap-products-1.xml</loc></sitemap></sitemapindex>")
    f = Fetcher({"https://shop.example/sitemap.xml": idx,
                 "https://shop.example/sitemap-products-1.xml": "<urlset><url><loc>https://shop.example/home/sofas/sofa-milano.html</loc></url></urlset>",
                 "https://shop.example/sitemap-categories.xml": "<urlset><url><loc>https://shop.example/home/sofas.html</loc></url></urlset>"})
    assert product_urls(SRC, f) == ["https://shop.example/home/sofas/sofa-milano.html"]
    assert "https://shop.example/sitemap-categories.xml" not in f.calls  # category sitemap not even fetched
    _fresh("shop_t")
    tree = "".join(f"<url><loc>https://shop.example{p}</loc></url>" for p in
                   ("/catalog/", "/catalog/furniture/", "/catalog/furniture/chairs/", "/catalog/furniture/chairs/oslo-beige/",
                    "/catalog/furniture/chairs/rio/", "/about/", "/catalog/sale/"))
    f = Fetcher({"https://shop.example/sitemap.xml": f"<urlset>{tree}</urlset>"})
    assert product_urls(SRC, f) == ["https://shop.example/catalog/furniture/chairs/oslo-beige/", "https://shop.example/catalog/furniture/chairs/rio/",
                                    "https://shop.example/catalog/sale/"]
    _fresh("shop_t")


def test_site_builder_placeholders_are_not_products():
    """Found live on Ideal System: the Wix store still holds the template items «I'm a product» at 25 AMD."""
    html = '<script type="application/ld+json">{"@type":"Product","name":"I\'m a product","offers":{"price":"25","priceCurrency":"AMD"}}</script>'
    assert extract_product(html, "https://www.idealsystem.am/product-page/i-m-a-product-1", SRC) == (None, "placeholder")


def test_word_sitemap_is_not_a_product_hint():
    from app.catalog.indexer import PRODUCT_SITEMAP_RE

    assert not PRODUCT_SITEMAP_RE.search("sitemap-iblock-24.xml".replace("sitemap", ""))  # Bitrix: «s-item-ap» is not «item»
    assert PRODUCT_SITEMAP_RE.search("sitemap-products-1.xml".replace("sitemap", ""))
