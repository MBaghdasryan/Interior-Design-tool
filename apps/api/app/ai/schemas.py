"""Structured-output contracts for AI tasks. LLM output is validated against these
Pydantic models; anything that fails validation is rejected (and retried/fallen back)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

StyleKey = Literal["warm_minimal", "modern_loft", "soft_scandi", "contemporary", "classic"]
Tier = Literal["economy", "comfort", "business", "premium"]


class Household(BaseModel):
    adults: int = 2
    children: int = 0
    elderly: int = 0
    pets: list[str] = Field(default_factory=list)


class RoomPurpose(BaseModel):
    room_type: str
    purpose: str


class DesignBrief(BaseModel):
    household: Household = Field(default_factory=Household)
    rooms_program: list[RoomPurpose] = Field(default_factory=list)
    styles: list[StyleKey] = Field(default_factory=list)
    colors_like: list[str] = Field(default_factory=list)
    colors_avoid: list[str] = Field(default_factory=list)
    budget_tier: Tier = "comfort"
    budget_amd: int | None = None
    storage_level: Literal["low", "medium", "high"] = "medium"
    work_from_home: bool = False
    keep_items: list[str] = Field(default_factory=list)
    preferred_suppliers: list[str] = Field(default_factory=list)
    only_in_stock: bool = False
    max_weeks: int | None = None
    eco_materials: bool = False
    replanning_allowed: bool = True
    finish_level: Literal["basic", "standard", "premium"] = "standard"
    notes: str = ""
    assumptions: list[str] = Field(default_factory=list)


OpName = Literal[
    "replace_product", "make_compact", "change_color", "add_object", "remove_object", "change_material",
    "budget_delta", "lighter", "darker", "cheaper", "premium", "change_style",
]


class OpParams(BaseModel):
    target_color: str | None = None
    max_width_mm: int | None = None
    delta_amd: int | None = None
    material: str | None = None
    style: StyleKey | None = None
    closed_storage: bool | None = None


class ChangeOperation(BaseModel):
    op: OpName
    room_type: str | None = None
    room_id: str | None = None
    category: str | None = None
    params: OpParams = Field(default_factory=OpParams)
    explanation: str = ""


class ChangePlan(BaseModel):
    operations: list[ChangeOperation]
    summary: str
    unsupported: list[str] = Field(default_factory=list)


class RecognizedWall(BaseModel):
    id: str
    a: tuple[float, float]
    b: tuple[float, float]
    thickness: float
    kind: Literal["exterior", "interior", "partition", "balcony"]
    confidence: float


class RecognizedOpening(BaseModel):
    id: str
    wall_id: str
    type: Literal["door", "window", "opening", "balcony_door", "entrance_door", "sliding_door"]
    offset: float
    width: float
    confidence: float


class RecognizedRoom(BaseModel):
    id: str
    type: str
    name: str
    polygon: list[tuple[float, float]]
    area_label_m2: float | None = None
    confidence: float


class FloorplanRecognition(BaseModel):
    """Plan-image recognition draft. Units: mm after applying the detected/declared scale."""

    scale_source: Literal["dimension_text", "control_dimension", "assumed"]
    walls: list[RecognizedWall]
    openings: list[RecognizedOpening]
    rooms: list[RecognizedRoom]
    dimension_texts: list[str] = Field(default_factory=list)
    ceiling_height_mm: float | None = None
    uncertainties: list[str] = Field(default_factory=list)


class VariantCopy(BaseModel):
    title: str
    subtitle: str
    description: str


class GroundedItem(BaseModel):
    code: str
    visible: bool
    type_match: float = Field(ge=0, le=1, description="the object is of the listed type")
    color_match: float = Field(ge=0, le=1, description="dominant colour matches the listed colour")
    position_match: float = Field(ge=0, le=1, description="it is where the manifest says (left/center/right)")
    note: str = ""


class GroundingCheck(BaseModel):
    """Vision check of a photoreal render against its SKU manifest."""
    items: list[GroundedItem]
    extra_objects: list[str] = Field(default_factory=list, description="prominent furniture/fixtures not in the manifest")
