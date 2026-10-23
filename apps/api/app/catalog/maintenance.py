"""Scheduled catalogue upkeep (P1-7), run from the worker's maintenance loop:

* `catalog_index`  — background-indexed sources (VLV) get one index batch every
  `policy.index_interval_min` (30 min); a full pass refreshes prices and availability.
* `catalog_ttl`    — hourly: external records used in projects whose price TTL expired are
  re-checked (`source_refresh` job, live sources only) and the project owner is told once a
  day that selected prices are out of date (`price_stale`).
* `supplier_feeds` — supplier price feeds (official CSV/XLSX URL) are synced every
  `feed.interval_h`; the mass-price-change guard holds a suspicious feed for review.
* `evaluate_run()` — after every connector run: index batch result drop >50% against the recent median,
  parser break (pages without JSON-LD), open circuit / blocked source → `catalog_alert` to
  platform staff, at most once per source and reason a day.
Nothing here fetches anything unless EXTERNAL_FETCH_LIVE and the per-source opt-in are on."""
from __future__ import annotations

import logging
import statistics
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..config import get_settings
from ..scheduler import periodic

log = logging.getLogger("forma.catalog")
ALERT_COOLDOWN_H = 24
ALERT_REASONS = ("result_drop", "parser", "circuit", "blocked", "feed_guard", "feed_error")
_last: dict[str, float] = {}


def _aware(d: datetime | None) -> datetime | None:
    return d if d is None or d.tzinfo else d.replace(tzinfo=timezone.utc)


def _every(name: str, seconds: int) -> bool:
    import time

    if time.time() - _last.get(name, 0) < seconds:
        return False
    _last[name] = time.time()
    return True


# ------------------------------------------------------------------ alerts
def raise_alert(db: Session, source_name: str, reason: str, *, holder: dict, detail: str = "", link: str = "/app/admin") -> bool:
    """Record an alert in `holder` (a stats/feed dict, mutated) and notify platform staff, once a day per reason."""
    from ..notify import notify, platform_staff

    now = datetime.now(timezone.utc)
    last = (holder.get("alerts") or {}).get(reason)
    if last and now - datetime.fromisoformat(last) < timedelta(hours=ALERT_COOLDOWN_H):
        return False
    holder["alerts"] = {**(holder.get("alerts") or {}), reason: now.isoformat()}
    holder["alert_log"] = ([{"at": now.isoformat(), "reason": reason, "detail": detail[:200]}] + list(holder.get("alert_log") or []))[:20]
    notify(db, platform_staff(db), "catalog_alert", params={"source": source_name, "reason": reason}, link=link)
    log.warning("catalogue alert %s: %s %s", source_name, reason, detail[:200])
    return True


def evaluate_run(db: Session, source: m.ExternalSource, run: m.ExternalConnectorRun, counters: dict | None = None) -> list[str]:
    reasons: list[tuple[str, str]] = []
    # result drop is judged on index batches (same batch size each run); discovery runs differ per need and are not comparable
    prev = [] if run.kind != "index" else db.scalars(select(m.ExternalConnectorRun).where(m.ExternalConnectorRun.source_id == source.id, m.ExternalConnectorRun.kind == run.kind,
                                                          m.ExternalConnectorRun.id != run.id, m.ExternalConnectorRun.status == "ok")
                      .order_by(m.ExternalConnectorRun.created_at.desc()).limit(10)).all()
    if len(prev) >= 3:
        base = statistics.median(r.found for r in prev)
        if base >= 4 and run.found < 0.5 * base:
            reasons.append(("result_drop", f"{run.found} vs median {base:g}"))
    c = counters or {}
    missing = c.get("no_product", c.get("no_jsonld", 0))  # nothing extracted by any method (older runs: no JSON-LD)
    if c.get("fetched", 0) >= 5 and missing / c["fetched"] > 0.5:
        reasons.append(("parser", f"{missing}/{c['fetched']} pages without a recognisable product"))
    if any("circuit open" in str(e) for e in run.errors or []):
        reasons.append(("circuit", str(run.errors[0])[:200]))
    if run.status == "blocked":
        reasons.append(("blocked", str((run.errors or [""])[0])[:200]))
    stats = dict(source.stats or {})
    fired = [r for r, d in reasons if raise_alert(db, source.name, r, holder=stats, detail=d)]
    if fired:
        source.stats = stats
    return fired


# ------------------------------------------------------------------ scheduled index batches
def _active_job(db: Session, kind: str, key: str, value: str) -> bool:
    return any((j.params or {}).get(key) == value for j in db.scalars(select(m.GenerationJob).where(
        m.GenerationJob.kind == kind, m.GenerationJob.status.in_(("queued", "running")))))


