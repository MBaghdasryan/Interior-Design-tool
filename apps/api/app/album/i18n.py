"""Album vocabulary (HY default, as in professional Armenian albums; RU and EN)."""
from __future__ import annotations

import json
from functools import cache
from pathlib import Path

T: dict[str, dict[str, str]] = {
    "album_title": {"hy": "ԲՆԱԿԱՐԱՆԻ ԴԻԶԱՅՆ ՆԱԽԱԳԻԾ", "ru": "ДИЗАЙН-ПРОЕКТ КВАРТИРЫ", "en": "APARTMENT DESIGN PROJECT"},
    "code": {"hy": "ԴՆ", "ru": "ДП", "en": "DP"},
    "toc": {"hy": "Բովանդակություն", "ru": "Содержание", "en": "Contents"},
    "section": {"hy": "Բաժին", "ru": "Раздел", "en": "Section"},
    "page": {"hy": "Էջ", "ru": "Лист", "en": "Sheet"},
    "name": {"hy": "Անուն", "ru": "Наименование", "en": "Name"},
    "sec1": {"hy": "Ինժեներական", "ru": "Инженерный", "en": "Engineering"},
    "sec2": {"hy": "Հարդարում", "ru": "Отделка", "en": "Finishing"},
    "sec3": {"hy": "Փռվածքներ", "ru": "Развёртки", "en": "Elevations"},
    "sec4": {"hy": "Վիզուալացում", "ru": "Визуализация", "en": "Visualisation"},
    "sec5": {"hy": "Սպեցիֆիկացիա և նախահաշիվ", "ru": "Спецификация и смета", "en": "Specification & estimate"},
    "project_address": {"hy": "Նախագծի հասցե", "ru": "Адрес объекта", "en": "Project address"},
    "client": {"hy": "Պատվիրատու", "ru": "Заказчик", "en": "Client"},
    "designer": {"hy": "Դիզայներ", "ru": "Дизайнер", "en": "Designer"},
    "legend": {"hy": "Պայմանական նշաններ", "ru": "Условные обозначения", "en": "Legend"},
    "sheet_name": {"hy": "Թերթի անվանումը", "ru": "Наименование листа", "en": "Sheet title"},
    "sheet_no": {"hy": "Թերթի համար", "ru": "Номер листа", "en": "Sheet no."},
    "format": {"hy": "Չափս", "ru": "Формат", "en": "Format"},
    "scale": {"hy": "Մ", "ru": "М", "en": "S"},
    "area": {"hy": "Մակերես(քմ)", "ru": "Площадь (м²)", "en": "Area (m²)"},
    "total": {"hy": "Ընդամենը", "ru": "Итого", "en": "Total"},
    "ceiling_h": {"hy": "Առաստաղի բարձրություն", "ru": "Высота потолка", "en": "Ceiling height"},
    # sheet titles
    "s_measure": {"hy": "Չափագրություն", "ru": "Обмерный план", "en": "Measured survey"},
    "s_demolish": {"hy": "Դեմոնտաժվող պատեր", "ru": "План демонтажа", "en": "Demolition plan"},
    "s_new": {"hy": "Նոր էլեմենտներ", "ru": "План возводимых перегородок", "en": "New partitions"},
    "s_axo": {"hy": "Դեմոնտաժվող և մոնտաժվող պատերի եռաչափ տեսք", "ru": "Аксонометрия демонтажа и монтажа", "en": "Demolition & construction axonometry"},
    "s_zoning": {"hy": "Զոնավորում", "ru": "Функциональное зонирование", "en": "Zoning"},
    "s_plumbing": {"hy": "Ջրամատակարարման, ջրահեռացման և ջեռուցման հատակագիծ", "ru": "План водоснабжения, канализации и отопления", "en": "Plumbing & heating plan"},
    "s_drywall_plan": {"hy": "Գիպսաստվարաթղթե պատերի հատակագիծ", "ru": "План перегородок из ГКЛ", "en": "Drywall partitions plan"},
    "s_drywall": {"hy": "Գիպսաստվարաթղթե պատեր", "ru": "Перегородки из ГКЛ — ведомость и узел", "en": "Drywall partitions"},
    "s_sockets": {"hy": "Վարդակների և անջատիչների հատակագիծ", "ru": "План розеток и выключателей", "en": "Sockets & switches plan"},
    "s_sockets_list": {"hy": "Վարդակների և անջատիչների ցանկ", "ru": "Ведомость розеток и выключателей", "en": "Sockets & switches schedule"},
    "s_lighting": {"hy": "Լուսավորության հատակագիծ", "ru": "План освещения", "en": "Lighting plan"},
    "s_lighting_list": {"hy": "Լուսավորություն", "ru": "Ведомость светильников", "en": "Lighting schedule"},
    "s_ceiling": {"hy": "Առաստաղի հատակագիծ", "ru": "План потолков", "en": "Ceiling plan"},
    "s_ceiling_nodes": {"hy": "Առաստաղի հանգույցներ", "ru": "Узлы потолков", "en": "Ceiling details"},
    "s_floors": {"hy": "Հատակների հատակագիծ", "ru": "План полов", "en": "Floor plan"},
    "s_doors": {"hy": "Դռների ցուցակ", "ru": "Ведомость дверей", "en": "Door schedule"},
    "s_walls": {"hy": "Պատերի հարդարման հատակագիծ", "ru": "План отделки стен", "en": "Wall finishes plan"},
    "s_materials": {"hy": "Նյութեր", "ru": "Материалы", "en": "Materials"},
    "s_furniture_plan": {"hy": "Կահավորման հատակագիծ", "ru": "План расстановки мебели", "en": "Furniture plan"},
    "s_furniture": {"hy": "Կահավորում", "ru": "Ведомость мебели и оборудования", "en": "Furniture schedule"},
    "s_elev_key": {"hy": "Հատակագիծ", "ru": "План-схема развёрток", "en": "Elevation key plan"},
    "s_visual": {"hy": "Վիզուալացում", "ru": "Визуализация", "en": "Visualisation"},
    "s_spec": {"hy": "Սպեցիֆիկացիա", "ru": "Спецификация", "en": "Specification"},
    "s_estimate": {"hy": "Նախահաշիվ", "ru": "Смета", "en": "Estimate"},
    "s_suppliers": {"hy": "Մատակարարներ և ժամկետներ", "ru": "Поставщики, сроки, 3D-сцена", "en": "Suppliers, lead times, 3D"},
    "s_approval": {"hy": "Ստուգումներ և հաստատում", "ru": "Проверки и утверждение", "en": "Checks & approval"},
    # legends
    "existing_wall": {"hy": "Գոյություն ունեցող պատ", "ru": "Существующая стена", "en": "Existing wall"},
    "demolish_wall": {"hy": "Քանդվող պատ", "ru": "Демонтируемая стена", "en": "Wall to demolish"},
    "new_wall": {"hy": "Նոր պատ", "ru": "Возводимая перегородка", "en": "New partition"},
    "drywall": {"hy": "Գիպսաստվարաթուղթ", "ru": "ГКЛ", "en": "Drywall"},
    "zone_day": {"hy": "Օրվա գոտի", "ru": "Дневная зона", "en": "Day zone"},
    "zone_night": {"hy": "Գիշերային գոտի", "ru": "Ночная зона", "en": "Night zone"},
    "zone_wet": {"hy": "Խոնավ գոտի", "ru": "Мокрая зона", "en": "Wet zone"},
    "zone_service": {"hy": "Սպասարկման գոտի", "ru": "Служебная зона", "en": "Service zone"},
    "zone_outdoor": {"hy": "Պատշգամբ", "ru": "Балкон / лоджия", "en": "Balcony"},
    "cold_water": {"hy": "Սառը ջուր", "ru": "Холодная вода", "en": "Cold water"},
    "hot_water": {"hy": "Տաք ջուր", "ru": "Горячая вода", "en": "Hot water"},
    "sewer": {"hy": "Կոյուղի", "ru": "Канализация", "en": "Drain"},
    "radiator": {"hy": "Ռադիատոր", "ru": "Радиатор", "en": "Radiator"},
    "warm_floor": {"hy": "Տաք հատակ", "ru": "Тёплый пол", "en": "Underfloor heating"},
    "riser": {"hy": "Ստոյակ", "ru": "Стояк", "en": "Riser"},
    "height": {"hy": "Բարձրություն", "ru": "Высота", "en": "Height"},
    "qty": {"hy": "Քանակ", "ru": "Кол-во", "en": "Qty"},
    "room": {"hy": "Սենյակ", "ru": "Помещение", "en": "Room"},
    "note": {"hy": "Նշումներ", "ru": "Примечание", "en": "Notes"},
    "type": {"hy": "Տեսակ", "ru": "Тип", "en": "Type"},
    "power": {"hy": "Հզորություն", "ru": "Мощность", "en": "Power"},
    "scenario": {"hy": "Սցենար", "ru": "Сценарий", "en": "Scenario"},
    "group": {"hy": "Խումբ", "ru": "Группа", "en": "Group"},
    "product": {"hy": "Ապրանք", "ru": "Товар", "en": "Product"},
    "supplier": {"hy": "Մատակարար", "ru": "Поставщик", "en": "Supplier"},
    "price": {"hy": "Գին", "ru": "Цена", "en": "Price"},
    "sum": {"hy": "Գումար", "ru": "Сумма", "en": "Amount"},
    "dims": {"hy": "Չափսեր", "ru": "Размеры", "en": "Dimensions"},
    "status": {"hy": "Կարգավիճակ", "ru": "Статус", "en": "Status"},
    "size": {"hy": "Չափս Լ×Բ", "ru": "Размер Ш×В", "en": "Size W×H"},
    "opening_dir": {"hy": "Բացման ուղղություն", "ru": "Направление открывания", "en": "Swing"},
    "plan_view": {"hy": "Տեսք հատակագծում", "ru": "Вид в плане", "en": "Plan view"},
    "elev_view": {"hy": "Տեսք", "ru": "Вид", "en": "Elevation"},
    "length": {"hy": "Երկարություն", "ru": "Длина", "en": "Length"},
    "profile": {"hy": "Պրոֆիլ", "ru": "Профиль", "en": "Profile"},
    "layers": {"hy": "Շերտեր", "ru": "Обшивка", "en": "Boards"},
    "ceiling_type": {"hy": "Առաստաղի տեսակ", "ru": "Тип потолка", "en": "Ceiling type"},
    "floor_material": {"hy": "Հատակի ծածկույթ", "ru": "Напольное покрытие", "en": "Floor finish"},
    "wall_finish": {"hy": "Պատերի հարդարում", "ru": "Отделка стен", "en": "Wall finish"},
    "schematic_note": {"hy": "Սխեմատիկ վիզուալացում՝ ստեղծված նախագծի 3D մոդելից", "ru": "Схематическая визуализация из 3D-модели проекта (фотореалистичный рендер — после подключения рендер-провайдера)",
                       "en": "Schematic view generated from the project 3D model"},
    "demo_note": {"hy": "DEMO տվյալներ — ոչ իրական առաջարկներ", "ru": "DEMO-данные демонстрационного каталога — не реальные предложения", "en": "DEMO catalogue data — not real offers"},
}

