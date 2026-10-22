"""Background index crawler for sources whose catalogue pages are script-rendered
behind robots-disallowed endpoints (audit 2026-10-22: VLV). It walks the product
URLs of the audited sitemap in batches, at the site's crawl-delay, parses schema.org
Product JSON-LD and keeps only items that map to an interior category. A cursor in
`source.stats.index` makes runs resumable; a full pass restarts from the beginning,
which refreshes prices and availability."""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from .. import models as m
from ..config import get_settings
from .connectors.jsonld import LOC_RE, parse_product_page
from .discovery import source_dict, upsert_record
from .net import FetchBlocked, SafeFetcher
from .normalize import is_accessory

SITEMAP_CACHE_TTL_H = 24


def _sitemap_cache(source_key: str) -> Path:
    return get_settings().storage_dir / "cache" / "sitemaps" / f"{source_key}.xml"


def product_urls(src: dict, fetcher: SafeFetcher) -> list[str]:
    """Product URLs from the audited sitemap(s), cached on disk for 24 h (large sitemaps are fetched once a day)."""
    pol = src.get("policy", {})
    pattern = re.compile(pol.get("product_url_regex", r"/product/"), re.I)
    cache = _sitemap_cache(src["key"])
    if cache.exists() and time.time() - cache.stat().st_mtime < SITEMAP_CACHE_TTL_H * 3600:
        xml = cache.read_text(encoding="utf-8")
    else:
        parts = [fetcher.fetch(sm, src["allowed_hosts"], rate_limit_s=src.get("rate_limit_s", 3.0), max_bytes=pol.get("max_bytes")).text
                 for sm in pol.get("sitemaps", [])]
        xml = "\n".join(parts)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(xml, encoding="utf-8")
    return list(dict.fromkeys(u for u in LOC_RE.findall(xml) if pattern.search(u)))


def crawl_batch(db: Session, source: m.ExternalSource, *, batch: int = 60, fetcher: SafeFetcher | None = None,
                deadline_s: float | None = None) -> dict:
    """Index up to `batch` product pages from the cursor. Never exceeds the fetcher budget or `deadline_s`."""
    src = source_dict(source)
    if not (get_settings().external_fetch_live and source.live_enabled and source.enabled):
        return {"status": "live_disabled", "fetched": 0, "indexed": 0}
    fetcher = fetcher or SafeFetcher()
    t0 = time.time()
    counters = {"fetched": 0, "indexed": 0, "irrelevant": 0, "accessories": 0, "no_jsonld": 0, "blocked": 0, "errors": []}
    run = m.ExternalConnectorRun(source_id=source.id, kind="index", status="running")
    db.add(run)
    db.flush()
    try:
        urls = product_urls(src, fetcher)
    except FetchBlocked as e:
        run.status, run.errors = "blocked", [str(e)[:300]]
        source.health_status = "blocked"
        from .maintenance import evaluate_run

        evaluate_run(db, source, run)
        db.commit()
        return {**counters, "status": "blocked", "error": str(e)[:300]}
    stats = dict(source.stats or {})
    idx = dict(stats.get("index", {}))
    cursor = idx.get("cursor", 0)
    if cursor >= len(urls):  # full pass done → start a refresh pass
        cursor, idx["passes"] = 0, idx.get("passes", 0) + 1
    end = min(len(urls), cursor + batch)
    while cursor < end:
        if deadline_s is not None and time.time() - t0 > deadline_s:
            break
        url = urls[cursor]
        try:
            html = fetcher.fetch(url, src["allowed_hosts"], rate_limit_s=src.get("rate_limit_s", 3.0)).text
        except FetchBlocked as e:
            counters["blocked"] += 1
            counters["errors"].append(f"{url}: {str(e)[:120]}")
            if "budget" in str(e) or "circuit" in str(e):
                break
            cursor += 1
            continue
        cursor += 1
        counters["fetched"] += 1
        p = parse_product_page(html, url, src, "jsonld-index-1.0")
        if not p:
            counters["no_jsonld"] += 1
        elif is_accessory(p.name, p.category):
            counters["accessories"] += 1
        elif not p.normalized_category:
            counters["irrelevant"] += 1  # electronics, cookware, tyres… — not an interior product
        else:
            upsert_record(db, p)
            counters["indexed"] += 1
    total_indexed = db.query(m.ExternalProductRecord).filter(m.ExternalProductRecord.source_id == source.id).count()
    idx.update({"cursor": cursor, "total": len(urls), "indexed": total_indexed, "last_run_at": datetime.now(timezone.utc).isoformat(),
                "last_batch": {k: v for k, v in counters.items() if k != "errors"}})
    stats["index"] = idx
    source.stats = stats
    source.last_success_at = datetime.now(timezone.utc) if counters["fetched"] else source.last_success_at
    source.health_status = "ok" if counters["fetched"] and counters["no_jsonld"] < max(3, counters["fetched"] // 2) else "degraded"
    run.status = "ok" if counters["fetched"] else "empty"
    run.found = counters["fetched"]
    run.validated = counters["indexed"]
    run.errors = counters["errors"][:20]
    run.latency_ms = int((time.time() - t0) * 1000)
    db.commit()
    return {**counters, "status": run.status, "cursor": cursor, "total": len(urls), "indexed_total": total_indexed,
            "next_run_after": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()}
