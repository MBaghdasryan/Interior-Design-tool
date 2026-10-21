"""DEMO catalogue. Every supplier and product created here has is_demo=True and
price_status="demo": the UI, estimate and album label them as demonstration data.
They exist so the full pipeline can be exercised before real supplier feeds are
signed. They are NOT real offers and must never be sent in an RFQ."""
from __future__ import annotations

import itertools

DEMO_SUPPLIERS = [
    # slug, name, kind, delivery {fee, days}, install
    ("dom-i-stil", "Дом и стиль (DEMO)", "store", {"fee_amd": 15000, "days_min": 5, "days_max": 10}, {"pct": 5}),
    ("armenia-mebel", "Армения Мебель (DEMO)", "store", {"fee_amd": 20000, "days_min": 7, "days_max": 14}, {"pct": 6}),
    ("eco-svet", "Эко Свет (DEMO)", "store", {"fee_amd": 5000, "days_min": 2, "days_max": 5}, {"per_item_amd": 4000}),
    ("santeh-plus", "Сантех Плюс (DEMO)", "store", {"fee_amd": 10000, "days_min": 3, "days_max": 7}, {"pct": 8}),
    ("finish-mat", "Финиш Материалы (DEMO)", "store", {"fee_amd": 12000, "days_min": 1, "days_max": 3}, {}),
    ("techno-dom", "Техно Дом (DEMO)", "store", {"fee_amd": 0, "days_min": 1, "days_max": 4}, {"per_item_amd": 8000}),
    ("dveri-pro", "Двери Про (DEMO)", "manufacturer", {"fee_amd": 15000, "days_min": 14, "days_max": 28}, {"per_item_amd": 25000}),
    ("kitchen-lab", "Мастерская Кухонь (DEMO)", "manufacturer", {"fee_amd": 0, "days_min": 21, "days_max": 35}, {"pct": 0}),
]

# category -> supplier slug, base dims (w, d, h), base price AMD (comfort tier), unit, extra
BASE = {
    "sofa": ("dom-i-stil", (2600, 980, 820), 780000),
    "armchair": ("dom-i-stil", (800, 820, 780), 260000),
    "coffee_table": ("armenia-mebel", (1000, 600, 400), 120000),
    "tv_unit": ("armenia-mebel", (1800, 420, 500), 210000),
    "dining_table": ("armenia-mebel", (1600, 900, 750), 290000),
    "dining_chair": ("armenia-mebel", (480, 540, 800), 65000),
    "bed": ("dom-i-stil", (1760, 2150, 1050), 520000),
    "kids_bed": ("armenia-mebel", (960, 2050, 800), 210000),
    "nightstand": ("armenia-mebel", (500, 400, 500), 70000),
    "wardrobe": ("kitchen-lab", (1800, 600, 2600), 620000),
    "dresser": ("armenia-mebel", (1200, 480, 820), 190000),
    "desk": ("armenia-mebel", (1200, 600, 750), 110000),
    "desk_chair": ("dom-i-stil", (600, 600, 1050), 85000),
    "hallway_wardrobe": ("kitchen-lab", (1500, 600, 2600), 480000),
    "shoe_cabinet": ("armenia-mebel", (900, 350, 900), 95000),
    "bench": ("dom-i-stil", (1000, 400, 450), 75000),
    "storage_system": ("kitchen-lab", (1400, 450, 2400), 320000),
    "kitchen_run": ("kitchen-lab", (3600, 600, 2400), 1650000),
    "fridge": ("techno-dom", (600, 650, 2010), 520000),
    "cooktop": ("techno-dom", (600, 520, 60), 210000),
    "oven": ("techno-dom", (600, 560, 600), 260000),
    "hood": ("techno-dom", (600, 300, 400), 140000),
    "dishwasher": ("techno-dom", (450, 570, 820), 290000),
    "washer": ("techno-dom", (600, 450, 850), 270000),
    "tv": ("techno-dom", (1450, 80, 840), 380000),
    "toilet": ("santeh-plus", (370, 540, 400), 140000),
    "installation": ("santeh-plus", (500, 150, 1120), 95000),
    "vanity": ("santeh-plus", (800, 460, 850), 230000),
    "bathtub": ("santeh-plus", (1700, 750, 600), 260000),
    "shower": ("santeh-plus", (900, 900, 2000), 310000),
    "faucet": ("santeh-plus", (60, 200, 300), 65000),
    "towel_dryer": ("santeh-plus", (500, 120, 800), 90000),
    "pendant_light": ("eco-svet", (300, 300, 400), 120000),
    "spot_light": ("eco-svet", (90, 90, 70), 9000),
    "track_light": ("eco-svet", (2000, 40, 60), 95000),
    "led_strip": ("eco-svet", (5000, 10, 3), 18000),
    "wall_light": ("eco-svet", (150, 120, 250), 38000),
    "floor_lamp": ("eco-svet", (400, 400, 1700), 110000),
    "door_interior": ("dveri-pro", (800, 40, 2100), 135000),
    "door_sliding": ("dveri-pro", (1000, 40, 2400), 260000),
    "door_entrance": ("dveri-pro", (960, 90, 2050), 480000),
    "rug": ("dom-i-stil", (2000, 3000, 10), 160000),
    "curtains": ("dom-i-stil", (3000, 100, 2650), 120000),
    "artwork": ("dom-i-stil", (700, 30, 900), 45000),
    "mirror": ("dom-i-stil", (600, 30, 1600), 70000),
    "plant": ("dom-i-stil", (450, 450, 1300), 35000),
}