CEILING_TYPES = {
    "paint": {"hy": "Ներկված սալ", "ru": "Окраска по плите", "en": "Painted slab"},
    "gkl_flat": {"hy": "Գիպսաստվարաթղթե հարթ", "ru": "ГКЛ одноуровневый", "en": "Flat drywall"},
    "gkl_multilevel": {"hy": "Բազմաստիճան ԳՍԹ", "ru": "ГКЛ многоуровневый с LED-нишей", "en": "Multi-level drywall + LED cove"},
    "stretch": {"hy": "Ձգվող առաստաղ", "ru": "Натяжной", "en": "Stretch ceiling"},
    "shadow_gap": {"hy": "Ստվերային կարով ԳՍԹ", "ru": "ГКЛ с теневым швом", "en": "Drywall with shadow gap"},
    "cove": {"hy": "LED քիվ", "ru": "LED-карниз", "en": "LED cove"},
}

ROOM_NAMES = {
    "living": {"hy": "Հյուրասենյակ", "ru": "Гостиная", "en": "Living room"},
    "kitchen": {"hy": "Խոհանոց", "ru": "Кухня", "en": "Kitchen"},
    "kitchen_living": {"hy": "Խոհանոց-հյուրասենյակ", "ru": "Кухня-гостиная", "en": "Kitchen-living"},
    "bedroom": {"hy": "Ննջասենյակ", "ru": "Спальня", "en": "Bedroom"},
    "kids": {"hy": "Մանկական", "ru": "Детская", "en": "Kids room"},
    "bathroom": {"hy": "Սանհանգույց", "ru": "Санузел", "en": "Bathroom"},
    "wc": {"hy": "Զուգարան", "ru": "Туалет", "en": "WC"},
    "hallway": {"hy": "Նախասենյակ", "ru": "Прихожая", "en": "Hallway"},
    "wardrobe": {"hy": "Հանդերձարան", "ru": "Гардеробная", "en": "Walk-in closet"},
    "balcony": {"hy": "Պատշգամբ", "ru": "Балкон", "en": "Balcony"},
    "office": {"hy": "Աշխատասենյակ", "ru": "Кабинет", "en": "Study"},
    "storage": {"hy": "Պահեստ", "ru": "Кладовая", "en": "Storage"},
    "laundry": {"hy": "Լվացքատուն", "ru": "Постирочная", "en": "Laundry"},
}

