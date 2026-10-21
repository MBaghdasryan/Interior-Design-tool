"""ExternalCatalogConnector contract (addon prompt §5). Connectors return
schema-validated NormalizedExternalProduct objects — never raw HTML."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..schema import NormalizedExternalProduct


@dataclass
class SearchFilters:
    max_price_amd: float | None = None
    min_price_amd: float | None = None
    only_priced: bool = False
    only_available: bool = False
    allow_quote: bool = True
    city: str = "Ереван"
    limit: int = 6


@dataclass
class NeedQuery:
    key: str
    category: str
    text: str = ""
    max_width_mm: float | None = None
    style: str | None = None
    color: str | None = None


@dataclass
class ConnectorHealth:
    status: str  # ok | degraded | blocked | needs_audit | needs_feed | rfq_only | disabled | unreachable
    message: str = ""
    latency_ms: int = 0
    details: dict = field(default_factory=dict)


class ExternalCatalogConnector(ABC):
    parser_version = "0"

    def __init__(self, source: dict):
        self.source = source  # ExternalSource row as dict

    @property
    def key(self) -> str:
        return self.source["key"]

    @abstractmethod
    def search_products(self, need: NeedQuery, filters: SearchFilters) -> list[NormalizedExternalProduct]: ...

    def get_product(self, url_or_id: str) -> NormalizedExternalProduct | None:
        return None

    def get_categories(self) -> list[str]:
        return list(self.source.get("categories", []))

    def refresh_product(self, external_id: str) -> NormalizedExternalProduct | None:
        return self.get_product(external_id)

    def check_availability(self, external_id: str) -> str:
        p = self.get_product(external_id)
        return p.availability_status if p else "unknown"

    @abstractmethod
    def get_connector_health(self) -> ConnectorHealth: ...

    def get_policy_status(self) -> dict:
        return self.source.get("policy", {})
