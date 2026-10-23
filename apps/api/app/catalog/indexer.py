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
from .connectors.jsonld import LOC_RE
from .discovery import source_dict, upsert_record
from .extract import detect_restriction, extract_product
from .net import FetchBlocked, SafeFetcher
from .normalize import is_accessory

SITEMAP_CACHE_TTL_H = 24


def is_indexed(source: m.ExternalSource) -> bool:
    """Background-indexed sources: script-rendered stores (VLV) and full-catalogue indexing of sitemap stores (Domus)."""
    return source.connector_type == "jsonld_index" or bool((source.policy or {}).get("background_index"))


def _sitemap_cache(source_key: str) -> Path:
    return get_settings().storage_dir / "cache" / "sitemaps" / f"{source_key}.xml"


# common product URL shapes (Shopify/Woo/Wix/OpenCart/Bitrix/custom), used when a source has no audited regex
AUTO_PRODUCT_RE = r"/(?:product|products|product-page|p|item|items|tovar|goods|shop)/[^/?#]+/?$|route=product/product&|[?&]product_id=\d+"


def _sitemaps(src: dict, fetcher: SafeFetcher) -> list[str]:
    """Audited sitemaps from the policy; otherwise the `Sitemap:` lines of robots.txt, then /sitemap.xml."""
    pol = src.get("policy", {})
    if pol.get("sitemaps"):
        return pol["sitemaps"]
    found = fetcher.robots_sitemaps(src["domain"])
    return found or [src["domain"].rstrip("/") + "/sitemap.xml"]


PRODUCT_SITEMAP_RE = re.compile(r"products?|goods|tovar|items?|apranq", re.I)  # tested on the name without the word «sitemap»
SITEMAP_MAX_BYTES = 50_000_000  # the sitemap protocol limit (pages keep the 5 MB fetch limit)
NON_PRODUCT_SITEMAP_RE = re.compile(r"categor|manufactur|brand|information|page-sitemap|pages|blog|news|post|tag|author|video|image", re.I)
NON_PRODUCT_PAGE_RE = re.compile(r"/(about|contact|delivery|shipping|payment|faq|blog|news|sales|brands?|manufacturers?|privacy|terms|cart|checkout|account|login|search|tag|author|page)(/|\.html?|$)", re.I)


def _expand(src: dict, fetcher: SafeFetcher, text: str) -> list[tuple[str, str]]:
    """→ [(sitemap url or '', xml)]. A sitemap of sitemaps — standard <sitemapindex>, or (Domus) a <urlset>
    whose entries are sitemap pages — is followed one level; child sitemaps that are clearly not about
    products (categories, brands, information pages, blog) are skipped."""
    pol = src.get("policy", {})
    if pol.get("child_sitemap_regex"):
        children = [c for c in LOC_RE.findall(text) if re.search(pol["child_sitemap_regex"], c, re.I)]
    elif "<sitemapindex" in text:
        children = [c for c in LOC_RE.findall(text) if not NON_PRODUCT_SITEMAP_RE.search(c.rsplit("/", 1)[-1])]
    else:
        return [("", text)]
    out = []
    for child in children[: pol.get("max_child_sitemaps", 200)]:
        try:
            out.append((child, fetcher.fetch(child, src["allowed_hosts"], rate_limit_s=src.get("rate_limit_s", 3.0), max_bytes=pol.get("max_bytes") or SITEMAP_MAX_BYTES).text))
        except FetchBlocked:
            continue
    return out or [("", text)]


def _leaf_urls(urls: list[str]) -> list[str]:
    """Product pages are leaves of the catalogue tree: a URL that is the prefix of another one is a category."""
    clean = [u for u in dict.fromkeys(urls) if not NON_PRODUCT_PAGE_RE.search(u)]
    norm = sorted((u.rstrip("/"), u) for u in clean)
    leaves = []
    for i, (n, u) in enumerate(norm):
        nxt = norm[i + 1][0] if i + 1 < len(norm) else ""
        if not nxt.startswith(n + "/") and n.count("/") >= 4:  # scheme://host/a/b at least — skip the home and top sections
            leaves.append(u)
    return leaves


def crawl_links(src: dict, fetcher: SafeFetcher, pattern: re.Pattern, *, max_pages: int = 30) -> list[str]:
    """No usable sitemap: breadth-first walk of the site's own pages (home + configured catalogue URLs),
    collecting links that look like product pages. Bounded by `max_pages`; robots and rate limits apply."""
    from urllib.parse import urljoin, urlparse

    pol = src.get("policy", {})
    hosts = set(src["allowed_hosts"])
    queue = list(dict.fromkeys([*pol.get("catalog_urls", []), src["domain"]]))
    seen, products = set(), []
    while queue and len(seen) < max_pages:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            html = fetcher.fetch(url, src["allowed_hosts"], rate_limit_s=src.get("rate_limit_s", 3.0)).text
        except FetchBlocked:
            continue
        for href in re.findall(r'href="([^"#]+)"', html):
            link = urljoin(url, href.replace("&amp;", "&"))
            if (urlparse(link).hostname or "").lower() not in hosts or link.startswith(("mailto:", "tel:")):
                continue
            if pattern.search(link):
                products.append(link)
            elif re.search(r"categor|catalog|collection|shop|products|page=|/c/|bazhin|razdel", link, re.I) and link not in seen:
                queue.append(link)
    return list(dict.fromkeys(products))


