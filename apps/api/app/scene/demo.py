"""Demo apartment used for the public seed and tests. It is a synthetic 3-room
apartment (≈66 m²) — NOT the pilot client's apartment; real pilot data must be
uploaded by its owner and is never part of the seed."""
from __future__ import annotations

from .model import (
    Assumption,
    CeilingSpec,
    ControlDimension,
    Fixture,
    Opening,
    Room,
    Scene,
    Wall,
)

H = 2750  # slab-to-slab height


def demo_base_scene() -> Scene:
    ext, inner = 300, 120
    walls = [
        # exterior contour (centre lines)
        Wall(id="W1", a=(0, 0), b=(9600, 0), thickness=ext, kind="exterior", material="concrete", load_bearing=True, source="recognized", confidence=0.97),
        Wall(id="W2", a=(9600, 0), b=(9600, 7400), thickness=ext, kind="exterior", material="concrete", load_bearing=True, source="recognized", confidence=0.96),
        Wall(id="W3", a=(9600, 7400), b=(0, 7400), thickness=ext, kind="exterior", material="concrete", load_bearing=True, source="recognized", confidence=0.95),
        Wall(id="W4", a=(0, 7400), b=(0, 0), thickness=ext, kind="exterior", material="concrete", load_bearing=True, source="recognized", confidence=0.97),
        # load-bearing spine between bedroom and living
        Wall(id="W5", a=(3800, 0), b=(3800, 4200), thickness=200, kind="interior", material="concrete", load_bearing=True, source="recognized", confidence=0.93),
        # corridor wall (north side of hallway)
        Wall(id="W6", a=(0, 4200), b=(9600, 4200), thickness=inner, kind="interior", material="brick", source="recognized", confidence=0.9),
        # old kitchen partition — removed by the design to open the kitchen-living
        Wall(id="W7", a=(7200, 0), b=(7200, 4200), thickness=inner, kind="partition", material="brick", status="demolish", source="recognized", confidence=0.82),
        # bathroom | hallway
        Wall(id="W8", a=(2200, 4200), b=(2200, 7400), thickness=inner, kind="partition", material="brick", source="recognized", confidence=0.88),
        # kids room | hallway (east)
        Wall(id="W9", a=(6800, 4200), b=(6800, 7400), thickness=inner, kind="partition", material="brick", source="recognized", confidence=0.86),
        # new wardrobe partitions (drywall)
        Wall(id="W10", a=(5200, 5600), b=(5200, 7400), thickness=100, kind="partition", material="drywall", status="new", source="ai", confidence=0.9),
        Wall(id="W11", a=(5200, 5600), b=(6800, 5600), thickness=100, kind="partition", material="drywall", status="new", source="ai", confidence=0.9),
        # balcony
        Wall(id="W12", a=(4800, 0), b=(4800, -1400), thickness=150, kind="balcony", material="block", source="recognized", confidence=0.7),
        Wall(id="W13", a=(4800, -1400), b=(9000, -1400), thickness=150, kind="balcony", material="glass", source="recognized", confidence=0.65),
        Wall(id="W14", a=(9000, -1400), b=(9000, 0), thickness=150, kind="balcony", material="block", source="recognized", confidence=0.7),
    ]
    openings = [
        Opening(id="D1", wall_id="W3", type="entrance_door", offset=9600 - 4300, width=960, height=2100, hinge="end", swing="left", source="recognized", confidence=0.9),
        Opening(id="D2", wall_id="W8", type="door", offset=600, width=800, hinge="start", swing="left", source="recognized", confidence=0.85),
        Opening(id="D3", wall_id="W6", type="door", offset=2700, width=800, hinge="start", swing="left", source="recognized", confidence=0.85),
        Opening(id="D4", wall_id="W6", type="opening", offset=4300, width=1200, height=2400, source="recognized", confidence=0.8),
        Opening(id="D5", wall_id="W11", type="sliding_door", offset=300, width=1000, status="new", source="ai", confidence=0.9),
        Opening(id="D6", wall_id="W9", type="door", offset=250, width=800, hinge="start", swing="left", source="recognized", confidence=0.84),
        Opening(id="WN1", wall_id="W1", type="window", offset=1000, width=1700, height=1600, sill=800, source="recognized", confidence=0.92),
        Opening(id="WN2", wall_id="W1", type="window", offset=5300, width=1800, height=1600, sill=800, source="recognized", confidence=0.9),
        Opening(id="WN3", wall_id="W1", type="balcony_door", offset=7550, width=800, height=2200, hinge="end", swing="right", source="recognized", confidence=0.88),
        Opening(id="WN4", wall_id="W2", type="window", offset=1300, width=1400, height=1500, sill=850, source="recognized", confidence=0.9),
        Opening(id="WN5", wall_id="W2", type="window", offset=5000, width=1400, height=1500, sill=850, source="recognized", confidence=0.87),
    ]
    e, i2, d2 = ext / 2, inner / 2, 100 / 2
    rooms = [
        Room(id="R1", number=1, type="hallway", name="Прихожая", zone="service", ceiling_height=H,
             polygon=[(2200 + i2, 4200 + i2), (6800 - i2, 4200 + i2), (6800 - i2, 5600 - d2), (5200 - d2, 5600 - d2), (5200 - d2, 7400 - e), (2200 + i2, 7400 - e)],
             source="recognized", confidence=0.86),
        Room(id="R2", number=2, type="bathroom", name="Санузел", zone="wet", ceiling_height=H,
             polygon=[(0 + e, 4200 + i2), (2200 - i2, 4200 + i2), (2200 - i2, 7400 - e), (0 + e, 7400 - e)],
             source="recognized", confidence=0.9),
        Room(id="R3", number=3, type="bedroom", name="Спальня", zone="night", ceiling_height=H,
             polygon=[(0 + e, 0 + e), (3800 - 100, 0 + e), (3800 - 100, 4200 - i2), (0 + e, 4200 - i2)],
             source="recognized", confidence=0.93),
        Room(id="R4", number=4, type="kitchen_living", name="Кухня-гостиная", zone="day", ceiling_height=H,
             polygon=[(3800 + 100, 0 + e), (9600 - e, 0 + e), (9600 - e, 4200 - i2), (3800 + 100, 4200 - i2)],
             source="recognized", confidence=0.9),
        Room(id="R5", number=5, type="kids", name="Детская", zone="night", ceiling_height=H,
             polygon=[(6800 + i2, 4200 + i2), (9600 - e, 4200 + i2), (9600 - e, 7400 - e), (6800 + i2, 7400 - e)],
             source="recognized", confidence=0.88),
        Room(id="R6", number=6, type="wardrobe", name="Гардеробная", zone="service", ceiling_height=H,
             polygon=[(5200 + d2, 5600 + d2), (6800 - i2, 5600 + d2), (6800 - i2, 7400 - e), (5200 + d2, 7400 - e)],
             source="ai", confidence=0.9),
        Room(id="R7", number=7, type="balcony", name="Балкон", zone="outdoor", ceiling_height=2600,
             polygon=[(4800 + 75, -1400 + 75), (9000 - 75, -1400 + 75), (9000 - 75, 0 - e), (4800 + 75, 0 - e)],
             source="recognized", confidence=0.7),
    ]
    fixtures = [
        Fixture(id="F1", type="riser_water", position=(300, 4500), room_id="R2", size=(200, 200), source="recognized", confidence=0.8),
        Fixture(id="F2", type="riser_sewer", position=(520, 4500), room_id="R2", size=(160, 160), source="recognized", confidence=0.8),
        Fixture(id="F3", type="water_cold", position=(9300, 2900), room_id="R4", source="assumed", confidence=0.55, note="Перенос мойки к окну — согласовать"),
        Fixture(id="F4", type="drain", position=(9300, 3100), room_id="R4", source="assumed", confidence=0.55),
        Fixture(id="F5", type="radiator", position=(1850, 260), room_id="R3", size=(1200, 100), source="recognized", confidence=0.85),
        Fixture(id="F6", type="radiator", position=(6200, 260), room_id="R4", size=(1400, 100), source="recognized", confidence=0.85),
        Fixture(id="F7", type="radiator", position=(9340, 5700), room_id="R5", size=(100, 1000), rotation=90, source="recognized", confidence=0.83),
        Fixture(id="F8", type="radiator", position=(9340, 2000), room_id="R4", size=(100, 1000), rotation=90, source="recognized", confidence=0.8),
        Fixture(id="F9", type="electrical_panel", position=(2400, 7180), room_id="R1", size=(400, 120), source="recognized", confidence=0.75),
        Fixture(id="F10", type="ventilation", position=(1950, 4450), room_id="R2", size=(200, 200), source="recognized", confidence=0.7),
        Fixture(id="F11", type="ventilation", position=(9350, 3950), room_id="R4", size=(200, 200), source="assumed", confidence=0.5),
        Fixture(id="F12", type="warm_floor", position=(1100, 5800), room_id="R2", size=(1700, 2800), source="ai", confidence=0.9),
    ]
    ceilings = [
        CeilingSpec(room_id="R1", type="gkl_flat", height=2550, note="Короб под вентиляцию"),
        CeilingSpec(room_id="R2", type="gkl_flat", height=2500, note="Влагостойкий ГКЛ"),
        CeilingSpec(room_id="R3", type="shadow_gap", height=2650, curtain_niche=True),
        CeilingSpec(room_id="R4", type="gkl_multilevel", height=2650, curtain_niche=True, note="Скрытая LED-подсветка по периметру"),
        CeilingSpec(room_id="R5", type="shadow_gap", height=2650, curtain_niche=True),
        CeilingSpec(room_id="R6", type="paint", height=2650),
        CeilingSpec(room_id="R7", type="paint", height=2600),
    ]
    return Scene(
        name="Демо-квартира · 3 комнаты",
        ceiling_height=H,
        walls=walls,
        openings=openings,
        rooms=rooms,
        fixtures=fixtures,
        ceilings=ceilings,
        control_dimensions=[ControlDimension(wall_id="W1", measured_mm=9600)],
        assumptions=[
            Assumption(key="kitchen_water", text="Точки воды кухни определены по типовой схеме дома — требуется проверка на объекте", severity="warning", element_id="F3"),
            Assumption(key="balcony_glazing", text="Тип остекления балкона определён по фото с низкой уверенностью", severity="info", element_id="W13"),
            Assumption(key="w7_bearing", text="Стена W7 предполагается ненесущей (кирпич 120 мм). Демонтаж — только после подтверждения конструктора", severity="critical", element_id="W7"),
        ],
    )
