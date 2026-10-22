"""Deterministic normalisation of external product data: prices, currencies,
units of sale, dimensions, categories, fingerprints and validation."""
from __future__ import annotations

import hashlib
import re

from .schema import NormalizedExternalProduct

# Fixed-rate snapshot; the estimator stores the snapshot used. Never mix currencies silently.
DEFAULT_FX_TO_AMD = {"AMD": 1.0, "USD": 387.0, "EUR": 452.0, "RUB": 4.8}


def parse_price(raw) -> tuple[float | None, str | None]:
    """'2 790 ֏' → (2790, 'AMD'); '1,240,000 AMD' → (1240000, 'AMD'); '$1,299.50' → (1299.5,'USD')."""
    if raw is None:
        return None, None
    if isinstance(raw, (int, float)):
        return float(raw), None
    s = str(raw).strip()
    cur = None
    if re.search(r"֏|AMD|դր|драм", s, re.I):
        cur = "AMD"
    elif "$" in s or re.search(r"USD", s, re.I):
        cur = "USD"
    elif "€" in s or re.search(r"EUR", s, re.I):
        cur = "EUR"
    elif "₽" in s or re.search(r"RUB|руб", s, re.I):
        cur = "RUB"
    digits = re.sub(r"[^\d.,]", "", s)
    if not digits:
        return None, cur
    # thousands separators: "1,240,000" / "1.240.000" / "1 240 000"; decimals: "1299.50" / "1299,50"
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", digits):
        val = float(re.sub(r"[.,]", "", digits))
    elif re.fullmatch(r"\d{1,3}(,\d{3})+\.\d{1,2}", digits):
        val = float(digits.replace(",", ""))
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+,\d{1,2}", digits):
        val = float(digits.replace(".", "").replace(",", "."))
    else:
        val = float(digits.replace(",", "."))
    return val, cur


def to_amd(value: float | None, currency: str | None, fx: dict | None = None) -> float | None:
    if value is None or currency is None:
        return None
    rate = (fx or DEFAULT_FX_TO_AMD).get(currency.upper())
    return round(value * rate, 0) if rate else None


UNIT_PATTERNS = [
    (r"(?:/|за|per|1)\s*(?:м²|м2|m²|m2|քմ|մ²|մ2|кв\.?\s*м)", "m2"),
    (r"(?:/|за|per)\s*(?:упак|уп\.|pack|տուփ)", "pack"),
    (r"(?:/|за|per)\s*(?:кг|kg|կգ)", "kg"),
    (r"(?:/|за|per)\s*(?:л|l|լ)\b", "l"),
    (r"(?:/|за|per)\s*(?:пог\.?\s*м|lm|գծ\.?\s*մ)", "m"),
]


def detect_unit(*texts: str | None) -> str:
    blob = " ".join(t for t in texts if t)
    for pat, unit in UNIT_PATTERNS:
        if re.search(pat, blob, re.I):
            return unit
    return "pcs"


def parse_package_coverage(text: str | None) -> float | None:
    """'1.44 м² в упаковке' / '1,44 մ²/տուփ' → 1.44"""
    if not text:
        return None
    m = re.search(r"(\d+[.,]?\d*)\s*(?:м²|м2|m²|m2|մ²|քմ)\s*(?:в\s*упак|/\s*упак|/\s*pack|/\s*տուփ|in\s*pack)", text, re.I)
    return float(m.group(1).replace(",", ".")) if m else None


_MM = {"мм": 1, "mm": 1, "մմ": 1, "см": 10, "cm": 10, "սմ": 10, "м": 1000, "m": 1000, "մ": 1000}


def parse_dimensions(text: str | None) -> dict:
    """Extracts dimensions from free text. Returns mm values; nothing is guessed."""
    out: dict = {}
    if not text:
        return out
    t = text.replace("×", "x").replace("Х", "x").replace("х", "x").replace("*", "x")
    m = re.search(r"(\d+[.,]?\d*)\s*x\s*(\d+[.,]?\d*)(?:\s*x\s*(\d+[.,]?\d*))?\s*(мм|mm|մմ|см|cm|սմ|м|m|մ)?\b", t, re.I)
    if m:
        unit = _MM.get((m.group(4) or "mm").lower(), 1)
        nums = [float(g.replace(",", ".")) * unit for g in m.groups()[:3] if g]
        if len(nums) == 2:
            out.update(tile_w_mm=nums[0], tile_h_mm=nums[1])
        else:
            out.update(width_mm=nums[0], depth_mm=nums[1], height_mm=nums[2])
        out["raw"] = m.group(0)
        return out
    m = re.search(r"(?:Ø|ø|диаметр|d=)\s*(\d+)\s*(мм|mm|մմ|см|cm)?", t, re.I)
    if m:
        out["diameter_mm"] = float(m.group(1)) * _MM.get((m.group(2) or "mm").lower(), 1)
        out["raw"] = m.group(0)
    m = re.search(r"(\d+)\s*/\s*(\d+)\s*(մմ|мм|mm)", t)
    if m and "diameter_mm" not in out:
        out["diameter_mm"] = float(m.group(1))
        out["raw"] = m.group(0)
    return out


