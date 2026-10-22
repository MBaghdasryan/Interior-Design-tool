"""Units, prices and connector safety (addon prompt §16)."""
from pathlib import Path

import httpx
import pytest

from app.catalog.connectors.jsonld import parse_product_page
from app.catalog.net import FetchBlocked, SafeFetcher, assert_public_host, host_allowed
from app.catalog.normalize import detect_unit, fingerprint, normalize_availability, parse_dimensions, parse_package_coverage, parse_price, to_amd, validate
from app.estimate.estimator import material_purchase

FIX = Path(__file__).parent / "fixtures"
SOURCE = {"id": "src1", "key": "domus", "allowed_hosts": ["domus.am"], "rate_limit_s": 0}


@pytest.mark.parametrize("raw,val,cur", [
    ("2 790 ֏", 2790, "AMD"), ("1,240,000 AMD", 1240000, "AMD"), ("1.240.000 драм", 1240000, "AMD"), ("$1,299.50", 1299.5, "USD"),
    ("1299,50 €", 1299.5, "EUR"), ("85000", 85000, None), (12000, 12000, None), ("Цена по запросу", None, None),
])
def test_parse_price(raw, val, cur):
    v, c = parse_price(raw)
    assert v == val and c == cur


def test_currency_never_mixed_without_rate():
    assert to_amd(100, "USD") == 38700
    assert to_amd(100, None) is None
    assert to_amd(100, "GBP") is None


@pytest.mark.parametrize("text,unit", [("Керамогранит 60×60, цена за м²", "m2"), ("Плитка 1.44 м² в упак, цена за упак.", "pack"),
                                       ("Клей 25 кг, цена за кг", "kg"), ("Կերամոգրանիտ, գինը 1 քմ", "m2"), ("Диван", "pcs")])
def test_units(text, unit):
    assert detect_unit(text) == unit


def test_dimensions_and_package():
    assert parse_dimensions("Плитка 60x120 см")["tile_w_mm"] == 600
    d = parse_dimensions("Диван 2600×980×820 мм")
    assert (d["width_mm"], d["depth_mm"], d["height_mm"]) == (2600, 980, 820)
    assert parse_dimensions("лампа кругла 223/210մմ")["diameter_mm"] == 223
    assert parse_package_coverage("1,44 м² в упаковке") == 1.44
    assert parse_dimensions("без размеров") == {}


def test_purchase_quantity_formula():
    # Q = ceil(A·(1+w)/A_pkg): 21.4 m² · 1.1 / 1.44 = 16.35 → 17 packs
    gross, packs = material_purchase(21.4, 0.10, 1.44)
    assert packs == 17 and round(gross, 2) == 23.54
    assert material_purchase(10, 0.1, None)[1] is None


def test_availability_mapping():
    assert normalize_availability("https://schema.org/InStock") == "in_stock"
    assert normalize_availability("PreOrder") == "to_order"
    assert normalize_availability(None) == "unknown"
    assert normalize_availability("whatever") == "unknown"


def test_domus_jsonld_fixture():
    html = (FIX / "domus_product.html").read_text()
    p = parse_product_page(html, "https://domus.am/product/ER-00052270", SOURCE, "jsonld-test")
    assert p.sku == "ER-00052270" and p.brand == "Vallight"
    assert p.price_value == 2790 and p.original_currency == "AMD" and p.price_amd == 2790
    assert p.normalized_category == "spot_light"
    assert p.dimensions.diameter_mm == 223
    assert p.delivery == {"days_min": 1, "days_max": 6, "country": "AM"}
    # logo is not accepted as a product photo; template review is ignored
    assert p.main_image_url is None
    assert any("логотип" in w for w in p.validation_warnings)
    # markup-only stock claim is flagged
    assert any("разметке" in w for w in p.validation_warnings)
    assert {pv.field for pv in p.provenance} >= {"name", "sku", "price", "currency"}


def test_validation_flags_missing_and_disputed():
    html = (FIX / "domus_product.html").read_text().replace('"price":"2790",', "")
    p = parse_product_page(html, "https://domus.am/product/X", SOURCE, "t")
    assert p.quote_required and p.price_amd is None
    p.old_price, p.price_value = 1000, 2000
    p = validate(p)
    assert "old_price" in p.disputed_fields and p.manual_confirmation_required


def test_fingerprint_stable():
    assert fingerprint("domus", "Brand", "Model", "white") == fingerprint("domus", " brand ", "model", "WHITE")


