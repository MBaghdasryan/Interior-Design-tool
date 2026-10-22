"""P1-7: scheduled catalogue upkeep — alerts (result drop, parser break, circuit), due index
batches, price TTL → refresh + `price_stale`, supplier feed sync with the mass-change guard,
connector history for admins. No network: fake fetchers."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app import models as m
from app.catalog import maintenance as mt
from app.catalog.net import FetchBlocked
from app.config import get_settings
from app.db import SessionLocal

pytestmark = pytest.mark.usefixtures("client")
VLV_HTML = (Path(__file__).parent / "fixtures" / "vlv_product.html").read_text(encoding="utf-8")


@pytest.fixture(autouse=True, scope="module")
def _cleanup():
    yield
    with SessionLocal() as db:  # test-only sources/suppliers must not leak into seed/count tests
        for s in db.scalars(select(m.ExternalSource).where(m.ExternalSource.key.like("t\\_%", escape="\\"))):
            db.query(m.ExternalProductRecord).filter_by(source_id=s.id).delete()
            db.query(m.ExternalConnectorRun).filter_by(source_id=s.id).delete()
            db.delete(s)
        db.commit()


def _source(db, key: str) -> m.ExternalSource:
    s = db.scalar(select(m.ExternalSource).where(m.ExternalSource.key == key))
    if s:
        db.query(m.ExternalConnectorRun).filter_by(source_id=s.id).delete()
        s.stats = {}
    else:
        vlv = db.scalar(select(m.ExternalSource).where(m.ExternalSource.key == "vlv"))
        s = m.ExternalSource(key=key, name=f"Test {key}", domain=vlv.domain, canonical_domain=f"{key}.test", connector_type="jsonld_index", method="jsonld_index",
                             live_enabled=True, enabled=True, policy_status="approved", allowed_hosts=vlv.allowed_hosts, policy=dict(vlv.policy), rate_limit_s=3.0,
                             ttl_h={"price": 24}, categories=vlv.categories)
        db.add(s)
    db.commit()
    return s


def _alerts(db):
    admin = db.scalar(select(m.User).where(m.User.email == "admin@forma.local"))
    return db.scalars(select(m.Notification).where(m.Notification.user_id == admin.id, m.Notification.kind == "catalog_alert")).all()


def test_alerts_result_drop_parser_circuit_with_cooldown():
    with SessionLocal() as db:
        db.query(m.Notification).filter_by(kind="catalog_alert").delete()
        src = _source(db, "t_alerts")
        for _ in range(4):
            db.add(m.ExternalConnectorRun(source_id=src.id, kind="index", status="ok", found=60))
        db.flush()
        run = m.ExternalConnectorRun(source_id=src.id, kind="index", status="ok", found=12, errors=["https://x: circuit open for vlv.am"])
        db.add(run)
        db.flush()
        fired = mt.evaluate_run(db, src, run, {"fetched": 12, "no_jsonld": 9})
        db.commit()
        assert set(fired) == {"result_drop", "parser", "circuit"}
        a = _alerts(db)
        assert {n.params["reason"] for n in a} == {"result_drop", "parser", "circuit"} and all(n.params["source"] == "Test t_alerts" for n in a)
        assert len(db.get(m.ExternalSource, src.id).stats["alert_log"]) == 3
        assert mt.evaluate_run(db, src, run, {"fetched": 12, "no_jsonld": 9}) == []  # cooldown: once a day per reason
        ok = m.ExternalConnectorRun(source_id=src.id, kind="index", status="ok", found=58)
        db.add(ok)
        db.flush()
        assert mt.evaluate_run(db, src, ok, {"fetched": 58, "no_jsonld": 1}) == []
        db.commit()


def test_due_index_sources_respects_interval_and_running_jobs():
    with SessionLocal() as db:
        src = _source(db, "t_index")
        now = datetime.now(timezone.utc)
        assert src.id in [s.id for s in mt.due_index_sources(db, now)]
        src.stats = {"index": {"last_run_at": (now - timedelta(minutes=10)).isoformat()}}
        db.commit()
        assert src.id not in [s.id for s in mt.due_index_sources(db, now)]
        assert src.id in [s.id for s in mt.due_index_sources(db, now + timedelta(minutes=25))]
        job = m.GenerationJob(kind="source_index", params={"source_id": src.id}, status="running")
        db.add(job)
        db.commit()
        assert src.id not in [s.id for s in mt.due_index_sources(db, now + timedelta(minutes=25))]
        db.delete(job)
        db.commit()


class Fetcher:
    def __init__(self, pages: dict, headers=None):
        self.pages, self.calls, self.headers = pages, [], headers or {}

    def fetch(self, url, allowed_hosts, rate_limit_s=None, max_bytes=None, **_):
        self.calls.append((url, tuple(allowed_hosts)))
        if url not in self.pages:
            raise FetchBlocked("404")
        body = self.pages[url]
        return type("R", (), {"text": body if isinstance(body, str) else body.decode(), "content": body.encode() if isinstance(body, str) else body,
                              "status_code": 200, "headers": self.headers})()


def test_stale_prices_notify_once_and_refresh(monkeypatch):
    url = "https://vlv.am/Product/36469"
    with SessionLocal() as db:
        src = _source(db, "t_ttl")
        old = datetime.now(timezone.utc) - timedelta(hours=50)
        rec = db.scalar(select(m.ExternalProductRecord).where(m.ExternalProductRecord.source_id == src.id))
        if not rec:
            rec = m.ExternalProductRecord(source_id=src.id, external_key="ttl-1", canonical_url=url, data={}, price_amd=100.0, retrieved_at=old)
            db.add(rec)
        rec.retrieved_at = old
        proj = db.query(m.Project).filter(m.Project.title.like("Демо%")).first()
        v = m.DesignVariant(project_id=proj.id, key="ttl", title="TTL", style="modern", tier="comfort")
        db.add(v)
        db.flush()
        ver = m.DesignVersion(variant_id=v.id, number=1, scene={}, estimate={"lines": [{"ref": f"ext:{rec.id}"}, {"ref": "pv:x"}]})
        db.add(ver)
        db.flush()
        v.current_version_id = ver.id
        db.query(m.Notification).filter_by(kind="price_stale").delete()
        db.commit()
        stale = mt.stale_refs_by_project(db)
        assert rec.id in stale[proj.id]
        assert mt.notify_stale_prices(db, stale) >= 1
        n = db.scalar(select(m.Notification).where(m.Notification.kind == "price_stale", m.Notification.project_id == proj.id))
        assert n.params["n"] >= 1 and n.link == f"/app/p/{proj.id}"
        assert mt.notify_stale_prices(db, stale) == 0  # once a day per project

        r = mt.refresh_records(db, src, [rec.id], fetcher=Fetcher({url: VLV_HTML}))
        assert r["status"] == "live_disabled" and r["fetched"] == 0  # EXTERNAL_FETCH_LIVE=false → nothing fetched
        monkeypatch.setattr(get_settings(), "external_fetch_live", True)
        f = Fetcher({url: VLV_HTML})
        r = mt.refresh_records(db, src, [rec.id], fetcher=f)
        assert r["status"] == "ok" and r["refreshed"] == 1 and f.calls[0][1] == tuple(src.allowed_hosts)
        assert proj.id not in mt.stale_refs_by_project(db) or rec.id not in mt.stale_refs_by_project(db).get(proj.id, [])
        db.delete(v)
        db.commit()


CSV1 = "sku;name;category;price;stock\nF-1;Плитка напольная Тест;floor_tile;10000;да\nF-2;Смеситель Тест;faucet;20000;да\n"
CSV_BAD = "sku;name;category;price;stock\nF-1;Плитка напольная Тест;floor_tile;90000;да\nF-2;Смеситель Тест;faucet;80000;да\n"


def test_supplier_feed_sync_guard_and_errors(monkeypatch):
    feed = "https://feeds.example.com/price.csv"
    with SessionLocal() as db:
        sup = m.Supplier(name="Feed Test", slug="feed-test", feed={"enabled": True, "url": feed, "interval_h": 24})
        db.add(sup)
        db.query(m.Notification).filter_by(kind="catalog_alert").delete()
        db.commit()
        assert mt.sync_feed(db, sup, fetcher=Fetcher({feed: CSV1}))["status"] == "live_disabled"
        monkeypatch.setattr(get_settings(), "external_fetch_live", True)
        assert sup.id in [s.id for s in mt.due_feeds(db, datetime.now(timezone.utc) + timedelta(hours=25))]
        f = Fetcher({feed: CSV1})
        r = mt.sync_feed(db, sup, fetcher=f)
        assert r["status"] == "ok" and r["created"] == 2 and f.calls[0][1] == ("feeds.example.com",)  # only the feed host is allowed
        assert sup.id not in [s.id for s in mt.due_feeds(db)]  # just synced
        r = mt.sync_feed(db, sup, fetcher=Fetcher({feed: CSV_BAD}))
        assert r["status"] == "guard_blocked" and r["count"] == 2
        prices = sorted(v.price for v in db.scalars(select(m.ProductVariant).join(m.Product).where(m.Product.supplier_id == sup.id)))
        assert prices == [10000, 20000]  # nothing applied
        assert [n.params["reason"] for n in _alerts(db)] == ["feed_guard"]
        assert mt.sync_feed(db, sup, fetcher=Fetcher({}))["status"] == "error"
        assert {n.params["reason"] for n in _alerts(db)} == {"feed_guard", "feed_error"}
        assert [h["status"] for h in sup.feed["history"]][:3] == ["error", "guard_blocked", "ok"]


def test_feed_settings_api_and_admin_history(client, admin):
    from tests.conftest import login

    sh = login(client, "supplier@forma.local")
    assert client.get("/api/v1/supplier/feed", headers=sh).json()["enabled"] is False
    assert client.put("/api/v1/supplier/feed", headers=sh, json={"enabled": True, "url": "http://insecure.example.com/x.csv"}).status_code == 422
    r = client.put("/api/v1/supplier/feed", headers=sh, json={"enabled": True, "url": "https://feeds.example.com/p.csv", "interval_h": 12})
    assert r.status_code == 200 and r.json()["interval_h"] == 12
    assert client.put("/api/v1/supplier/feed", headers=sh, json={"interval_h": 1}).status_code == 422
    assert client.get("/api/v1/supplier/feed", headers=login(client)).status_code == 403  # designer has no supplier:manage
    client.put("/api/v1/supplier/feed", headers=sh, json={"enabled": False, "url": ""})
    with SessionLocal() as db:
        sid = _source(db, "t_hist").id
        db.add(m.ExternalConnectorRun(source_id=sid, kind="index", status="ok", found=5))
        db.commit()
    h = client.get(f"/api/v1/admin/sources/{sid}/history", headers=admin).json()
    assert h["runs"][0]["found"] == 5 and h["schedule"]["index_interval_min"] == 30
    assert client.get(f"/api/v1/admin/sources/{sid}/history", headers=sh).status_code == 403