AVAILABILITY_MAP = {
    "instock": "in_stock", "in_stock": "in_stock", "https://schema.org/instock": "in_stock", "http://schema.org/instock": "in_stock",
    "outofstock": "out_of_stock", "https://schema.org/outofstock": "out_of_stock", "soldout": "out_of_stock",
    "preorder": "to_order", "backorder": "to_order", "madetoorder": "to_order", "https://schema.org/preorder": "to_order",
    "limitedavailability": "in_stock", "https://schema.org/limitedavailability": "in_stock",
}


def normalize_availability(raw: str | None) -> str:
    if not raw:
        return "unknown"
    return AVAILABILITY_MAP.get(str(raw).strip().lower().replace(" ", ""), "unknown")


# Keyword classifier (HY/RU/EN). Deterministic; an LLM may only propose, never override silently.
CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    # "built-in" alone (ներկառուցվող / встраив) also describes ovens, hobs and washbasins → needs a light word ("a+b" = all parts)
    ("spot_light", ["downlight", "spotlight", "точечн", "спот", "ներկառուցվող+լուսատու", "встраив+светильник", "recessed+light", "led պանել", "led панел", "led panel"]),
    ("pendant_light", ["կախովի", "подвес", "pendant"]),
    ("led_strip", ["led ժապավեն", "лента", "led strip"]),
    ("wall_light", ["բրա", "бра", "wall lamp", "настенный светильник"]),
    ("floor_tile", ["керамогранит", "porcelain", "կերամոգրանիտ", "напольная плитка", "հատակի սալիկ"]),
    ("wall_tile", ["настенная плитка", "wall tile", "պատի սալիկ", "мозаик", "mosaic", "խճանկար"]),
    ("floor_parquet", ["паркет", "инженерная доска", "parquet", "մանրահատակ"]),
    ("floor_laminate", ["ламинат", "laminate", "լամինատ"]),
    ("wall_paint", ["краска", "paint", "ներկ"]),
    ("tile_adhesive", ["плиточный клей", "tile adhesive", "սալիկի սոսինձ"]),
    ("putty", ["шпаклев", "шпаклёв", "putty", "ծեփամածիկ"]),
    ("toilet", ["унитаз", "toilet", "զուգարանակոնք"]),
    ("vanity", ["тумба с раковиной", "раковин", "vanity", "washbasin", "լվացարան"]),
    ("bathtub", ["ванна ", "bathtub", "լոգարան"]),
    ("shower", ["душев", "shower", "ցնցուղ"]),
    ("faucet", ["смесител", "faucet", "mixer", "ծորակ"]),
    ("towel_dryer", ["полотенцесуш", "towel", "սրբիչ"]),
    ("fridge", ["холодильник", "refrigerator", "fridge", "սառնարան"]),
    ("washer", ["стиральн", "washing machine", "լվացքի մեքենա"]),
    ("dishwasher", ["посудомо", "dishwasher", "սպասք լվաց"]),  # «սպասք» alone = dishware
    ("cooktop", ["варочн", "cooktop", "hob", "եփման"]),
    ("oven", ["духов", "oven", "ջեռոց"]),
    ("hood", ["вытяжк", "hood", "օդաքարշ"]),
    ("tv_unit", ["тумба под тв", "тв-тумба", "tv stand", "tv unit", "tv cabinet", "հեռուստացույցի տակդիր", "tv տումբա"]),
    ("tv", ["телевизор", "tv ", "հեռուստացույց"]),
    ("sofa", ["диван", "sofa", "բազմոց"]),
    ("armchair", ["кресло", "armchair", "բազկաթոռ"]),
    ("bed", ["кровать", "bed", "մահճակալ"]),
    ("wardrobe", ["шкаф", "wardrobe", "պահարան"]),
    ("dining_table", ["обеденный стол", "dining table", "ճաշասեղան"]),
    ("dining_chair", ["стул", "chair", "աթոռ"]),
    ("door_interior", ["межкомнатн", "interior door", "միջսենյակային"]),
    ("door_entrance", ["входная дверь", "entrance door", "մուտքի դուռ"]),
]


