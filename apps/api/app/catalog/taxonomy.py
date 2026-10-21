"""Normalised product taxonomy shared by PIM, external discovery, estimator and album."""
from __future__ import annotations

# key: (group, ru, hy, en)
CATEGORIES: dict[str, tuple[str, str, str, str]] = {
    "sofa": ("furniture", "Диван", "Բազմոց", "Sofa"),
    "armchair": ("furniture", "Кресло", "Բազկաթոռ", "Armchair"),
    "coffee_table": ("furniture", "Журнальный стол", "Սուրճի սեղան", "Coffee table"),
    "tv_unit": ("furniture", "ТВ-тумба", "TV տումբա", "TV unit"),
    "dining_table": ("furniture", "Обеденный стол", "Ճաշասեղան", "Dining table"),
    "dining_chair": ("furniture", "Обеденный стул", "Աթոռ", "Dining chair"),
    "bed": ("furniture", "Кровать", "Մահճակալ", "Bed"),
    "kids_bed": ("furniture", "Детская кровать", "Մանկական մահճակալ", "Kids bed"),
    "nightstand": ("furniture", "Прикроватная тумба", "Կողատումբա", "Nightstand"),
    "wardrobe": ("furniture", "Шкаф", "Զգեստապահարան", "Wardrobe"),
    "dresser": ("furniture", "Комод", "Կոմոդ", "Dresser"),
    "desk": ("furniture", "Письменный стол", "Գրասեղան", "Desk"),
    "desk_chair": ("furniture", "Рабочее кресло", "Աշխատանքային աթոռ", "Desk chair"),
    "hallway_wardrobe": ("furniture", "Шкаф в прихожую", "Նախասենյակի պահարան", "Hallway wardrobe"),
    "shoe_cabinet": ("furniture", "Обувница", "Կոշկապահարան", "Shoe cabinet"),
    "bench": ("furniture", "Банкетка", "Նստարան", "Bench"),
    "storage_system": ("furniture", "Гардеробная система", "Հանդերձարանի համակարգ", "Storage system"),
    "kitchen_run": ("furniture", "Кухонный гарнитур", "Խոհանոցային կահույք", "Kitchen run"),
    "fridge": ("appliances", "Холодильник", "Սառնարան", "Fridge"),
    "cooktop": ("appliances", "Варочная панель", "Եփման վահանակ", "Cooktop"),
    "oven": ("appliances", "Духовой шкаф", "Ջեռոց", "Oven"),
    "hood": ("appliances", "Вытяжка", "Օդաքարշ", "Hood"),
    "dishwasher": ("appliances", "Посудомоечная машина", "Սպասք լվացող մեքենա", "Dishwasher"),
    "washer": ("appliances", "Стиральная машина", "Լվացքի մեքենա", "Washing machine"),
    "tv": ("appliances", "Телевизор", "Հեռուստացույց", "TV"),
    "toilet": ("plumbing", "Унитаз подвесной", "Զուգարանակոնք", "Wall-hung WC"),
    "vanity": ("plumbing", "Тумба с раковиной", "Լվացարանով տումբա", "Vanity unit"),
    "bathtub": ("plumbing", "Ванна", "Լոգարան", "Bathtub"),
    "shower": ("plumbing", "Душевая зона", "Ցնցուղ", "Shower"),
    "faucet": ("plumbing", "Смеситель", "Ծորակ", "Faucet"),
    "towel_dryer": ("plumbing", "Полотенцесушитель", "Սրբիչի չորանոց", "Towel dryer"),
    "installation": ("plumbing", "Инсталляция", "Ինստալյացիա", "WC frame"),
    "pendant_light": ("lighting", "Подвесной светильник", "Կախովի լուսատու", "Pendant light"),
    "spot_light": ("lighting", "Точечный светильник", "Կետային լուսատու", "Spot light"),
    "track_light": ("lighting", "Трековая система", "Թրեքային համակարգ", "Track light"),
    "led_strip": ("lighting", "LED-лента", "LED ժապավեն", "LED strip"),
    "wall_light": ("lighting", "Бра", "Պատի լուսատու", "Wall light"),
    "floor_lamp": ("lighting", "Торшер", "Հատակի լամպ", "Floor lamp"),
    "door_interior": ("doors", "Межкомнатная дверь", "Միջսենյակային դուռ", "Interior door"),
    "door_sliding": ("doors", "Раздвижная дверь", "Սահող դուռ", "Sliding door"),
    "door_entrance": ("doors", "Входная дверь", "Մուտքի դուռ", "Entrance door"),
    "floor_parquet": ("finishing", "Паркет / инженерная доска", "Մանրահատակ", "Engineered wood"),
    "floor_laminate": ("finishing", "Ламинат", "Լամինատ", "Laminate"),
    "floor_tile": ("finishing", "Керамогранит пол", "Հատակի սալիկ", "Floor porcelain tile"),
    "wall_tile": ("finishing", "Плитка настенная", "Պատի սալիկ", "Wall tile"),
    "wall_paint": ("finishing", "Краска интерьерная", "Ներկ", "Interior paint"),
    "wall_panel": ("finishing", "Декоративные панели", "Դեկորատիվ պանելներ", "Wall panels"),
    "putty": ("finishing", "Шпаклёвка", "Ծեփամածիկ", "Putty"),
    "tile_adhesive": ("finishing", "Плиточный клей", "Սալիկի սոսինձ", "Tile adhesive"),
    "drywall": ("finishing", "Гипсокартон", "Գիպսաստվարաթուղթ", "Drywall"),
    "rug": ("decor", "Ковёр", "Գորգ", "Rug"),
    "curtains": ("decor", "Шторы", "Վարագույրներ", "Curtains"),
    "artwork": ("decor", "Декор / картины", "Դեկոր", "Artwork"),
    "mirror": ("decor", "Зеркало", "Հայելի", "Mirror"),
    "plant": ("decor", "Растения и кашпо", "Բույսեր", "Plants"),
}

