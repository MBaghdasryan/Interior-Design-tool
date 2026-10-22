"""Custom furniture module library (P2-5): kitchens, wardrobes, walk-in closets and TV zones.
Ranges, steps and production constraints are typical for Armenian cabinet shops working with
2800×2070 chipboard sheets; a manufacturer's own limits override them (`rates.limits`).
No prices here — prices come only from the manufacturer's rates (see pricing.py)."""
from __future__ import annotations

BODY = ("ldsp16", "ldsp18", "mdf18")
FRONTS = ("ldsp", "mdf_film", "mdf_paint", "veneer", "glass_frame")
HARDWARE = ("hinge_softclose", "runner_full", "liftup", "sliding_system", "handle", "rail")

# type: family, w/h/d ranges (min, max, step) mm, door rule, defaults
MODULES: dict[str, dict] = {
    "kitchen_base": {"family": "kitchen", "w": (300, 1000, 50), "h": (720, 900, 10), "d": (450, 650, 10), "doors": "auto", "shelves": 1, "hw": {"hinge_softclose": 2}},
    "kitchen_drawer_base": {"family": "kitchen", "w": (300, 1000, 50), "h": (720, 900, 10), "d": (450, 650, 10), "drawers": 3, "hw": {"runner_full": 3}},
    "kitchen_sink_base": {"family": "kitchen", "w": (500, 1000, 50), "h": (720, 900, 10), "d": (500, 650, 10), "doors": "auto", "shelves": 0, "back": False, "hw": {"hinge_softclose": 2}},
    "kitchen_wall": {"family": "kitchen", "w": (300, 1000, 50), "h": (360, 960, 10), "d": (280, 400, 10), "doors": "auto", "shelves": 1, "hw": {"hinge_softclose": 2}},
    "kitchen_wall_liftup": {"family": "kitchen", "w": (400, 1200, 50), "h": (300, 450, 10), "d": (280, 400, 10), "doors": 1, "shelves": 0, "hw": {"liftup": 1}},
    "kitchen_tall": {"family": "kitchen", "w": (400, 700, 50), "h": (1800, 2400, 10), "d": (500, 650, 10), "doors": 2, "shelves": 4, "hw": {"hinge_softclose": 6}},
    "wardrobe_hinged": {"family": "wardrobe", "w": (400, 1200, 50), "h": (1800, 2700, 10), "d": (450, 650, 10), "doors": "auto", "shelves": 3, "hw": {"hinge_softclose": 4, "rail": 1}},
    "wardrobe_sliding": {"family": "wardrobe", "w": (1000, 3000, 50), "h": (1800, 2700, 10), "d": (600, 700, 10), "doors": "sliding", "shelves": 3, "hw": {"sliding_system": 1, "rail": 1}},
    "wardrobe_drawers": {"family": "wardrobe", "w": (400, 1000, 50), "h": (600, 1200, 10), "d": (450, 650, 10), "drawers": 4, "hw": {"runner_full": 4}},
    "walkin_tower": {"family": "walkin", "w": (300, 900, 50), "h": (1800, 2700, 10), "d": (300, 600, 10), "doors": 0, "shelves": 6, "back": False, "hw": {}},
    "walkin_hanging": {"family": "walkin", "w": (500, 1200, 50), "h": (1800, 2700, 10), "d": (500, 600, 10), "doors": 0, "shelves": 1, "back": False, "hw": {"rail": 2}},
    "tv_low": {"family": "tv", "w": (900, 2400, 50), "h": (300, 600, 10), "d": (350, 500, 10), "doors": "auto", "shelves": 0, "hw": {"liftup": 0, "hinge_softclose": 4}},
    "tv_panel": {"family": "tv", "w": (900, 3000, 50), "h": (600, 2400, 10), "d": (18, 40, 1), "doors": 0, "shelves": 0, "back": False, "panel": True, "hw": {}},
    "tv_shelf": {"family": "tv", "w": (400, 1800, 50), "h": (200, 400, 10), "d": (200, 350, 10), "doors": 0, "shelves": 0, "hw": {}},
}
FAMILIES = ("kitchen", "wardrobe", "walkin", "tv")
SHEET = (2800, 2070)  # default chipboard sheet, mm
MAX_DOOR_W = 600  # hinged door; wider openings get two doors
MAX_HINGED_DOOR_H = 2400
PANEL_T = {"ldsp16": 16, "ldsp18": 18, "mdf18": 18}