def due_index_sources(db: Session, now: datetime | None = None) -> list[m.ExternalSource]:
    now = now or datetime.now(timezone.utc)
    out = []
    from .indexer import is_indexed

    for s in db.scalars(select(m.ExternalSource).where(m.ExternalSource.enabled.is_(True), m.ExternalSource.live_enabled.is_(True))):
        if not is_indexed(s):
            continue
        last = (s.stats or {}).get("index", {}).get("last_run_at")
        interval = int((s.policy or {}).get("index_interval_min", 30))
        if (not last or now - datetime.fromisoformat(last) >= timedelta(minutes=interval)) and not _active_job(db, "source_index", "source_id", s.id):
            out.append(s)
    return out


@periodic("catalog_index")
def scheduled_index(db: Session) -> bool:
    if not get_settings().external_fetch_live or not _every("catalog_index", 60):
        return False
    from ..jobs.runner import enqueue

    for s in due_index_sources(db):
        enqueue(db, "source_index", project_id=None, params={"source_id": s.id, "batch": int((s.policy or {}).get("index_batch", 60)), "scheduled": True})
    return True


# ------------------------------------------------------------------ price TTL
def _price_ttl_h(src: m.ExternalSource | None) -> float:
    return float(((src.ttl_h if src else None) or {}).get("price", get_settings().external_price_ttl_h))


def stale_refs_by_project(db: Session, now: datetime | None = None) -> dict[str, list[str]]:
    """Projects → external record ids in their current variant estimates whose price TTL expired."""
    now = now or datetime.now(timezone.utc)
    sources = {s.id: s for s in db.scalars(select(m.ExternalSource))}
    out: dict[str, set[str]] = {}
    rows = db.execute(select(m.DesignVariant.project_id, m.DesignVersion.estimate).join(m.DesignVersion, m.DesignVersion.id == m.DesignVariant.current_version_id)
                      .join(m.Project, m.Project.id == m.DesignVariant.project_id).where(m.Project.status != "archived", m.DesignVariant.status != "archived")).all()
    for pid, est in rows:
        for ln in (est or {}).get("lines", []):
            ref = ln.get("ref") or ""
            if not ref.startswith("ext:"):
                continue
            rec = db.get(m.ExternalProductRecord, ref[4:])
            if rec and (now - _aware(rec.retrieved_at)).total_seconds() / 3600 > _price_ttl_h(sources.get(rec.source_id)):
                out.setdefault(pid, set()).add(rec.id)
    return {k: sorted(v) for k, v in out.items()}


def notify_stale_prices(db: Session, stale: dict[str, list[str]], now: datetime | None = None) -> int:
    from ..notify import notify, project_people

    now = now or datetime.now(timezone.utc)
    sent = 0
    for pid, recs in stale.items():
        recent = db.scalar(select(m.Notification.id).where(m.Notification.project_id == pid, m.Notification.kind == "price_stale",
                                                           m.Notification.created_at > now - timedelta(hours=24)).limit(1))
        proj = db.get(m.Project, pid)
        if recent or not proj:
            continue
        sent += notify(db, project_people(db, proj), "price_stale", params={"n": len(recs), "project": proj.title}, link=f"/app/p/{pid}", project_id=pid)
    db.commit()
    return sent


@periodic("catalog_ttl")
def scheduled_ttl(db: Session) -> bool:
    if not _every("catalog_ttl", 3600):
        return False
    stale = stale_refs_by_project(db)
    if get_settings().external_fetch_live:
        from ..jobs.runner import enqueue

        by_source: dict[str, list[str]] = {}
        for rid in sorted({r for recs in stale.values() for r in recs}):
            rec = db.get(m.ExternalProductRecord, rid)
            by_source.setdefault(rec.source_id, []).append(rid)
        for sid, rids in by_source.items():
            src = db.get(m.ExternalSource, sid)
            if src and src.enabled and src.live_enabled and not _active_job(db, "source_refresh", "source_id", sid):
                enqueue(db, "source_refresh", project_id=None, params={"source_id": sid, "record_ids": rids[:int((src.policy or {}).get("refresh_batch", 30))]})
    notify_stale_prices(db, stale)
    return bool(stale)


def refresh_records(db: Session, source: m.ExternalSource, record_ids: list[str], fetcher=None) -> dict:
    """Re-fetch individual product pages (allowlist, robots, crawl-delay and breaker of SafeFetcher apply)."""
    import time

    from .connectors.others import build_connector
    from .discovery import source_dict, upsert_record
    from .extract import extract_product
    from .indexer import is_indexed
    from .net import FetchBlocked, SafeFetcher

    src = source_dict(source)
    live = get_settings().external_fetch_live and source.live_enabled and source.enabled
    t0 = time.time()
    run = m.ExternalConnectorRun(source_id=source.id, kind="refresh", status="running")
    db.add(run)
    db.flush()
    counters = {"fetched": 0, "refreshed": 0, "no_jsonld": 0, "errors": []}
    if live:
        fetcher = fetcher or SafeFetcher()
        conn = build_connector(src, live=True, cache_lookup=None, fetcher=fetcher)
        for rid in record_ids:
            rec = db.get(m.ExternalProductRecord, rid)
            if not rec or rec.source_id != source.id:
                continue
            try:
                if is_indexed(source):
                    html = fetcher.fetch(rec.canonical_url, src["allowed_hosts"], rate_limit_s=src.get("rate_limit_s", 3.0)).text
                    p, _ = extract_product(html, rec.canonical_url, src)
                else:
                    p = conn.refresh_product(rec.canonical_url)
            except FetchBlocked as e:
                counters["errors"].append(str(e)[:200])
                if "circuit" in str(e) or "budget" in str(e):
                    break
                continue
            counters["fetched"] += 1
            if p:
                upsert_record(db, p, existing=rec)
                counters["refreshed"] += 1
            else:
                counters["no_jsonld"] += 1
    run.status = "ok" if counters["refreshed"] else ("live_disabled" if not live else "empty")
    run.found, run.validated, run.errors = counters["fetched"], counters["refreshed"], counters["errors"][:20]
    run.latency_ms = int((time.time() - t0) * 1000)
    evaluate_run(db, source, run, counters)
    db.commit()
    return {k: v for k, v in counters.items() if k != "errors"} | {"status": run.status}