ELEC = {
    "socket": ("Վարդակ", "Розетка", "Socket"), "socket_double": ("Կրկնակի վարդակ", "Розетка двойная", "Double socket"),
    "socket_triple": ("Եռակի վարդակ", "Блок 3 розеток", "Triple socket"), "socket_waterproof": ("IP44 վարդակ", "Розетка IP44", "IP44 socket"),
    "socket_power": ("Ուժային վարդակ", "Силовая розетка", "Power socket"), "tv": ("TV", "TV", "TV"), "data": ("LAN", "LAN", "LAN"),
    "switch": ("Անջատիչ", "Выключатель", "Switch"), "switch_double": ("Կրկնակի անջատիչ", "Выкл. 2-клав.", "2-gang switch"),
    "switch_pass": ("Անցողիկ անջատիչ", "Проходной выкл.", "2-way switch"), "thermostat": ("Ջերմակարգավորիչ", "Терморегулятор", "Thermostat"),
    "hood": ("Օդաքարշ", "Вытяжка", "Hood"), "oven": ("Ջեռոց", "Духовой шкаф", "Oven"), "cooktop": ("Եփման վահանակ", "Варочная панель", "Cooktop"),
    "dishwasher": ("Սպասք լվացող", "ПММ", "Dishwasher"), "washer": ("Լվացքի մեքենա", "Стиральная машина", "Washing machine"),
    "boiler": ("Կաթսա", "Бойлер", "Boiler"), "fridge": ("Սառնարան", "Холодильник", "Fridge"),
}