# Materials: (supplier, unit, package_coverage_m2, waste, price per unit, extra)
MATERIALS = {
    "floor_parquet": ("finish-mat", "m2", 1.98, 0.08, 18500),
    "floor_laminate": ("finish-mat", "pack", 2.13, 0.07, 14000),
    "floor_tile": ("finish-mat", "m2", 1.44, 0.10, 11500),
    "wall_tile": ("finish-mat", "m2", 1.08, 0.12, 12500),
    "wall_paint": ("finish-mat", "l", 8.0, 0.10, 4200),  # coverage per litre for 2 coats ≈ 8 m²/l → see estimator
    "wall_panel": ("finish-mat", "m2", 1.0, 0.08, 26000),
    "putty": ("finish-mat", "kg", 1.0, 0.05, 520),  # 1 kg ≈ 1 m² for finishing coat
    "tile_adhesive": ("finish-mat", "kg", 0.2, 0.05, 260),  # 5 kg/m²
    "drywall": ("finish-mat", "m2", 3.0, 0.10, 3900),
}

TIER_MULT = {"economy": 0.62, "comfort": 1.0, "business": 1.55, "premium": 2.4}
STYLE_DESC = {
    "warm_minimal": ("тёплый дуб", "#b98f6a", "букле, молочный", "#e9dfd2"),
    "modern_loft": ("тёмный орех", "#5a3d2e", "кожа коньячная", "#7a4a32"),
    "soft_scandi": ("светлый ясень", "#d6c2a1", "лён, светло-серый", "#d9d6cf"),
}
# small price spread between style lines so variants differ realistically
STYLE_PRICE = {"warm_minimal": 1.0, "modern_loft": 1.07, "soft_scandi": 0.94}
MODEL_NAMES = ["Arno", "Sevan", "Dilijan", "Areni", "Gyumri", "Tsaghik", "Hrazdan", "Lori"]


def demo_products() -> list[dict]:
    """Yields product dicts ready to insert (supplier slug, product, variants)."""
    out: list[dict] = []
    names = itertools.cycle(MODEL_NAMES)
    for cat, (sup, dims, price) in BASE.items():
        for tier in ("economy", "comfort", "premium"):
            mult = TIER_MULT[tier]
            w, d, h = dims
            if cat in ("sofa", "wardrobe", "hallway_wardrobe", "dining_table", "bed") and tier == "premium":
                w = round(w * 1.08 / 10) * 10
            if cat in ("sofa",) and tier == "economy":
                w = round(w * 0.85 / 10) * 10
            model = next(names)
            styles_variants = []
            for style, (wood, wood_hex, fabric, fabric_hex) in STYLE_DESC.items():
                is_soft = cat in ("sofa", "armchair", "bed", "dining_chair", "desk_chair", "bench", "rug", "curtains")
                styles_variants.append({
                    "style": style,
                    "color": fabric if is_soft else wood,
                    "color_hex": fabric_hex if is_soft else wood_hex,
                    "material": fabric if is_soft else wood,
                })
            item_type = "made_to_order" if sup in ("kitchen-lab",) else "serial"
            if cat == "kitchen_run":
                item_type = "parametric"
            price_status = "demo"
            # door manufacturer premium line has no public price → quote
            quote = sup == "dveri-pro" and tier == "premium"
            out.append({
                "supplier": sup,
                "category": cat,
                "tier": tier,
                "item_type": item_type,
                "brand": f"{model} Collection",
                "name_ru": f"{model} — {cat.replace('_', ' ')}",
                "styles": [v["style"] for v in styles_variants],
                "parametric": {"width_range": [1200, 4800], "price_per_m": round(price * mult / 3.6), "lead_time_days": 28, "made_to_measure": True}
                if item_type == "parametric" or (item_type == "made_to_order" and cat in ("wardrobe", "hallway_wardrobe", "storage_system"))
                else {},
                "variants": [
                    {
                        "sku": f"DEMO-{cat.upper()}-{tier[:3].upper()}-{v['style'][:3].upper()}",
                        "color": v["color"],
                        "color_hex": v["color_hex"],
                        "material": v["material"],
                        "style": v["style"],
                        "width_mm": w,
                        "depth_mm": d,
                        "height_mm": h,
                        "price": None if quote else round(price * mult * STYLE_PRICE[v["style"]], -3),
                        "price_status": "quote_required" if quote else price_status,
                        "stock_status": "to_order" if item_type != "serial" else ("in_stock" if tier != "premium" else "to_order"),
                        "lead_time_days": 28 if item_type != "serial" else (3 if tier != "premium" else 21),
                    }
                    for v in styles_variants
                ],
            })
    for cat, (sup, unit, cov, waste, price) in MATERIALS.items():
        for tier in ("economy", "comfort", "premium"):
            mult = TIER_MULT[tier]
            out.append({
                "supplier": sup,
                "category": cat,
                "tier": tier,
                "item_type": "material",
                "brand": f"{next(names)} Materials",
                "name_ru": f"{cat.replace('_', ' ')} ({tier})",
                "unit": unit,
                "package_coverage_m2": cov,
                "waste_pct": waste,
                "styles": list(STYLE_DESC.keys()),
                "variants": [
                    {
                        "sku": f"DEMO-{cat.upper()}-{tier[:3].upper()}-{style[:3].upper()}",
                        "color": desc[0],
                        "color_hex": {"floor_tile": "#cfc6bb", "wall_tile": "#e8e2d9", "wall_paint": desc[3]}.get(cat, desc[1]),
                        "material": desc[0],
                        "style": style,
                        "price": round(price * mult * STYLE_PRICE[style], -1),
                        "price_status": "demo",
                        "stock_status": "in_stock",
                        "lead_time_days": 2,
                    }
                    for style, desc in STYLE_DESC.items()
                ],
            })
    return out
