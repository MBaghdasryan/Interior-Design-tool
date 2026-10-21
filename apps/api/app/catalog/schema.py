"""Normalised external product (addon prompt §6). Missing fields stay None —
never filled in by an AI guess."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Dimensions(BaseModel):
    width_mm: float | None = None
    depth_mm: float | None = None
    height_mm: float | None = None
    diameter_mm: float | None = None
    tile_w_mm: float | None = None
    tile_h_mm: float | None = None
    thickness_mm: float | None = None
    raw: str | None = None


class FieldProvenance(BaseModel):
    field: str
    url: str
    method: str  # jsonld | og | feed | manual | api
    value: str | None = None


class NormalizedExternalProduct(BaseModel):
    external_source_id: str
    source_key: str
    external_product_id: str | None = None
    canonical_url: str
    name: str
    brand: str | None = None
    sku: str | None = None
    mpn: str | None = None
    category: str | None = None
    normalized_category: str | None = None
    description_summary: str | None = None
    dimensions: Dimensions = Field(default_factory=Dimensions)
    color: str | None = None
    material: str | None = None
    attributes: dict = Field(default_factory=dict)
    price_value: float | None = None
    original_currency: str | None = None
    price_amd: float | None = None
    old_price: float | None = None
    promo_price: float | None = None
    price_valid_until: str | None = None
    unit_of_sale: str = "pcs"  # pcs | m2 | pack | kg | l | m
    package_coverage_m2: float | None = None
    availability_status: str = "unknown"  # in_stock | to_order | out_of_stock | unknown
    availability_evidence: str | None = None
    delivery: dict = Field(default_factory=dict)
    warranty: str | None = None
    main_image_url: str | None = None
    image_urls: list[str] = Field(default_factory=list)
    source_language: str | None = None
    retrieved_at: datetime
    price_checked_at: datetime | None = None
    availability_checked_at: datetime | None = None
    parser_version: str
    provenance: list[FieldProvenance] = Field(default_factory=list)
    confidence: float = 0.0
    validation_warnings: list[str] = Field(default_factory=list)
    disputed_fields: dict = Field(default_factory=dict)
    quote_required: bool = False
    manual_confirmation_required: bool = False