def product_urls(src: dict, fetcher: SafeFetcher) -> list[str]:
    """Product URLs, cached on disk for 24 h (large sitemaps are fetched once a day):
    1. audited policy (sitemaps + product_url_regex) — Domus, VLV;
    2. otherwise sitemaps from robots.txt or /sitemap.xml: child sitemaps named «product…» are trusted
       as a whole (OpenCart, WooCommerce, Shopify); else URLs matching common product URL shapes; else the
       leaves of the catalogue tree (Bitrix-style /catalog/section/item/);
    3. no sitemap at all: a bounded crawl of the site's own pages."""
    pol = src.get("policy", {})
    audited = bool(pol.get("product_url_regex"))
    pattern = re.compile(pol.get("product_url_regex") or AUTO_PRODUCT_RE, re.I)
    cache = _sitemap_cache(src["key"])
    if cache.exists() and time.time() - cache.stat().st_mtime < SITEMAP_CACHE_TTL_H * 3600:
        cached = LOC_RE.findall(cache.read_text(encoding="utf-8"))
        return list(dict.fromkeys(u for u in cached if pattern.search(u))) if audited else cached
    parts: list[tuple[str, str]] = []
    for sm in _sitemaps(src, fetcher):
        try:
            text = fetcher.fetch(sm, src["allowed_hosts"], rate_limit_s=src.get("rate_limit_s", 3.0), max_bytes=pol.get("max_bytes") or SITEMAP_MAX_BYTES).text
        except FetchBlocked:
            if pol.get("sitemaps"):
                raise  # an audited sitemap that fails is an error, not a reason to crawl
            continue
        parts += _expand(src, fetcher, text)
    all_urls = list(dict.fromkeys(u for _, x in parts for u in LOC_RE.findall(x)))
    if audited or pol.get("sitemaps") and any(pattern.search(u) for u in all_urls):
        urls = [u for u in all_urls if pattern.search(u)]
    else:
        trusted = [u for name, x in parts if name and PRODUCT_SITEMAP_RE.search(name.rsplit("/", 1)[-1].lower().replace("sitemap", "")) for u in LOC_RE.findall(x)]
        urls = (list(dict.fromkeys(trusted)) or [u for u in all_urls if pattern.search(u)] or _leaf_urls(all_urls)
                or crawl_links(src, fetcher, pattern, max_pages=int(pol.get("crawl_max_pages", 30))))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text("\n".join(f"<loc>{u}</loc>" for u in urls), encoding="utf-8")
    return urls


def crawl_batch(db: Session, source: m.ExternalSource, *, batch: int = 60, fetcher: SafeFetcher | None = None,
                deadline_s: float | None = None) -> dict:
    """Index up to `batch` product pages from the cursor. Never exceeds the fetcher budget or `deadline_s`."""
    src = source_dict(source)
    if not (get_settings().external_fetch_live and source.live_enabled and source.enabled and is_indexed(source)):
        return {"status": "live_disabled", "fetched": 0, "indexed": 0}
    fetcher = fetcher or SafeFetcher()
    t0 = time.time()
    counters = {"fetched": 0, "indexed": 0, "irrelevant": 0, "accessories": 0, "no_jsonld": 0, "no_product": 0, "blocked": 0, "methods": {}, "errors": []}
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
        restricted = detect_restriction(html)
        if restricted:  # CAPTCHA / anti-bot page: reported, never bypassed
            counters["blocked"] += 1
            counters["errors"].append(f"{url}: {restricted} — not bypassing")
            break
        p, method = extract_product(html, url, src)
        if method != "jsonld":
            counters["no_jsonld"] += 1
        if method:
            counters["methods"][method] = counters["methods"].get(method, 0) + 1
        if not p:
            counters["no_product"] += 1
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
    source.health_status = ("blocked" if counters["blocked"] and not counters["fetched"] else
                            "ok" if counters["fetched"] and counters["no_product"] < max(3, counters["fetched"] // 2) else "degraded")
    run.status = "ok" if counters["fetched"] else "empty"
    run.found = counters["fetched"]
    run.validated = counters["indexed"]
    run.errors = counters["errors"][:20]
    run.latency_ms = int((time.time() - t0) * 1000)
    db.commit()
    return {**counters, "status": run.status, "cursor": cursor, "total": len(urls), "indexed_total": total_indexed,
            "next_run_after": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()}
