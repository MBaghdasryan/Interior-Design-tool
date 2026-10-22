"""Rule-based development handlers used when no AI provider key is configured.
They are deterministic and conservative: anything not understood is reported as
unsupported instead of guessed."""
from __future__ import annotations

import json
import re

from .providers import LLMRequest

ROOM_WORDS = {
    "hallway": ["коридор", "прихож", "նախասենյակ", "hall"],
    "kitchen_living": ["кухн", "խոհանոց", "kitchen", "столов"],
    "living": ["гостин", "հյուրասենյակ", "living"],
    "bedroom": ["спальн", "ննջասենյակ", "bedroom"],
    "kids": ["детск", "մանկական", "kids"],
    "bathroom": ["ванн", "санузел", "сануз", "լոգարան", "սանհանգույց", "bath"],
    "wardrobe": ["гардероб"],
}
CATEGORY_WORDS = {
    "sofa": ["диван", "բազմոց", "sofa"], "bed": ["кроват", "մահճակալ", "bed"], "dining_table": ["стол обеден", "обеденный стол", "стол"],
    "dining_chair": ["стул"], "wardrobe": ["шкаф", "պահարան", "wardrobe"], "rug": ["ковёр", "ковер"], "armchair": ["кресло"],
    "tv_unit": ["тв-тумб", "тумбу под тв", "тв тумб"], "floor_parquet": ["паркет", "пол "], "wall_paint": ["стены", "краск"],
    "pendant_light": ["люстр", "подвес", "свет"], "kitchen_run": ["гарнитур", "кухню"],
}


def _rooms_in(text: str) -> list[str]:
    return [rt for rt, ws in ROOM_WORDS.items() if any(w in text for w in ws)]


def _cat_in(text: str) -> str | None:
    for cat, ws in CATEGORY_WORDS.items():
        if any(w in text for w in ws):
            return cat
    return None


def change_command(req: LLMRequest) -> dict:
    ctx = json.loads(req.user)
    text = ctx["command"].lower()
    parts = re.split(r"[,.;]| и | а также |\n", text)
    ops, unsupported = [], []
    for raw in parts:
        p = raw.strip()
        if not p:
            continue
        rooms = _rooms_in(p)
        room = rooms[0] if rooms else None
        if room == "kitchen_living" and "kitchen_living" not in ctx.get("room_types", []) and "kitchen" in ctx.get("room_types", []):
            room = "kitchen"
        cat = _cat_in(p)
        m = re.search(r"бюджет\w*\s+на\s+(\d[\d\s]{2,})", p)
        if m and re.search(r"сократ|уменьш|сниз|урез|меньше|дешевле", p):
            num = int(re.sub(r"\D", "", m.group(1)))
            ops.append({"op": "budget_delta", "params": {"delta_amd": -num}, "explanation": f"Снизить смету на {num:,} AMD".replace(",", " ")})
            continue
        if "светлее" in p or "светл" in p and "сделай" in p:
            ops.append({"op": "lighter", "room_type": room, "explanation": "Светлые отделка и мебель"})
            continue
        if "темнее" in p:
            ops.append({"op": "darker", "room_type": room, "explanation": "Более тёмная палитра"})
            continue
        if "компакт" in p or "меньше" in p and cat:
            mw = re.search(r"(\d{3,4})\s*(?:мм|mm)", p)
            mcm = re.search(r"(\d{2,3})\s*(?:см|cm)", p)
            width = int(mw.group(1)) if mw else (int(mcm.group(1)) * 10 if mcm else None)
            ops.append({"op": "make_compact", "room_type": room, "category": cat or "sofa", "params": {"max_width_mm": width}, "explanation": "Заменить на более компактную модель"})
            continue
        if p.startswith(("добав", "постав")) or " добав" in p:
            closed = "закрыт" in p
            c = cat or ("wardrobe" if "шкаф" in p else None)
            if c == "wardrobe" and room == "hallway":
                c = "hallway_wardrobe"
            if c:
                ops.append({"op": "add_object", "room_type": room, "category": c, "params": {"closed_storage": closed or None}, "explanation": "Добавить предмет"})
                continue
        if p.startswith(("убер", "удали", "убрать")):
            if cat:
                ops.append({"op": "remove_object", "room_type": room, "category": cat, "explanation": "Убрать предмет"})
                continue
        if "дешевле" in p or "бюджетн" in p:
            ops.append({"op": "cheaper", "room_type": room, "category": cat, "explanation": "Подобрать более дешёвый аналог"})
            continue
        if "дороже" in p or "премиум" in p:
            ops.append({"op": "premium", "room_type": room, "category": cat, "explanation": "Подобрать аналог выше классом"})
            continue
        if p.startswith(("замени", "поменя")) and cat:
            ops.append({"op": "replace_product", "room_type": room, "category": cat, "explanation": "Заменить на следующий по рейтингу аналог"})
            continue
        unsupported.append(raw.strip())
    summary = "; ".join(o["explanation"] for o in ops) or "Изменения не распознаны"
    return {"operations": [{"params": {}, "room_type": None, "room_id": None, "category": None, **o} for o in ops], "summary": summary, "unsupported": unsupported}


