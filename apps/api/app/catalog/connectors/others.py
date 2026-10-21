"""Connectors for sources without machine-readable product pages."""
from __future__ import annotations

from ..schema import NormalizedExternalProduct
from .base import ConnectorHealth, ExternalCatalogConnector, NeedQuery, SearchFilters
from .jsonld import JsonLdSitemapConnector, filter_candidates


class FeedConnector(ExternalCatalogConnector):
    """Supplier-provided CSV/XLSX/XML feed imported through the admin (or manual
    operator entry). Searches only records that were imported for this source."""

    parser_version = "feed-1.0"

    def __init__(self, source: dict, cache_lookup=None, **_):
        super().__init__(source)
        self.cache_lookup = cache_lookup

    def search_products(self, need: NeedQuery, filters: SearchFilters) -> list[NormalizedExternalProduct]:
        items = list(self.cache_lookup(self.source["id"], need.category)) if self.cache_lookup else []
        return filter_candidates(items, need, filters)

    def get_connector_health(self) -> ConnectorHealth:
        n = self.source.get("stats", {}).get("records", 0)
        if n:
            return ConnectorHealth(status="ok", message=f"{n} позиций из фида")
        return ConnectorHealth(status=self.source.get("connector_status", "needs_feed"),
                               message="Автоматическое обновление недоступно. Требуется каталог поставщика или ручное подтверждение.")


class RfqConnector(ExternalCatalogConnector):
    """Custom-made systems without public prices (Profal). Never returns invented
    products: discovery produces an RFQ requirement for the need instead."""

    parser_version = "rfq-1.0"

    def search_products(self, need: NeedQuery, filters: SearchFilters) -> list[NormalizedExternalProduct]:
        return []

    def rfq_supported(self, category: str) -> bool:
        from ..taxonomy import group_of

        return group_of(category) in self.source.get("categories", [])

    def get_connector_health(self) -> ConnectorHealth:
        return ConnectorHealth(status="rfq_only", message="Цены по запросу — формируется RFQ")


def build_connector(source: dict, *, live: bool, cache_lookup, fetcher=None) -> ExternalCatalogConnector:
    method = source.get("connector_type") or source.get("method")
    if method == "jsonld_sitemap":
        # live only when the global switch AND the per-source opt-in are both on
        return JsonLdSitemapConnector(source, fetcher=fetcher, live=live and bool(source.get("live_enabled")), cache_lookup=cache_lookup)
    if method == "rfq":
        return RfqConnector(source)
    return FeedConnector(source, cache_lookup=cache_lookup)
