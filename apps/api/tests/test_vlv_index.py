"""P0-3: second live source (VLV, background index) — parser contract on a real
(trimmed) product page, resumable index crawler, classifier regressions found on
real data, and the end-to-end path «two sources → shortlist → variant → estimate
with links to both stores» on fixtures (no network)."""
from pathlib import Path

import pytest
from sqlalchemy import select

from app import models as m
from app.catalog.connectors.jsonld import parse_product_page
from app.catalog.discovery import source_dict, upsert_record
from app.catalog.indexer import _sitemap_cache, crawl_batch
from app.catalog.net import FetchBlocked
from app.catalog.normalize import classify
from app.config import get_settings
from app.db import SessionLocal

FIX = Path(__file__).parent / "fixtures"
VLV_HTML = (FIX / "vlv_product.html").read_text(encoding="utf-8")
DOMUS_HTML = (FIX / "domus_product.html").read_text(encoding="utf-8")
pytestmark = pytest.mark.usefixtures("client")


def test_vlv_product_jsonld_contract():
    p = parse_product_page(VLV_HTML, "https://vlv.am/Product/36469", {"id": "s", "key": "vlv"}, "t")
    assert p.sku == "36469" and p.brand == "FLORENTINA" and p.price_amd == 48500 and p.original_currency == "AMD"
    assert p.normalized_category == "vanity"  # JSON-LD category «Ներկառուցվող լվացարաններ» = built-in washbasins
    assert p.availability_status == "in_stock" and any("подтвердить перед заказом" in w for w in p.validation_warnings)
    assert p.canonical_url.startswith("https://vlv.am/") and p.main_image_url.endswith(".webp")


@pytest.mark.parametrize("text,cat", [
    ("Ներկառուցվող լվացարաններ FLORENTINA", "vanity"),        # was spot_light: «built-in» is not a lamp
    ("Լուսադիոդային լուսատու 18W ներկառուցվող", "spot_light"),
    ("Ներկ ջրադիսպերսիոն 10լ", "wall_paint"),
    ("Ներկառուցվող ջեռոց", "oven"),                          # «ներկ» (paint) is the stem of «ներկառուցվող»
    ("Встраиваемая варочная панель", "cooktop"),
    ("Մարտկոցներ GP", None),
    # live index batch 2026-10-22 findings
    ("MART LIGA Հեռուստացույցի տակդիրներ", "tv_unit"),
    ("HI-LUXE 4318 Ճաշի սպասքի հավաքածուներ", None),           # dishware set, not a dishwasher
    ("Սպասք լվացող մեքենա Hisense", "dishwasher"),
    ("SIMFER 8662SM Օդաքարշ պահարաններ", "hood"),
])
def test_classifier_regressions_from_real_vlv_data(text, cat):
    assert classify(text) == cat


@pytest.mark.parametrize("name,category", [
    ("LEOSTAR LS3994", "Հեռուստացույցի կախիչներ"),   # TV wall mount
    ("- AV1metr", "Բաժանարարներ"),                    # AV splitter / cable
    ("SIMFER RING CARBON", "Օդաքաշ պահարանի ֆիլտրեր"),  # hood filter
])
def test_accessories_detected_from_store_category(name, category):
    from app.catalog.normalize import is_accessory

    assert is_accessory(name, category)


class FakeFetcher:
    """Serves a sitemap and product pages; records calls (no network)."""

    def __init__(self, pages: dict[str, str]):
        self.pages, self.calls = pages, []

    def fetch(self, url, allowed_hosts, rate_limit_s=None, max_bytes=None, **_):
        assert rate_limit_s >= 3.0  # VLV crawl-delay is honoured
        self.calls.append(url)
        if url not in self.pages:
            raise FetchBlocked("404")
        return type("R", (), {"text": self.pages[url]})()


def _pages():
    battery = VLV_HTML.replace("FLORENTINA ASTORIA 800 WHITE /10.170.00800.001", "GP 15AUP-2UE4").replace("Ներկառուցվող լվացարաններ", "Մարտկոցներ").replace("36469", "2818")
    siphon = VLV_HTML.replace("FLORENTINA ASTORIA 800 WHITE /10.170.00800.001", "Սիֆոն լվացարանի համար").replace("36469", "5000")
    sitemap = "<urlset>" + "".join(f"<url><loc>https://vlv.am/{p}</loc></url>" for p in ("category/furniture", "Product/36469", "Product/2818", "Product/5000")) + "</urlset>"
    return {"https://vlv.am/sitemap.xml": sitemap, "https://vlv.am/Product/36469": VLV_HTML, "https://vlv.am/Product/2818": battery, "https://vlv.am/Product/5000": siphon}