# ------------------------------------------------------------------ supplier feeds
FEED_DEFAULTS = {"enabled": False, "url": "", "interval_h": 24, "max_price_change_pct": 60.0, "mapping": None}


def feed_cfg(sup: m.Supplier) -> dict:
    return {**FEED_DEFAULTS, **(sup.feed or {})}


def due_feeds(db: Session, now: datetime | None = None) -> list[m.Supplier]:
    now = now or datetime.now(timezone.utc)
    out = []
    for sup in db.scalars(select(m.Supplier)):
        f = feed_cfg(sup)
        if not (f["enabled"] and f["url"]):
            continue
        last = f.get("last_sync_at")
        if (not last or now - datetime.fromisoformat(last) >= timedelta(hours=float(f["interval_h"]))) and not _active_job(db, "supplier_feed", "supplier_id", sup.id):
            out.append(sup)
    return out


@periodic("supplier_feeds")
def scheduled_feeds(db: Session) -> bool:
    if not get_settings().external_fetch_live or not _every("supplier_feeds", 600):
        return False
    from ..jobs.runner import enqueue

    for sup in due_feeds(db):
        enqueue(db, "supplier_feed", project_id=None, params={"supplier_id": sup.id})
    return True


def sync_feed(db: Session, sup: m.Supplier, fetcher=None) -> dict:
    """Fetch the supplier's feed and apply it through the guarded price-list import."""
    from urllib.parse import urlparse

    from .net import FetchBlocked, SafeFetcher
    from .pricelist import PriceGuard, _read_table, apply_price_list, guess_mapping

    f = feed_cfg(sup)
    now = datetime.now(timezone.utc)
    result: dict = {"status": "error"}
    if not get_settings().external_fetch_live:
        result = {"status": "live_disabled"}
    else:
        url = f["url"]
        host = (urlparse(url).hostname or "").lower()
        try:
            r = (fetcher or SafeFetcher()).fetch(url, [host], max_bytes=20_000_000)
            if r.status_code != 200:
                raise FetchBlocked(f"HTTP {r.status_code}")
            name = urlparse(url).path.rsplit("/", 1)[-1] or "feed.csv"
            if "spreadsheetml" in r.headers.get("content-type", "") and not name.lower().endswith((".xlsx", ".xlsm")):
                name += ".xlsx"
            rows = _read_table(r.content, name)
            if not rows:
                raise ValueError("empty feed")
            mapping = f["mapping"] or guess_mapping(list(rows[0].keys()))
            result = {"status": "ok", **apply_price_list(db, sup, rows, mapping, float(f["max_price_change_pct"]), source="feed")}
            result["errors"] = result["errors"][:20]
        except PriceGuard as e:
            result = {"status": "guard_blocked", "count": e.count, "total": e.total, "pct": e.pct}
            raise_alert(db, sup.name, "feed_guard", holder=f, detail=str(e))
        except (FetchBlocked, ValueError, KeyError) as e:
            result = {"status": "error", "error": str(e)[:200]}
            raise_alert(db, sup.name, "feed_error", holder=f, detail=str(e))
    f["last_sync_at"] = now.isoformat()
    f["last_status"] = result["status"]
    f["history"] = ([{"at": now.isoformat(), **{k: v for k, v in result.items() if k != "errors"}}] + list(f.get("history") or []))[:20]
    sup.feed = f
    db.add(m.AuditEvent(action="supplier.feed_sync", entity="supplier", entity_id=sup.id, data={k: v for k, v in result.items() if k != "errors"}))
    db.commit()
    return result


@periodic("search_index")
def scheduled_search_index(db: Session) -> bool:
    """Every 6 h: incremental re-embedding (only changed product texts are embedded again)."""
    if not _every("search_index", 6 * 3600):
        return False
    if db.scalar(select(m.GenerationJob.id).where(m.GenerationJob.kind == "search_index", m.GenerationJob.status.in_(("queued", "running"))).limit(1)):
        return False
    from ..jobs.runner import enqueue

    enqueue(db, "search_index", project_id=None, params={})
    return True