def elec_label(kind: str, lang: str) -> str:
    v = ELEC.get(kind)
    return v[{"hy": 0, "ru": 1, "en": 2}.get(lang, 1)] if v else kind


# Sheet phrases (format strings). Units are words too: Armenian albums write մմ / մ / մ².
TX: dict[str, dict[str, str]] = {
    "u_mm": {"hy": "մմ", "ru": "мм", "en": "mm"}, "u_m": {"hy": "մ", "ru": "м", "en": "m"}, "u_m2": {"hy": "մ²", "ru": "м²", "en": "m²"},
    "days": {"hy": "{n} օր", "ru": "{n} дн.", "en": "{n} d"},
    "slab_to_slab": {"hy": "{h} մմ (սալից սալ)", "ru": "{h} мм (от плиты до плиты)", "en": "{h} mm (slab to slab)"},
    "riser_w": {"hy": "ՋՍ1", "ru": "СТ.В1", "en": "WR1"}, "riser_s": {"hy": "ԿՍ1", "ru": "СТ.К1", "en": "SR1"},
    "gkl": {"hy": "Գ", "ru": "Г", "en": "D"}, "door": {"hy": "Դ", "ru": "Д", "en": "D"}, "left": {"hy": "Ձ", "ru": "Л", "en": "L"}, "right": {"hy": "Ա", "ru": "П", "en": "R"},
    "gkl_box": {"hy": "ԳՍԹ արկղ", "ru": "Короб ГКЛ", "en": "Drywall box-out"},
    "gkl_profile": {"hy": "ՊՍ 75×50 / ՊՆ 75×40, քայլը 600", "ru": "ПС 75×50 / ПН 75×40, шаг 600", "en": "CW 75×50 / UW 75×40, 600 c/c"},
    "gkl_layers": {"hy": "2×ԳՍԹ 12.5 մմ (խոնավ գոտիներում՝ խոնավակայուն) + հանքային բամբակ 50", "ru": "2×ГКЛ 12.5 мм (ГКЛВ в мокрых зонах) + минвата 50",
                   "en": "2×12.5 mm board (moisture-resistant in wet zones) + 50 mineral wool"},
    "gkl_node": {"hy": "ԳՍԹ միջնապատի հանգույց (կտրվածք)", "ru": "Узел перегородки ГКЛ (разрез)", "en": "Drywall partition detail (section)"},
    "gkl_n1": {"hy": "1. ԳՍԹ 12.5 մմ — 2 շերտ յուրաքանչյուր կողմից, կարերը՝ շախմատաձև", "ru": "1. ГКЛ 12.5 мм — 2 слоя с каждой стороны, швы вразбежку",
               "en": "1. 12.5 mm board — 2 layers each side, staggered joints"},
    "gkl_n2": {"hy": "2. Պրոֆիլ ՊՍ 75×50, քայլը 600 մմ; ՊՆ 75×40 հատակին և առաստաղին՝ դեմպֆեր ժապավենով", "ru": "2. Профиль ПС 75×50, шаг 600 мм; ПН 75×40 по полу и потолку на демпферной ленте",
               "en": "2. CW 75×50 studs at 600 mm; UW 75×40 on floor and ceiling on isolation tape"},
    "gkl_n3": {"hy": "3. Ձայնամեկուսացում — հանքային բամբակ 50 մմ", "ru": "3. Звукоизоляция — минеральная вата 50 мм", "en": "3. Acoustic insulation — 50 mm mineral wool"},
    "gkl_n4": {"hy": "4. Խոնավ գոտիներում՝ խոնավակայուն ԳՍԹ + հիդրոմեկուսացում հատակից 200 մմ (ցնցուղում՝ ամբողջ բարձրությամբ)",
               "ru": "4. В мокрых зонах — ГКЛВ + гидроизоляция на 200 мм вверх от пола (в душе — на всю высоту)",
               "en": "4. Wet zones — moisture-resistant board + waterproofing 200 mm up from floor (full height in showers)"},
    "gkl_n5": {"hy": "5. Կախովի կահույքի և TV-ի ներդիրներ — ձող 50×40 / OSB 12 մմ՝ ըստ փռվածքների", "ru": "5. Закладные под навесную мебель и ТВ — брус 50×40 / OSB 12 мм по разметке развёрток",
               "en": "5. Backing for wall cabinets and TV — 50×40 timber / 12 mm OSB per elevations"},
    "el_n1": {"hy": "* Բարձրությունները՝ մաքուր հատակից մինչև վարդակի/անջատիչի առանցքը", "ru": "* Высоты указаны от чистового пола до оси розетки/выключателя",
              "en": "* Heights are from finished floor to socket/switch centre"},
    "el_n2": {"hy": "* Սանհանգույցի վարդակները — IP44, ՊԱՍ 30 մԱ-ով", "ru": "* Розетки в санузле — IP44, через УЗО 30 мА", "en": "* Bathroom sockets — IP44 via 30 mA RCD"},
    "el_n3": {"hy": "* Եփման վահանակ — առանձին գիծ 3×6 մմ², ավտոմատ 32 Ա", "ru": "* Варочная панель — отдельная линия 3×6 мм², автомат 32 А",
              "en": "* Cooktop — dedicated 3×6 mm² circuit, 32 A breaker"},
    "l_spot": {"hy": "Կետային", "ru": "Точечный", "en": "Spot"}, "l_pendant": {"hy": "Կախովի", "ru": "Подвесной", "en": "Pendant"},
    "l_wall": {"hy": "Պատի լամպ", "ru": "Бра", "en": "Wall light"}, "l_track": {"hy": "Տրեկ", "ru": "Трек", "en": "Track"},
    "l_led": {"hy": "LED ժապավեն", "ru": "LED-лента", "en": "LED strip"}, "l_switch": {"hy": "Անջատիչ", "ru": "Выключатель", "en": "Switch"},
    "l_ceiling": {"hy": "Առաստաղի լուսատու", "ru": "Потолочный", "en": "Ceiling light"}, "l_floor_lamp": {"hy": "Հատակի լամպ", "ru": "Торшер", "en": "Floor lamp"},
    "l_mirror": {"hy": "Հայելու լույս", "ru": "Подсветка зеркала", "en": "Mirror light"},
    "d_shadow": {"hy": "Ստվերային կար 10×10 մմ", "ru": "Теневой шов 10×10 мм", "en": "Shadow gap 10×10 mm"},
    "d_niche": {"hy": "Վարագույրի/քիվի խորշ", "ru": "Ниша для штор / карниза", "en": "Curtain / track recess"},
    "d_cove": {"hy": "Բազմաստիճան առաստաղի LED քիվ", "ru": "LED-карниз многоуровневого потолка", "en": "LED cove of multi-level ceiling"},
    "d_hanger": {"hy": "Կախիչ + պրոֆիլ 60×27", "ru": "Подвес + профиль 60×27", "en": "Hanger + 60×27 channel"},
    "d_shadow_profile": {"hy": "Ստվերային պրոֆիլ 10×10", "ru": "Теневой профиль 10×10", "en": "Shadow-gap profile 10×10"},
    "d_niche160": {"hy": "Խորշ 160 մմ, թաքնված քիվ", "ru": "Ниша 160 мм, карниз скрытый", "en": "160 mm recess, concealed track"},
    "d_niche_backing": {"hy": "Քիվի ներդիր — ձող 40×40", "ru": "Закладная под карниз — брус 40×40", "en": "Track backing — 40×40 timber"},
    "d_led": {"hy": "LED ժապավեն ալյումինե պրոֆիլում 24 V, 9.6 Վտ/մ", "ru": "LED-лента в алюм. профиле 24 V, 9.6 Вт/м", "en": "LED strip in aluminium profile 24 V, 9.6 W/m"},
    "d_psu": {"hy": "Սնուցման բլոկ — արկղում, սպասարկման լյուկ", "ru": "Блок питания — в коробе, сервисный люк", "en": "Driver in the box-out, access hatch"},
    "code_col": {"hy": "Կոդ", "ru": "Код", "en": "Code"}, "layout_col": {"hy": "Դասավորում", "ru": "Раскладка", "en": "Pattern"},
    "surface": {"hy": "Մակերես", "ru": "Поверхность", "en": "Surface"}, "m2_total": {"hy": "մ² (ընդամենը)", "ru": "м² (всего)", "en": "m² (total)"},
    "furn_legend": {"hy": "Կահույք և սարքավորումներ (կոդերը՝ ցուցակում)", "ru": "Мебель и оборудование (коды — ведомость)", "en": "Furniture and equipment (codes — schedule)"},
    "elev_legend": {"hy": "Փռվածքի համար՝ սենյակ.պատ", "ru": "Номер развёртки: помещение.стена", "en": "Elevation no.: room.wall"},
    "category": {"hy": "Կատեգորիա", "ru": "Категория", "en": "Category"}, "checked": {"hy": "Ստուգված", "ru": "Проверено", "en": "Checked"},
    "est_section": {"hy": "Բաժին", "ru": "Раздел", "en": "Section"}, "items": {"hy": "Դիրքեր", "ru": "Позиций", "en": "Items"},
    "sum_amd": {"hy": "Գումար, AMD", "ru": "Сумма, AMD", "en": "Amount, AMD"}, "share": {"hy": "Մաս", "ru": "Доля", "en": "Share"},
    "on_request": {"hy": "Ըստ հարցման", "ru": "По запросу", "en": "On request"}, "max_lead": {"hy": "Առավ. ժամկետ", "ru": "Макс. срок", "en": "Max lead"},
    "tot_known": {"hy": "Ընդամենը (հայտնի գներ)", "ru": "Итого (известные цены)", "en": "Total (known prices)"},
    "tot_confirmed": {"hy": "այդ թվում՝ խանութների հաստատված գներ", "ru": "в т.ч. подтверждённые цены магазинов", "en": "incl. confirmed store prices"},
    "tot_estimated": {"hy": "այդ թվում՝ մոտավոր (աշխատանքներ, բանաձևով իրեր)", "ru": "в т.ч. ориентировочные (работы, изделия по формуле)", "en": "incl. estimated (works, formula-priced items)"},
    "tot_demo": {"hy": "այդ թվում՝ DEMO կատալոգ", "ru": "в т.ч. DEMO-каталог", "en": "incl. DEMO catalogue"},
    "tot_range": {"hy": "Բյուջեի միջակայք", "ru": "Диапазон бюджета", "en": "Budget range"},
    "budget_line": {"hy": "Նպատակային բյուջե {target} AMD · շեղում {delta} AMD", "ru": "Целевой бюджет {target} AMD · отклонение {delta} AMD", "en": "Target budget {target} AMD · deviation {delta} AMD"},
    "est_generated": {"hy": "Նախահաշիվը ձևավորվել է՝ {at} UTC · փոխարժեք՝ {fx}", "ru": "Смета сформирована: {at} UTC · курс: {fx}", "en": "Estimate generated {at} UTC · FX: {fx}"},
    "schedule_title": {"hy": "Իրականացման մոտավոր ժամանակացույց (աշխատանքային օրեր)", "ru": "Ориентировочный график реализации (рабочие дни)", "en": "Indicative implementation schedule (working days)"},
    "st_demolition": {"hy": "Ապամոնտաժ", "ru": "Демонтаж", "en": "Demolition"},
    "st_rough": {"hy": "Էլեկտրիկա և սանտեխնիկա (սևային)", "ru": "Электрика и сантехника (черновые)", "en": "Rough electrics and plumbing"},
    "st_partitions": {"hy": "Միջնապատեր և սվաղ", "ru": "Перегородки и штукатурка", "en": "Partitions and plaster"},
    "st_screed": {"hy": "Լցահատակ, տաք հատակ", "ru": "Стяжка, тёплый пол", "en": "Screed, underfloor heating"},
    "st_tile": {"hy": "Սալիկ", "ru": "Плитка", "en": "Tiling"}, "st_ceilings": {"hy": "Առաստաղներ", "ru": "Потолки", "en": "Ceilings"},
    "st_paint": {"hy": "Մածիկ և ներկում", "ru": "Шпаклёвка и окраска", "en": "Skim and paint"}, "st_floors": {"hy": "Հատակի ծածկույթներ", "ru": "Напольные покрытия", "en": "Floor finishes"},
    "st_doors": {"hy": "Դռներ և մաքուր էլեկտրիկա", "ru": "Двери и чистовая электрика", "en": "Doors and second-fix electrics"},
    "st_custom": {"hy": "Պատվերով կահույք (մոնտաժ)", "ru": "Мебель на заказ (монтаж)", "en": "Custom furniture (installation)"},
    "st_delivery": {"hy": "Կահույքի առաքում, դեկոր", "ru": "Доставка мебели, декор", "en": "Furniture delivery, decor"},
    "scene_qr": {"hy": "Ինտերակտիվ 3D տեսարան և համաձայնեցում", "ru": "Интерактивная 3D-сцена и согласование", "en": "Interactive 3D scene and approval"},
    "accuracy": {"hy": "Ճշգրտության մակարդակ՝ {v}", "ru": "Уровень точности: {v}", "en": "Accuracy level: {v}"},
    "confidence": {"hy": "Ճանաչման վստահություն՝ {pct}% · Ստուգիչ չափեր՝ {dims}", "ru": "Уверенность распознавания: {pct}% · Контрольные размеры: {dims}",
                   "en": "Recognition confidence: {pct}% · Control dimensions: {dims}"},
    "none": {"hy": "չկան", "ru": "нет", "en": "none"},
    "assumptions": {"hy": "ԱԲ ենթադրություններ և անորոշություններ", "ru": "Допущения ИИ и неопределённости", "en": "AI assumptions and uncertainties"},
    "rule_checks": {"hy": "Էրգոնոմիկայի և կոնստրուկտիվի կանոնների ստուգումներ", "ru": "Проверки правил эргономики и конструктива", "en": "Ergonomic and structural rule checks"},
    "approval_log": {"hy": "Համաձայնեցումների մատյան", "ru": "Журнал согласований", "en": "Approval log"},
    "not_approved": {"hy": "Տարբերակը դեռ հաստատված չէ", "ru": "Вариант ещё не утверждён", "en": "Variant not approved yet"},
    "sign_designer": {"hy": "Դիզայներ", "ru": "Дизайнер", "en": "Designer"},
    "sign_specialist": {"hy": "Պատասխանատու մասնագետ (չափագրության և կոնստրուկտիվի ստուգում)", "ru": "Ответственный специалист (проверка обмеров и конструктива)",
                        "en": "Responsible specialist (survey and structural check)"},
    "sign_client": {"hy": "Պատվիրատու", "ru": "Заказчик", "en": "Client"},
    "sign_line": {"hy": "{role}՝ ստորագրություն / ամսաթիվ", "ru": "{role}: подпись / дата", "en": "{role}: signature / date"},
    "ai_disclaimer": {"hy": "ԱԲ-ն ինքնուրույն չի թողարկում շինարարական փաթեթ։ Փաստաթղթերը աշխատանքային են միայն պատասխանատու մասնագետի ստուգումից և ստորագրությունից հետո․ փոփոխությունները գրանցվում են տարբերակների մատյանում։",
                      "ru": "ИИ не выпускает строительный пакет самостоятельно. Документация является рабочей только после проверки и подписи ответственного специалиста; изменения фиксируются в журнале версий.",
                      "en": "AI does not issue a construction package on its own. The documents become working drawings only after review and signature by a responsible specialist; changes are recorded in the version log."},
    "sev_block": {"hy": "արգելք", "ru": "блок", "en": "block"}, "sev_warning": {"hy": "զգուշացում", "ru": "внимание", "en": "warning"},
    "sev_critical": {"hy": "կրիտիկական", "ru": "критично", "en": "critical"}, "sev_info": {"hy": "տեղեկություն", "ru": "инфо", "en": "info"},
    "dec_approved": {"hy": "հաստատված", "ru": "утверждено", "en": "approved"}, "dec_changes_requested": {"hy": "պահանջվում են փոփոխություններ", "ru": "нужны правки", "en": "changes requested"},
    "dec_rejected": {"hy": "մերժված", "ru": "отклонено", "en": "rejected"},
    "eln_at_entry": {"hy": "Մուտքի մոտ", "ru": "У входа", "en": "By the entrance"},
    "eln_by_bed": {"hy": "Մահճակալի մոտ", "ru": "У кровати", "en": "By the bed"},
    "eln_pass_switch": {"hy": "Անցողիկ անջատիչ", "ru": "Проходной выключатель", "en": "2-way switch"},
    "eln_workplace": {"hy": "Աշխատատեղ", "ru": "Рабочее место", "en": "Workplace"},
    "eln_lan": {"hy": "LAN", "ru": "LAN", "en": "LAN"},
    "eln_tv_zone": {"hy": "TV գոտի", "ru": "ТВ-зона", "en": "TV zone"},
    "eln_tv_wall": {"hy": "TV պատին", "ru": "ТВ на стене", "en": "Wall-mounted TV"},
    "eln_by_sofa": {"hy": "Բազմոցի մոտ", "ru": "У дивана", "en": "By the sofa"},
    "eln_above_counter": {"hy": "Աշխատասեղանի վերևում", "ru": "Над столешницей", "en": "Above the worktop"},
    "eln_cooktop_line": {"hy": "Եփման վահանակ 7 կՎտ, մալուխ 3×6", "ru": "Варочная панель 7 кВт, кабель 3×6", "en": "Cooktop 7 kW, 3×6 cable"},
    "eln_oven": {"hy": "Ջեռոց", "ru": "Духовой шкаф", "en": "Oven"},
    "eln_dishwasher": {"hy": "Սպասք լվացող", "ru": "ПММ", "en": "Dishwasher"},
    "eln_hood": {"hy": "Օդաքարշ", "ru": "Вытяжка", "en": "Hood"},
    "eln_fridge": {"hy": "Սառնարան", "ru": "Холодильник", "en": "Fridge"},
    "eln_under_table": {"hy": "Սեղանի տակ — ճշտել", "ru": "Под столом — уточнить", "en": "Under the table — confirm"},
    "eln_washer_ip44": {"hy": "Խոնավակայուն IP44, ՊԱՍ", "ru": "Влагозащищённая IP44, УЗО", "en": "Splash-proof IP44, RCD"},
    "eln_hairdryer": {"hy": "Ֆեն/սափրիչ IP44", "ru": "Фен/бритва IP44", "en": "Hair dryer/shaver IP44"},
    "eln_vacuum": {"hy": "Փոշեկուլ", "ru": "Пылесос", "en": "Vacuum cleaner"},
    "eln_shoe_dryer": {"hy": "Կոշիկի չորանոց", "ru": "Сушилка для обуви", "en": "Shoe dryer"},
    "eln_cleaning": {"hy": "Մաքրման համար", "ru": "Уборка", "en": "Cleaning"},
    # fixed-text assumptions produced by the system (keyed); free-text ones (AI uncertainties) are printed as written
    "as_kitchen_water": {"hy": "Խոհանոցի ջրի կետերը որոշված են տան տիպային սխեմայով — անհրաժեշտ է ստուգում տեղում", "ru": "Точки воды кухни определены по типовой схеме дома — требуется проверка на объекте",
                         "en": "Kitchen water points taken from the typical building layout — verify on site"},
    "as_scale": {"hy": "Մասշտաբը հաստատված չէ — նշեք առնվազն մեկ պատի ստուգիչ չափը", "ru": "Масштаб не подтверждён — задайте контрольный размер хотя бы одной стены",
                 "en": "Scale not confirmed — set a control dimension for at least one wall"},
    "as_dxf_lines": {"hy": "DXF գծերը ընդունված են որպես 120 մմ հաստությամբ պատերի առանցքներ — ստուգեք հաստություններն ու տեսակները", "ru": "Линии DXF приняты как осевые стен толщиной 120 мм — проверьте толщины и тип стен",
                     "en": "DXF lines treated as 120 mm wall centrelines — check thicknesses and wall types"},
    "as_balcony_glazing": {"hy": "Պատշգամբի ապակեպատման տեսակը որոշված է լուսանկարով՝ ցածր վստահությամբ", "ru": "Тип остекления балкона определён по фото с низкой уверенностью",
                           "en": "Balcony glazing type inferred from photos with low confidence"},
    "as_w7_bearing": {"hy": "W7 պատը ենթադրաբար կրող չէ (աղյուս 120 մմ)։ Ապամոնտաժը՝ միայն կոնստրուկտորի հաստատումից հետո", "ru": "Стена W7 предполагается ненесущей (кирпич 120 мм). Демонтаж — только после подтверждения конструктора",
                      "en": "Wall W7 is assumed non-load-bearing (120 mm brick). Demolition only after structural engineer approval"},
    "as_nosrc": {"hy": "Սկզբնական ֆայլեր չկան — կառուցեք հատակագիծը ձեռքով", "ru": "Нет исходных файлов — постройте план вручную", "en": "No source files — draw the plan manually"},
}

