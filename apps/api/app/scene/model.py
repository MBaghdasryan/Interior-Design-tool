"""Normalised scene model (BuildingGraph). Units: millimetres. Coordinate system:
plan view, X to the right, Y downwards (screen / sheet orientation), origin at the
top-left interior corner. Every element carries `source` and `confidence` so the
UI can colour-code what was recognised, assumed or confirmed."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Point = tuple[float, float]
Source = Literal["recognized", "assumed", "manual", "measured", "imported", "ai", "template"]


class Tracked(BaseModel):
    source: Source = "manual"
    confidence: float = 1.0


class Wall(Tracked):
    id: str
    a: Point
    b: Point
    thickness: float = 120
    kind: Literal["exterior", "interior", "partition", "balcony"] = "interior"
    # existing walls are kept, "demolish" are removed, "new" are erected by the design
    status: Literal["existing", "demolish", "new"] = "existing"
    material: Literal["concrete", "brick", "block", "drywall", "glass"] = "brick"
    load_bearing: bool = False
    height: float | None = None


class Opening(Tracked):
    id: str
    wall_id: str
    type: Literal["door", "window", "opening", "balcony_door", "entrance_door", "sliding_door"]
    offset: float  # distance from wall.a to the opening start along the wall
    width: float
    height: float = 2100
    sill: float = 0
    hinge: Literal["start", "end"] = "start"  # hinge at the start or end of the opening span
    swing: Literal["left", "right"] = "left"  # which side of the wall (looking a→b) the leaf opens to
    status: Literal["existing", "demolish", "new"] = "existing"
    product_variant_id: str | None = None


class Room(Tracked):
    id: str
    number: int
    type: Literal[
        "living", "kitchen", "kitchen_living", "bedroom", "kids", "bathroom", "wc", "hallway",
        "wardrobe", "balcony", "office", "storage", "laundry",
    ]
    name: str
    polygon: list[Point]
    ceiling_height: float = 2700
    zone: Literal["day", "night", "wet", "service", "outdoor"] | None = None


class Fixture(Tracked):
    """Fixed engineering items: risers, water inlets, drains, radiators, panels."""

    id: str
    type: Literal[
        "riser_water", "riser_sewer", "water_cold", "water_hot", "drain", "radiator", "boiler",
        "electrical_panel", "ventilation", "gas", "warm_floor",
    ]
    position: Point
    room_id: str | None = None
    size: tuple[float, float] | None = None  # w, d for radiators / boxes
    rotation: float = 0
    note: str = ""


class SceneObject(Tracked):
    """A placed item. Must be grounded on a product variant (real mode) or be an
    explicit concept/custom object."""

    id: str
    code: str = ""  # drawing tag, e.g. "K-01"
    room_id: str
    category: str
    name: str = ""
    product_variant_id: str | None = None
    custom_product: dict | None = None  # parametric/custom definition
    x: float  # centre
    y: float
    w: float  # along local X
    d: float  # along local Y (depth)
    h: float = 800
    rotation: float = 0  # degrees, multiples of 90 in MVP; 0 = front faces +Y
    elevation: float = 0
    locked: bool = False
    against_wall_id: str | None = None
    color_hex: str = "#b9a48f"
    mode: Literal["real", "concept"] = "real"


class Electrical(Tracked):
    id: str
    code: str = ""
    type: Literal[
        "socket", "socket_double", "socket_triple", "socket_waterproof", "socket_power", "tv", "data",
        "switch", "switch_double", "switch_pass", "thermostat", "hood", "oven", "cooktop", "dishwasher",
        "washer", "boiler", "fridge",
    ]
    position: Point
    height: float = 300
    room_id: str | None = None
    wall_id: str | None = None
    group: str = ""
    note_key: str = ""  # stable code of a system-generated note (translated in documents); free-text notes leave it empty
    note: str = ""


class Light(Tracked):
    id: str
    code: str = ""
    type: Literal["pendant", "spot", "track", "led_strip", "wall", "ceiling", "floor_lamp", "mirror"]
    position: Point
    end: Point | None = None  # for strips / tracks
    room_id: str | None = None
    scenario: str = "general"  # general | accent | night | work
    switch_group: str = ""
    power_w: float = 10
    product_variant_id: str | None = None


class CeilingSpec(BaseModel):
    room_id: str
    type: Literal["paint", "gkl_flat", "gkl_multilevel", "stretch", "shadow_gap", "cove"] = "gkl_flat"
    height: float = 2650
    curtain_niche: bool = False
    note: str = ""


class SurfaceFinish(BaseModel):
    """Material assignment for a room surface (floor / walls / ceiling / accent wall)."""

    room_id: str
    surface: Literal["floor", "walls", "ceiling", "accent_wall", "apron", "wet_walls"]
    product_variant_id: str | None = None
    material_code: str = ""
    name: str = ""
    color_hex: str = "#d9c9b7"
    pattern: Literal["plain", "herringbone", "plank", "tile_grid", "large_tile", "paint"] = "plain"
    wall_id: str | None = None


class Camera(BaseModel):
    id: str
    room_id: str
    position: Point
    target: Point
    height: float = 1400
    fov: float = 60


class ControlDimension(BaseModel):
    wall_id: str
    measured_mm: float
    confirmed: bool = True


class Assumption(BaseModel):
    key: str
    text: str
    severity: Literal["info", "warning", "critical"] = "info"
    element_id: str | None = None


class Scene(BaseModel):
    schema_version: str = "1.0"
    units: Literal["mm"] = "mm"
    name: str = ""
    ceiling_height: float = 2700
    walls: list[Wall] = Field(default_factory=list)
    openings: list[Opening] = Field(default_factory=list)
    rooms: list[Room] = Field(default_factory=list)
    fixtures: list[Fixture] = Field(default_factory=list)
    objects: list[SceneObject] = Field(default_factory=list)
    electrical: list[Electrical] = Field(default_factory=list)
    lights: list[Light] = Field(default_factory=list)
    ceilings: list[CeilingSpec] = Field(default_factory=list)
    finishes: list[SurfaceFinish] = Field(default_factory=list)
    cameras: list[Camera] = Field(default_factory=list)
    control_dimensions: list[ControlDimension] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)

    def wall(self, wall_id: str) -> Wall | None:
        return next((w for w in self.walls if w.id == wall_id), None)

    def room(self, room_id: str) -> Room | None:
        return next((r for r in self.rooms if r.id == room_id), None)
