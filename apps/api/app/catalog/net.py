"""Safe outbound fetching for external catalog discovery:
allowlist, SSRF protection, redirect validation, robots.txt, per-domain rate
limit, exponential backoff and a circuit breaker. No CAPTCHA/anti-bot bypass —
a blocked source is reported, never worked around."""
from __future__ import annotations

import ipaddress
import socket
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from ..config import get_settings


class FetchBlocked(Exception):
    """Raised when policy forbids a request (allowlist, robots, SSRF, breaker)."""


def host_allowed(url: str, allowed_hosts: list[str]) -> bool:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    host = p.hostname.lower().rstrip(".")
    return any(host == h or host.endswith("." + h) for h in allowed_hosts)


def _is_public_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_reserved or addr.is_unspecified)


def assert_public_host(url: str, resolver=socket.getaddrinfo) -> None:
    """SSRF guard: every resolved address must be public."""
    host = urlparse(url).hostname or ""
    try:
        infos = resolver(host, None)
    except socket.gaierror as e:
        raise FetchBlocked(f"DNS resolution failed for {host}") from e
    for info in infos:
        ip = info[4][0]
        if not _is_public_ip(ip):
            raise FetchBlocked(f"{host} resolves to non-public address {ip}")


@dataclass
class _Breaker:
    failures: int = 0
    open_until: float = 0.0


@dataclass
class DomainPolicy:
    rate_limit_s: float
    last_request: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)


class SafeFetcher:
    """One instance per process. Thread-safe per-domain throttling."""

    BREAKER_THRESHOLD = 5
    BREAKER_COOLDOWN_S = 600

    def __init__(self, client: httpx.Client | None = None, resolver=socket.getaddrinfo, sleep=time.sleep):
        s = get_settings()
        self.ua = s.external_fetch_user_agent
        self.settings = s
        self.client = client or httpx.Client(timeout=s.external_fetch_timeout_s, follow_redirects=False, headers={"User-Agent": self.ua})
        self.resolver = resolver
        self.sleep = sleep
        self._policies: dict[str, DomainPolicy] = {}
        self._robots: dict[str, tuple[RobotFileParser | None, float]] = {}
        self._breakers: dict[str, _Breaker] = {}
        self.requests_made = 0
        self.max_requests: int | None = None  # per-run budget (set by discovery)

    # -- robots ---------------------------------------------------------------
    def robots_sitemaps(self, url: str) -> list[str]:
        """`Sitemap:` lines of the host's robots.txt (read through the same cached parser)."""
        self.robots_allows(url)
        p = urlparse(url)
        rp = self._robots.get(f"{p.scheme}://{p.hostname}", (None,))[0]
        return list(rp.site_maps() or []) if rp else []

    def robots_allows(self, url: str) -> bool:
        p = urlparse(url)
        base = f"{p.scheme}://{p.hostname}"
        cached = self._robots.get(base)
        if not cached or time.time() - cached[1] > 3600:
            rp = RobotFileParser()
            try:
                r = self.client.get(urljoin(base, "/robots.txt"))
                if r.status_code >= 400:
                    rp = None  # no robots → allowed
                else:
                    rp.parse(r.text.splitlines())
            except httpx.HTTPError:
                rp = None
            self._robots[base] = (rp, time.time())
            cached = self._robots[base]
        rp = cached[0]
        return True if rp is None else rp.can_fetch(self.ua, url)

    # -- throttle / breaker -----------------------------------------------------
    def _throttle(self, host: str, rate_limit_s: float) -> None:
        pol = self._policies.setdefault(host, DomainPolicy(rate_limit_s=rate_limit_s))
        with pol.lock:
            wait = pol.last_request + pol.rate_limit_s - time.time()
            if wait > 0:
                self.sleep(wait)
            pol.last_request = time.time()

    def _breaker(self, host: str) -> _Breaker:
        return self._breakers.setdefault(host, _Breaker())

    ALLOWED_TYPES = ("text/html", "application/xml", "text/xml", "application/json", "application/ld+json", "text/plain")

    def _check_response(self, r: httpx.Response, url: str, max_bytes: int | None = None, allowed_types: tuple[str, ...] | None = None) -> None:
        """Post-connection checks: DNS-rebinding (actual peer IP), content-type, size."""
        stream = r.extensions.get("network_stream")
        peer = stream.get_extra_info("server_addr") if stream is not None else None
        if peer and self.settings.external_ssrf_protection and not _is_public_ip(peer[0]):
            raise FetchBlocked(f"connected to non-public address {peer[0]} (DNS rebinding?)")
        ctype = r.headers.get("content-type", "text/html").split(";")[0].strip().lower()
        if r.status_code < 300 and ctype not in (allowed_types or self.ALLOWED_TYPES):
            raise FetchBlocked(f"unexpected content-type {ctype} for {url}")
        limit = max_bytes or self.settings.external_fetch_max_bytes
        if len(r.content) > limit:
            raise FetchBlocked(f"response larger than {limit} bytes")

    def fetch(self, url: str, allowed_hosts: list[str], rate_limit_s: float | None = None, max_redirects: int | None = None, retries: int | None = None,
              max_bytes: int | None = None, allowed_types: tuple[str, ...] | None = None) -> httpx.Response:
        """`max_bytes` overrides the global size limit for one request (e.g. a large audited sitemap)."""
        rate_limit_s = self.settings.external_fetch_rate_limit_s if rate_limit_s is None else rate_limit_s
        max_redirects = self.settings.external_fetch_max_redirects if max_redirects is None else max_redirects
        retries = self.settings.external_fetch_max_retries if retries is None else retries
        host = (urlparse(url).hostname or "").lower()
        br = self._breaker(host)
        if br.open_until > time.time():
            raise FetchBlocked(f"circuit open for {host}")
        for _ in range(max_redirects + 1):
            if not host_allowed(url, allowed_hosts):
                raise FetchBlocked(f"host not in allowlist: {url}")
            if self.settings.external_ssrf_protection:
                assert_public_host(url, self.resolver)
            if self.settings.external_robots_enforced and not self.robots_allows(url):
                raise FetchBlocked(f"robots.txt disallows {url}")
            attempt = 0
            while True:
                if self.max_requests is not None and self.requests_made >= self.max_requests:
                    raise FetchBlocked("request budget for this run exhausted")
                self.requests_made += 1
                self._throttle(host, rate_limit_s)
                try:
                    r = self.client.get(url)
                except httpx.HTTPError:
                    r = None
                if r is not None and r.status_code not in (429, 500, 502, 503, 504):
                    break
                attempt += 1
                if attempt > retries:
                    br.failures += 1
                    if br.failures >= self.BREAKER_THRESHOLD:
                        br.open_until = time.time() + self.BREAKER_COOLDOWN_S
                    raise FetchBlocked(f"upstream unavailable: {url}")
                self.sleep(min(30, 2 ** attempt))
            if r.status_code in (301, 302, 303, 307, 308):
                url = urljoin(url, r.headers.get("location", ""))
                host = (urlparse(url).hostname or "").lower()
                continue  # redirect target is re-validated at the top of the loop
            if r.status_code in (401, 403):
                raise FetchBlocked(f"access denied ({r.status_code}) — not bypassing")
            self._check_response(r, url, max_bytes, allowed_types)
            br.failures = 0
            return r
        raise FetchBlocked("too many redirects")