# Words that disqualify a category match (wine cooler is not a fridge, a bath panel is not a bath…)
CATEGORY_EXCLUDE: dict[str, list[str]] = {
    "fridge": ["գինու", "wine", "винн", "винный", "mini bar", "мини-бар"],
    "wall_paint": ["ներկառուցվ"],  # «ներկ» (paint) is also the stem of «ներկառուցվող» (built-in)
    "bathtub": ["էկրան", "экран", "panel", "панель", "шторк", "վարագույր"],
    "bed": ["բաժակ", "стакан", "glass", "постельн", "белье", "սպիտակեղեն"],
    "dining_chair": ["կոմպյուտերային", "компьютерн", "gaming"],
    "wardrobe": ["шкаф для обуви", "կոշիկ", "օդաքա", "вытяж"],  # «hood cabinet» is a cooker hood
    "tv": ["кронштейн", "bracket", "пульт"],
}


def classify(*texts: str | None) -> str | None:
    blob = " ".join(t for t in texts if t).lower()
    for cat, words in CATEGORY_KEYWORDS:
        if any(all(part in blob for part in w.split("+")) for w in words) and not any(x in blob for x in CATEGORY_EXCLUDE.get(cat, [])):
            return cat
    return None


ACCESSORY_WORDS = ["կախիչ", "tv mount", "wall mount", "крепление для тв", "ֆիլտր", "фильтр", "filter", "բաժանարար", "разветвит", "splitter",
                   "кабель", "cable", "մալուխ", "կափարիչ", "крышка", "cover", "кронштейн", "bracket", "запчаст", "spare", "адаптер", "adapter", "ремкомплект", "заглушк", "плафон для", "лампа для",
                   "էկրան լոգ", "экран для ванн", "bath panel", "сифон", "սիֆոն", "кнопка смыва", "ножк", "уплотнит"]


def is_accessory(name: str | None, category: str | None = None) -> bool:
    """Accessories/spare parts (mounts, filters, cables, covers…) must not be offered as the main product.
    The store's own category is checked too: VLV names are often bare model codes."""
    n = f"{name or ''} {category or ''}".lower()
    return any(w in n for w in ACCESSORY_WORDS)


def fingerprint(source_key: str, brand: str | None, model: str | None, variant: str | None) -> str:
    raw = "|".join((source_key, (brand or "").strip().lower(), (model or "").strip().lower(), (variant or "").strip().lower()))
    return "fp_" + hashlib.sha256(raw.encode()).hexdigest()[:24]


def validate(p: NormalizedExternalProduct) -> NormalizedExternalProduct:
    """Adds warnings, computes confidence, sets manual/quote flags."""
    w = list(p.validation_warnings)
    score = 1.0
    if p.price_value is None:
        p.quote_required = True
        w.append("Цена не указана — требуется запрос поставщику")
        score -= 0.25
    if p.price_value is not None and not p.original_currency:
        w.append("Валюта цены не определена")
        p.manual_confirmation_required = True
        score -= 0.3
    if p.original_currency and p.original_currency != "AMD" and p.price_amd is None:
        w.append("Нет курса для пересчёта в AMD")
        score -= 0.2
    if p.availability_status == "unknown":
        w.append("Наличие не подтверждено")
        score -= 0.15
    if not p.sku and not p.external_product_id:
        w.append("Нет SKU/артикула — используется fingerprint")
        score -= 0.1
    if not p.normalized_category:
        w.append("Категория не распознана")
        p.manual_confirmation_required = True
        score -= 0.2
    if p.old_price and p.price_value and p.old_price <= p.price_value:
        p.disputed_fields["old_price"] = {"old": p.old_price, "current": p.price_value}
        w.append("Старая цена не больше текущей — поле спорное")
        score -= 0.1
    if p.unit_of_sale in ("m2", "pack") and p.normalized_category in ("floor_tile", "wall_tile", "floor_parquet", "floor_laminate") and p.unit_of_sale == "pack" and not p.package_coverage_m2:
        w.append("Цена за упаковку без площади упаковки — расчёт количества невозможен")
        p.manual_confirmation_required = True
        score -= 0.2
    if p.disputed_fields:
        p.manual_confirmation_required = True
    p.validation_warnings = w
    p.confidence = round(max(0.0, min(1.0, score)), 2)
    return p