GROUPS: dict[str, tuple[str, str, str]] = {
    "furniture": ("Мебель", "Կահույք", "Furniture"),
    "lighting": ("Освещение", "Լուսավորություն", "Lighting"),
    "plumbing": ("Сантехника", "Սանտեխնիկա", "Plumbing"),
    "finishing": ("Отделочные материалы", "Հարդարման նյութեր", "Finishing materials"),
    "doors": ("Двери", "Դռներ", "Doors"),
    "appliances": ("Техника", "Տեխնիկա", "Appliances"),
    "decor": ("Декор и текстиль", "Դեկոր և տեքստիլ", "Decor & textile"),
    "custom": ("Изделия на заказ", "Պատվերով իրեր", "Custom-made"),
    "works": ("Работы", "Աշխատանքներ", "Works"),
    "delivery": ("Доставка", "Առաքում", "Delivery"),
    "installation": ("Монтаж и сборка", "Մոնտաժ", "Installation"),
    "contingency": ("Резерв", "Պահուստ", "Contingency"),
}

STYLES: dict[str, dict] = {
    "warm_minimal": {"ru": "Тёплый минимализм", "hy": "Ջերմ մինիմալիզմ", "en": "Warm minimalism",
                      "subtitle": "Спокойный, уютный, вне времени", "palette": ["#efe6da", "#d9c9b7", "#b98f6a", "#8a5a3c", "#2e2e2e"]},
    "modern_loft": {"ru": "Современный лофт", "hy": "Ժամանակակից լոֆտ", "en": "Modern loft",
                     "subtitle": "Характер и свобода пространства", "palette": ["#3a3532", "#6b4a3a", "#a4593c", "#c9b8a3", "#1f1d1b"]},
    "soft_scandi": {"ru": "Мягкий сканди", "hy": "Փափուկ սկանդի", "en": "Soft Scandi",
                     "subtitle": "Лёгкость, свет и натуральные материалы", "palette": ["#f4f1ec", "#e3d8c8", "#c8b08f", "#8f9f7e", "#5c5248"]},
    "contemporary": {"ru": "Современный", "hy": "Ժամանակակից", "en": "Contemporary",
                      "subtitle": "Чистые линии и функциональность", "palette": ["#f2f0ed", "#cfc8bf", "#8c8279", "#c97f63", "#2e2e2e"]},
    "classic": {"ru": "Неоклассика", "hy": "Նեոդասական", "en": "Neoclassic",
                 "subtitle": "Молдинги, симметрия, благородные оттенки", "palette": ["#f3eee6", "#ddd2c2", "#b8a17f", "#7c6a55", "#3c352e"]},
}

TIERS = ["economy", "comfort", "business", "premium"]


def label(key: str, lang: str = "ru") -> str:
    c = CATEGORIES.get(key)
    if not c:
        return key
    return {"ru": c[1], "hy": c[2], "en": c[3]}.get(lang, c[1])


def group_of(key: str) -> str:
    return CATEGORIES.get(key, ("custom",))[0]


def group_label(key: str, lang: str = "ru") -> str:
    g = GROUPS.get(key)
    if not g:
        return key
    return {"ru": g[0], "hy": g[1], "en": g[2]}.get(lang, g[0])


# Source routing for external discovery (addon prompt §8 step 2)
SOURCE_ROUTING: dict[str, list[str]] = {
    "finishing": ["domus", "idealsystem", "nortun", "lideria", "effectgroup"],
    "plumbing": ["domus", "idealsystem", "nortun", "lideria", "vlv"],
    "doors": ["profal", "domus"],
    "appliances": ["vlv", "vega", "domus"],
    "furniture": ["vlv", "vega", "domus"],
    "lighting": ["domus", "vlv"],
    "decor": ["vega", "vlv", "domus"],
}
PAINT_AND_MIXES = {"wall_paint", "putty", "tile_adhesive"}


def sources_for(category: str) -> list[str]:
    if category in PAINT_AND_MIXES:
        return ["effectgroup", "domus", "nortun"]
    return SOURCE_ROUTING.get(group_of(category), ["domus"])