# ---------------------------------------------------------------- network safety
def test_allowlist():
    assert host_allowed("https://domus.am/product/1", ["domus.am"])
    assert host_allowed("https://www.domus.am/x", ["domus.am"])
    assert not host_allowed("https://domus.am.evil.com/x", ["domus.am"])
    assert not host_allowed("ftp://domus.am/x", ["domus.am"])
    assert not host_allowed("http://169.254.169.254/latest", ["domus.am"])


def test_ssrf_private_ip_blocked():
    def fake(host, _):
        return [(None, None, None, None, ("127.0.0.1", 0))]

    with pytest.raises(FetchBlocked):
        assert_public_host("https://domus.am/", resolver=fake)


def _fetcher(handler, sleeps=None):
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    return SafeFetcher(client=client, resolver=lambda h, _: [(None, None, None, None, ("93.184.216.34", 0))], sleep=(sleeps.append if sleeps is not None else (lambda s: None)))


def test_redirect_to_foreign_host_blocked():
    def handler(req: httpx.Request):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(302, headers={"location": "https://evil.example/steal"})

    f = _fetcher(handler)
    with pytest.raises(FetchBlocked, match="allowlist"):
        f.fetch("https://domus.am/product/1", ["domus.am"], rate_limit_s=0)


def test_robots_disallow_respected():
    def handler(req: httpx.Request):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /search\n")
        return httpx.Response(200, text="ok")

    f = _fetcher(handler)
    with pytest.raises(FetchBlocked, match="robots"):
        f.fetch("https://domus.am/search?q=sofa", ["domus.am"], rate_limit_s=0)
    assert f.fetch("https://domus.am/product/1", ["domus.am"], rate_limit_s=0).text == "ok"


def test_access_denied_not_bypassed():
    def handler(req: httpx.Request):
        return httpx.Response(404) if req.url.path == "/robots.txt" else httpx.Response(403)

    with pytest.raises(FetchBlocked, match="not bypassing"):
        _fetcher(handler).fetch("https://domus.am/p", ["domus.am"], rate_limit_s=0)


def test_rate_limit_waits():
    sleeps: list[float] = []

    def handler(req):
        return httpx.Response(404) if req.url.path == "/robots.txt" else httpx.Response(200, text="x")

    f = _fetcher(handler, sleeps)
    f.fetch("https://domus.am/a", ["domus.am"], rate_limit_s=3)
    f.fetch("https://domus.am/b", ["domus.am"], rate_limit_s=3)
    assert sleeps and sleeps[-1] > 2.5


def test_accessories_are_not_products():
    from app.catalog.normalize import is_accessory

    assert is_accessory("Lumos CV-SGN-R80DR Կափարիչ լուսատուի")
    assert not is_accessory("Lumos SDN-R80FA Լուսատու աստիճանավանդակի")


def test_content_type_and_size_limits():
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, content=b"\x00" * 10, headers={"content-type": "application/octet-stream"})

    with pytest.raises(FetchBlocked, match="content-type"):
        _fetcher(handler).fetch("https://domus.am/x", ["domus.am"], rate_limit_s=0)


def test_source_seed_is_idempotent_and_domus_only_live(client):
    from app.db import SessionLocal
    from app.models import ExternalSource
    from app.seed import seed_external_sources

    with SessionLocal() as db:
        seed_external_sources(db)
        db.commit()
        again = seed_external_sources(db)
        db.commit()
        rows = db.query(ExternalSource).all()
        assert len(rows) == 8 and all(r["action"] == "unchanged" for r in again)
        assert len({r.canonical_domain for r in rows}) == 8
        # live: Domus (per-need discovery) and VLV (background index only, audit 2026-10-22)
        assert sorted(r.key for r in rows if r.live_enabled) == ["domus", "vlv"]
        assert next(r for r in rows if r.key == "vlv").connector_type == "jsonld_index"
        assert next(r for r in rows if r.key == "profal").connector_type == "rfq"
        assert {r.key for r in rows if not r.enabled} == {"idealsystem", "nortun", "effectgroup", "lideria", "vega"}


def test_category_exclusions_from_live_findings():
    from app.catalog.normalize import classify, is_accessory

    assert classify("Teka Sommelier RVU 10020 GBK Գինու սառնարան") is None
    assert classify("Samsung RB34 սառնարան") == "fridge"
    assert is_accessory("Էկրան լոգնոցի Медея")
    assert classify("Lav Բաժակ պաղպաղակի ապակյա Destina") is None