def design_brief(req: LLMRequest) -> dict:
    ctx = json.loads(req.user)
    prefs = ctx.get("preferences", {})
    text = (ctx.get("interview") or "").lower()
    styles = list(prefs.get("styles") or [])
    for key, words in {"warm_minimal": ["минимал", "тёпл", "тепл"], "modern_loft": ["лофт", "кирпич"], "soft_scandi": ["сканди", "светл"], "classic": ["классик", "молдинг"]}.items():
        if any(w in text for w in words) and key not in styles:
            styles.append(key)
    tier = prefs.get("budget_tier") or "comfort"
    fam = prefs.get("family") or ""
    household = {"adults": 1 if fam == "single" else 2, "children": 1 if fam == "kids" or "дет" in text else 0, "elderly": 0, "pets": ["кошка"] if "кош" in text else (["собака"] if "собак" in text else [])}
    assumptions = []
    if not styles:
        assumptions.append("Стиль не указан — ИИ предложит три стилистических варианта")
    if not prefs.get("budget_tier"):
        assumptions.append("Бюджет не указан — принят уровень «Комфорт»")
    return {
        "household": household, "rooms_program": [], "styles": styles[:3], "colors_like": prefs.get("colors", []), "colors_avoid": [],
        "budget_tier": tier, "budget_amd": prefs.get("budget_amd"), "storage_level": "high" if "хранен" in text else "medium",
        "work_from_home": "работ" in text and "дом" in text, "keep_items": prefs.get("keep_items", []), "preferred_suppliers": prefs.get("suppliers", []),
        "only_in_stock": bool(prefs.get("only_in_stock")), "max_weeks": prefs.get("max_weeks"), "eco_materials": False, "replanning_allowed": True,
        "finish_level": "standard", "notes": ctx.get("interview", "")[:500], "assumptions": assumptions,
    }


def variant_copy(req: LLMRequest) -> dict:
    ctx = json.loads(req.user)
    return {"title": ctx["style_title"], "subtitle": ctx["style_subtitle"],
            "description": f"{ctx['style_title']}: {ctx.get('materials', 'натуральные материалы')}, продуманное хранение и сценарии освещения. Уровень — {ctx['tier_title']}."}


def floorplan_vision(req: LLMRequest) -> dict:
    # Without a vision provider we cannot read a raster plan. Return an empty draft
    # with an explicit uncertainty — the UI then switches to manual tracing.
    return {"scale_source": "assumed", "walls": [], "openings": [], "rooms": [], "dimension_texts": [], "ceiling_height_mm": None,
            "uncertainties": ["Распознавание растрового плана требует подключённого AI-провайдера (OPENAI/ANTHROPIC/GEMINI). Постройте план вручную или загрузите DXF/DWG/IFC."]}


def render_grounding(req: LLMRequest) -> dict:
    """No vision without a provider: every item is reported as not verified (score 0), never as a match."""
    import json

    manifest = json.loads(req.user).get("manifest", [])
    return {"items": [{"code": it["code"], "visible": False, "type_match": 0, "color_match": 0, "position_match": 0, "note": "not verified (no vision provider)"}
                      for it in manifest], "extra_objects": []}


def _count(req: LLMRequest) -> int:
    return len(req.images)


def photo_rooms(req: LLMRequest) -> dict:
    """No vision: nothing is recognised (unknown, confidence 0) — never a fake room type."""
    return {"photos": [{"index": i, "room_type": "unknown", "confidence": 0.0} for i in range(_count(req))]}


def photo_elements(req: LLMRequest) -> dict:
    return {"photos": [{"index": i, "notes": "не распознано: нет vision-провайдера"} for i in range(_count(req))]}


def view_groups(req: LLMRequest) -> dict:
    return {"rooms": [{"room_type": "unknown", "photo_indexes": list(range(_count(req))), "confidence": 0.0}],
            "uncertainties": ["Фото не проанализированы: vision-провайдер недоступен"]}


HANDLERS = {"change_command": change_command, "design_brief": design_brief, "variant_copy": variant_copy, "floorplan_vision": floorplan_vision, "render_grounding": render_grounding, "photo_rooms": photo_rooms, "photo_elements": photo_elements, "view_groups": view_groups}