_IDX = {"hy": 0, "ru": 1, "en": 2}


@cache
def _shared() -> dict[str, dict[str, str]]:
    """Vocabulary shared with the web UI (works, notices, rules, enums, units), exported by
    apps/web/scripts/export-server-dict.mjs from the UI dictionaries."""
    return json.loads((Path(__file__).resolve().parent.parent / "i18n_shared.json").read_text(encoding="utf-8"))


def shared(key: str, lang: str, default: str | None = None, **kw) -> str:
    v = _shared().get(key)
    if not v:
        return key if default is None else default
    s = v.get(lang) or v.get("ru") or key
    try:
        return s.format(**kw) if kw else s
    except (KeyError, IndexError):
        return s


def tx(key: str, lang: str, **kw) -> str:
    v = TX.get(key) or T.get(key)
    s = (v.get(lang) or v.get("ru")) if v else key
    return s.format(**kw) if kw else s


def variant_title(variant: dict, lang: str) -> str:
    """Generated variant titles are style · tier; a title the designer typed is kept as written."""
    style = shared(f"enum.style.{variant.get('style')}", lang, default="")
    if not style:
        return variant.get("title", "")
    tier = shared(f"enum.tier.{variant.get('tier')}", lang, default="")
    return f"{style} · {tier}" if tier else style


