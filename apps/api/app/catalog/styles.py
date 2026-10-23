"""Interior styles: four groups (modern, classic & historic, ethnic, mixed).

Products in the catalogue carry one of five *base* style tags (warm_minimal, modern_loft, soft_scandi, contemporary,
classic). Every style maps to the base whose products suit it best (`base`), so a project in «Japandi» or «Baroque»
still gets real SKUs; the palette, light/dark preference and the English prompt shape finishes and renders.
UI names and subtitles live in the web dictionary (enum.style.* / enum.style_sub.*); `ru`/`subtitle` here are the
server-side fallback used in variant titles and the album."""
from __future__ import annotations

BASE_STYLES = ("warm_minimal", "modern_loft", "soft_scandi", "contemporary", "classic")
GROUPS = ("modern", "classic", "ethnic", "mixed")


def _s(group, ru, hy, en, subtitle, palette, base, prompt, light=None):
    return {"group": group, "ru": ru, "hy": hy, "en": en, "subtitle": subtitle, "palette": palette, "base": base, "prompt": prompt, "light": light}


STYLES: dict[str, dict] = {
    # ---- modern (XX–XXI c.)
    "warm_minimal": _s("modern", "Тёплый минимализм", "Ջերմ մինիմալիզմ", "Warm minimalism", "Спокойный, уютный, вне времени",
                       ["#efe6da", "#d9c9b7", "#b98f6a", "#8a5a3c", "#2e2e2e"], "warm_minimal", "warm minimalism: calm warm neutrals, natural oak, linen, soft daylight", True),
    "minimalism": _s("modern", "Минимализм", "Մինիմալիզմ", "Minimalism", "Строгая геометрия, минимум мебели, скрытое хранение",
                     ["#ffffff", "#e9e7e3", "#b7b4ae", "#5c5a57", "#1c1c1c"], "warm_minimal", "strict minimalism: pure geometry, handleless storage, white, grey and black, almost no decor", True),
    "modern_loft": _s("modern", "Лофт", "Լոֆթ", "Loft (industrial)", "Кирпич, бетон, открытые трубы и высокие потолки",
                      ["#3a3532", "#6b4a3a", "#a4593c", "#c9b8a3", "#1f1d1b"], "modern_loft", "industrial loft: exposed brick, raw concrete, black steel, visible pipes, leather and timber", False),
    "high_tech": _s("modern", "Хай-тек", "Հայ-տեկ", "High-tech", "Хром, стекло, умная техника и подсветка",
                    ["#f2f3f5", "#c0c4ca", "#7b8088", "#2a2d33", "#38bdf8"], "contemporary", "high-tech: chrome, glass, glossy white, integrated smart devices, cool LED accent lighting"),
    "soft_scandi": _s("modern", "Скандинавский", "Սկանդինավյան", "Scandinavian", "Светлое дерево, текстиль, белая база и акценты",
                      ["#f4f1ec", "#e3d8c8", "#c8b08f", "#8f9f7e", "#5c5248"], "soft_scandi", "Scandinavian: light birch and ash, white walls, wool throws and rugs, cosy daylight", True),
    "contemporary": _s("modern", "Контемпорари", "Կոնտեմպորարի", "Contemporary", "Лаконично, нейтрально, модульная мебель",
                       ["#f2f0ed", "#cfc8bf", "#8c8279", "#c97f63", "#2e2e2e"], "contemporary", "contemporary: clean lines, neutral tones, modular mass-market furniture"),
    "classic": _s("modern", "Неоклассика", "Նեոդասական", "Neoclassic", "Симметрия и молдинги в современных материалах",
                  ["#f3eee6", "#ddd2c2", "#b8a17f", "#7c6a55", "#3c352e"], "classic", "neoclassic: symmetry, wall mouldings, noble muted tones, modern appliances"),
    "eco": _s("modern", "Эко-стиль", "Էկո ոճ", "Eco style", "Дерево, камень, глина, бамбук и живые растения",
              ["#f1ece2", "#c9b994", "#8a9a6b", "#6b5440", "#3f4a32"], "soft_scandi", "eco style: raw wood, stone, clay, bamboo, many living plants, natural light", True),
    "japandi": _s("modern", "Джапанди", "Ջապանդի", "Japandi", "Японский минимализм и скандинавский уют, ваби-саби",
                  ["#efe9df", "#d6c7b0", "#a68a64", "#5f5446", "#2b2724"], "soft_scandi", "Japandi: low simple furniture, wabi-sabi imperfections, warm earthy palette, paper and oak", True),
    "art_deco": _s("modern", "Ар-деко", "Ար-դեկո", "Art Deco", "Геометрия, мрамор, латунь и глянец",
                   ["#1e2a2f", "#0f4c4a", "#b08d57", "#e8e0d0", "#111111"], "classic", "Art Deco: geometric patterns, marble, brass and gold inlays, velvet, lacquered gloss", False),
    "pop_art": _s("modern", "Поп-арт", "Փոփ-արտ", "Pop art", "Кислотные цвета, комиксы, глянцевый пластик",
                  ["#ffffff", "#ffde00", "#ff3c7d", "#00a8e8", "#111111"], "contemporary", "pop art: bold acid colours, comic posters, glossy plastic furniture, playful decor"),
    "memphis": _s("modern", "Мемфис", "Մեմֆիս", "Memphis", "Яркая геометрия, асимметрия, полоски и горох 80-х",
                  ["#f7f3ea", "#ff6f61", "#3dbfa4", "#f9c80e", "#2b2d42"], "contemporary", "Memphis design: 1980s colour blocking, squiggles and dots, asymmetric geometric furniture"),
    "brutalism": _s("modern", "Брутализм", "Բրուտալիզմ", "Brutalism", "Грубый бетон и монументальные формы",
                    ["#bdbab4", "#8f8c86", "#5f5d59", "#3b3a37", "#d8cfc0"], "modern_loft", "brutalism: board-formed raw concrete, massive monolithic forms, no ornament", False),
    "grunge": _s("modern", "Гранж", "Գրանժ", "Grunge", "Состаренная классика на простой отделке",
                 ["#e7e1d6", "#b7a993", "#8c7a63", "#5b4c3d", "#2f2924"], "modern_loft", "grunge: elegant slightly aged furniture against brick, whitewash and plain timber"),
    # ---- classic & historic
    "antique": _s("classic", "Античный", "Անտիկ", "Antique", "Колонны, арки, лепнина и мрамор",
                  ["#f5f1e8", "#e2d8c5", "#c7b99b", "#9c8a6c", "#5e5240"], "classic", "antique Greco-Roman: columns, arches, plaster mouldings, marble, statues, light tones", True),
    "gothic": _s("classic", "Готический", "Գոթական", "Gothic", "Стрельчатые окна, тёмное дерево, кованые элементы",
                 ["#2b2226", "#4a2f35", "#6e5a4a", "#a38f6b", "#14110f"], "classic", "Gothic: pointed arches, stained glass, dark carved oak, wrought iron, dramatic light", False),
    "baroque": _s("classic", "Барокко", "Բարոկո", "Baroque", "Дворцовая роскошь, позолота, бархат и зеркала",
                  ["#f3e7cf", "#c9a14a", "#7a1f2b", "#3d2a1e", "#1b1410"], "classic", "Baroque: palatial curves, gilding, heavy velvet, tapestries, huge mirrors", False),
    "rococo": _s("classic", "Рококо", "Ռոկոկո", "Rococo", "Пастель, завитки, фарфор и зеркала",
                 ["#fbf3f1", "#f2d7dd", "#cfe3ef", "#e7d6a8", "#b79a6a"], "classic", "Rococo: pastel pink and blue, delicate curls and shells, porcelain, gilded mirrors", True),
    "classicism": _s("classic", "Классицизм", "Կլասիցիզմ", "Classicism", "Строгая симметрия, колонны, сдержанная роскошь",
                     ["#f4efe6", "#dccfb8", "#b39b72", "#6f5c45", "#2f2a24"], "classic", "classicism: strict symmetry, columns, restrained luxury, fine wooden furniture"),
    "empire": _s("classic", "Ампир", "Ամպիր", "Empire", "Парадный стиль: гербы, позолота, тяжёлые драпировки",
                 ["#f2e6c9", "#c19a49", "#1f3a5f", "#7d1d20", "#20180f"], "classic", "Empire style: imperial symbols, laurel wreaths, gilding, massive mahogany, heavy drapes", False),
    "art_nouveau": _s("classic", "Модерн (ар-нуво)", "Մոդեռն (ար-նուվո)", "Art Nouveau", "Плавные линии, растительные орнаменты, витражи",
                      ["#efe8d6", "#b7c39a", "#7f8f5a", "#a5714a", "#3a3326"], "classic", "Art Nouveau: flowing organic lines, floral ornament, wrought iron, stained glass"),
    "provence": _s("classic", "Прованс", "Պրովանս", "Provence", "Пастель, выгоревшее дерево, лён и цветочные принты",
                   ["#f6f1e7", "#dfe6ea", "#c9b8d6", "#a9b892", "#8a7a64"], "soft_scandi", "Provence: French country, pastel lavender and blue, sun-bleached wood, linen, floral prints", True),
    "chalet": _s("classic", "Шале", "Շալե", "Chalet", "Дерево, балки, каменный камин и шкуры",
                 ["#e9dcc6", "#b58c5f", "#7a5233", "#4a3322", "#2a1f17"], "warm_minimal", "Alpine chalet: rough timber, ceiling beams, stone fireplace, sheepskins, warm light", False),
    "rustic": _s("classic", "Рустик", "Ռուստիկ", "Rustic", "Брёвна, сучковатые доски, необработанный камень",
                 ["#e6dccb", "#a88b65", "#7b6247", "#53412f", "#2e241b"], "warm_minimal", "rustic: massive logs, knotty planks, rough stone, simple homespun textiles", False),
    # ---- ethnic & national
    "english": _s("ethnic", "Английский", "Անգլիական", "English", "Честерфилд, камин, книги и деревянные панели",
                  ["#efe6d6", "#7a2e2e", "#1f3d34", "#8b6b4a", "#2a2018"], "classic", "English: Chesterfield leather sofas, fireplace, striped or tartan wallpaper, books, wood panelling", False),
    "japanese": _s("ethnic", "Японский", "Ճապոնական", "Japanese", "Дзен, сёдзи, татами, бамбук и камень",
                   ["#f4efe4", "#d9c8a9", "#9c8462", "#4b5d47", "#2b2622"], "warm_minimal", "Japanese zen: shoji screens, tatami, low furniture, bamboo and natural stone", True),
    "moroccan": _s("ethnic", "Марокканский", "Մարոկկական", "Moroccan", "Мозаика зеллиж, арки, ковры и кованые лампы",
                   ["#f3e6d3", "#c96a3a", "#1d6a8a", "#d9a441", "#4a2c21"], "warm_minimal", "Moroccan: zellige mosaic, horseshoe arches, layered rugs and floor cushions, pierced metal lanterns"),
    "mediterranean": _s("ethnic", "Средиземноморский", "Միջերկրածովյան", "Mediterranean", "Бело-синяя гамма, плетёная мебель, керамика",
                        ["#ffffff", "#e9e4d8", "#2f6fa8", "#c96f4a", "#7d8b5a"], "soft_scandi", "Mediterranean: white plaster, blue or olive-terracotta accents, rattan furniture, ceramics", True),
    "african": _s("ethnic", "Африканский", "Աֆրիկյան", "African", "Анималистичные принты, маски, кожа, терракота",
                  ["#e8d5b5", "#c46a2d", "#e0a32e", "#5b3a23", "#1d1712"], "warm_minimal", "African: animal prints, carved masks, natural leather, warm terracotta and ochre"),
    "chinese": _s("ethnic", "Китайский", "Չինական", "Chinese", "Красный, чёрный и золото, лак, бамбуковые ширмы",
                  ["#f2e6d0", "#a3201c", "#111111", "#c9a14a", "#3c2a20"], "classic", "Chinese: feng shui harmony, red, black and gold, lacquered furniture, bamboo screens", False),
    "american": _s("ethnic", "Американский", "Ամերիկյան", "American", "Простор, кухонный остров, крупная мебель и свет",
                   ["#f3efe8", "#d6cbbb", "#9c8f7d", "#3f4d5a", "#2b2b2b"], "contemporary", "American: open-plan spaces, large central sofa, kitchen island, layered lighting scenes"),
    # ---- mixed
    "eclectic": _s("mixed", "Эклектика", "Էկլեկտիկա", "Eclectic", "Смешение 2–3 близких стилей с общей идеей",
                   ["#f1ebe1", "#c9b28f", "#6e7f6a", "#a65e45", "#2e2e2e"], "contemporary", "eclectic: two or three related styles unified by colour, texture and architecture"),
    "fusion": _s("mixed", "Фьюжн", "Ֆյուժն", "Fusion", "Смелое сочетание противоположных стилей через цвет",
                 ["#f4f1ec", "#2b2d42", "#ef8354", "#4f5d75", "#bfc0c0"], "contemporary", "fusion: bold mix of opposite styles (e.g. high-tech and ethnic) held together by colour"),
    "kitsch": _s("mixed", "Китч", "Քիչ", "Kitsch", "Ироничный антидизайн: неон, пластик, «позолота»",
                 ["#ff4fa3", "#ffe14d", "#3ae0d0", "#d4af37", "#1a1a1a"], "contemporary", "kitsch: ironic anti-design, neon colours, cheap plastic, fake gilding"),
    "boho": _s("mixed", "Бохо", "Բոհո", "Boho", "Хендмейд, винтаж, ковры, подушки и растения",
               ["#f3e9da", "#d9a273", "#a65e3c", "#6b7a4f", "#3b2f27"], "soft_scandi", "boho: handmade textiles, vintage furniture, layered rugs and cushions, plants, travel souvenirs"),
}

STYLE_BASE: dict[str, str] = {k: v["base"] for k, v in STYLES.items()}