def test_index_crawler_is_resumable_and_filters(monkeypatch):
    s = get_settings()
    with SessionLocal() as db:
        vlv = db.scalar(select(m.ExternalSource).where(m.ExternalSource.key == "vlv"))
        assert vlv.connector_type == "jsonld_index" and vlv.live_enabled and vlv.enabled
        assert crawl_batch(db, vlv, batch=5, fetcher=FakeFetcher(_pages()))["status"] == "live_disabled"  # global switch off by default
        monkeypatch.setattr(s, "external_fetch_live", True)
        _sitemap_cache("vlv").unlink(missing_ok=True)
        f = FakeFetcher(_pages())
        r1 = crawl_batch(db, vlv, batch=2, fetcher=f)
        assert r1["total"] == 3 and r1["cursor"] == 2 and r1["indexed"] == 1 and r1["irrelevant"] == 1  # category URL is not a product
        r2 = crawl_batch(db, vlv, batch=2, fetcher=f)
        assert r2["cursor"] == 3 and r2["accessories"] == 1 and r2["indexed"] == 0
        assert f.calls.count("https://vlv.am/sitemap.xml") == 1  # sitemap cached between batches
        r3 = crawl_batch(db, vlv, batch=1, fetcher=f)  # a finished pass restarts → refresh
        assert r3["cursor"] == 1 and db.get(m.ExternalSource, vlv.id).stats["index"]["passes"] == 1
        recs = db.scalars(select(m.ExternalProductRecord).where(m.ExternalProductRecord.source_id == vlv.id)).all()
        assert [r.normalized_category for r in recs] == ["vanity"]  # one record, updated in place on the refresh pass
        assert db.scalars(select(m.ExternalConnectorRun).where(m.ExternalConnectorRun.source_id == vlv.id, m.ExternalConnectorRun.kind == "index")).all()


def test_two_sources_shortlist_variant_estimate_with_links(client, designer):
    """External catalog on → shortlist from Domus and VLV (cached records, no network) → variant → estimate links to both."""
    with SessionLocal() as db:
        for key, html, url in (("domus", DOMUS_HTML, "https://domus.am/product/led-panel"), ("vlv", VLV_HTML, "https://vlv.am/Product/36469")):
            src = db.scalar(select(m.ExternalSource).where(m.ExternalSource.key == key))
            upsert_record(db, parse_product_page(html, url, source_dict(src), "t"))
        db.commit()
    pid = client.post("/api/v1/projects", headers=designer, json={"title": "Two sources", "city": "Yerevan"}).json()["id"]
    assert client.post(f"/api/v1/projects/{pid}/use-demo-geometry", headers=designer).status_code == 200
    client.post(f"/api/v1/projects/{pid}/geometry/control-dimension", headers=designer, json={"wall_id": "W1", "measured_mm": 9600})
    assert client.post(f"/api/v1/projects/{pid}/geometry/confirm", headers=designer).status_code == 200
    r = client.post(f"/api/v1/projects/{pid}/generate", headers=designer,
                    json={"product_source": "external", "external_settings": {"sources": ["domus", "vlv"], "allow_quote": True}})
    assert r.status_code == 200, r.text
    v = client.get(f"/api/v1/projects/{pid}/variants", headers=designer).json()[0]
    lines = client.get(f"/api/v1/projects/{pid}/variants/{v['id']}", headers=designer).json()["version"]["estimate"]["lines"]
    urls = {ln.get("url") or "" for ln in lines}
    assert any("vlv.am/" in u for u in urls), "VLV product with link in the estimate"
    assert any("domus.am/" in u for u in urls), "Domus product with link in the estimate"
    vlv_line = next(ln for ln in lines if "vlv.am/" in (ln.get("url") or ""))
    assert vlv_line["sku"] == "36469" and vlv_line["unit_price"] == 48500 and vlv_line["price_status"] == "confirmed"


def test_sitemap_index_is_expanded_for_full_catalogue_sources(monkeypatch):
    """Domus publishes a sitemap index (72 pages); the indexer follows product sitemap pages only."""
    from app.catalog.indexer import _sitemap_cache, product_urls

    pages = {"https://domus.am/sitemap-products.xml": "<urlset><url><loc>https://domus.am/sitemap-products/page-1.xml</loc></url>"
                                                      "<url><loc>https://domus.am/sitemap-blog.xml</loc></url></urlset>",
             "https://domus.am/sitemap-products/page-1.xml": "<urlset><url><loc>https://domus.am/product/teka</loc></url><url><loc>https://domus.am/product/x-y</loc></url>"
                                                             "<url><loc>https://domus.am/category/a</loc></url></urlset>"}

    class F:
        calls = []

        def fetch(self, url, hosts, rate_limit_s=None, max_bytes=None, **_):
            self.calls.append(url)
            return type("R", (), {"text": pages[url]})()

    src = {"key": "domus_t", "allowed_hosts": ["domus.am"], "rate_limit_s": 3.0,
           "policy": {"sitemaps": ["https://domus.am/sitemap-products.xml"], "child_sitemap_regex": r"sitemap-products/page-\d+\.xml", "product_url_regex": r"/product/[^/]+$"}}
    _sitemap_cache("domus_t").unlink(missing_ok=True)
    f = F()
    assert product_urls(src, f) == ["https://domus.am/product/teka", "https://domus.am/product/x-y"]
    assert "https://domus.am/sitemap-blog.xml" not in f.calls
    _sitemap_cache("domus_t").unlink(missing_ok=True)