def rule_text(issue: dict, lang: str) -> str:
    from ..catalog.taxonomy import label

    tpl = _shared().get(f"rules.{issue.get('code')}", {}).get(lang)
    if not tpl:
        return issue.get("message", "")
    p = dict(issue.get("params") or {})
    for k in ("object", "other", "a", "b"):
        if isinstance(p.get(k), str):
            p[k] = label(p[k], lang)
    for code, cat in (("code", "object"), ("other_code", "other"), ("a_code", "a"), ("b_code", "b")):
        p.setdefault(code, p.get(cat, ""))
        if not p[code]:
            p[code] = p.get(cat, "")
    try:
        return tpl.format(**p)
    except (KeyError, IndexError):
        return issue.get("message", "")


def assumption_text(a, lang: str) -> str:
    key = f"as_{a.key}"
    return tx(key, lang) if key in TX else a.text


def line_name(ln: dict, lang: str) -> str:
    """Estimate line titles the system generated are rendered from codes; product names are data."""
    g = ln.get("group")
    if g == "works":
        return shared(f"works.{ln.get('category')}", lang, default=ln.get("name") or "")
    if g in ("delivery", "installation"):
        return shared(f"estimate.line_{g}", lang, supplier=ln.get("supplier") or "")
    if g == "contingency":
        return shared("estimate.line_contingency", lang)
    return ln.get("name") or ""


def unit(u: str, lang: str) -> str:
    return shared(f"unit.{u}", lang, default=u)


def notice(n: dict, lang: str) -> str:
    return shared(f"notice.{n['code']}", lang, **(n.get("params") or {}))


def elec_note(e, lang: str) -> str:
    from ..scene.layout import ELEC_NOTES

    key = e.note_key or next((k for k, v in ELEC_NOTES.items() if v == e.note), "")
    return tx(f"eln_{key}", lang) if f"eln_{key}" in TX else e.note


def severity(sev: str, lang: str) -> str:
    return tx(f"sev_{sev}", lang) if f"sev_{sev}" in TX else sev


def t(key: str, lang: str) -> str:
    v = T.get(key)
    if not v:
        return key
    return v.get(lang) or v.get("ru") or key


def room_name(room, lang: str) -> str:
    if lang == "ru":
        return room.name
    return ROOM_NAMES.get(room.type, {}).get(lang, room.name)
