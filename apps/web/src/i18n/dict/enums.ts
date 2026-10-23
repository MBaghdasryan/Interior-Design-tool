import type { Dict, Entry } from "../index";

const e = (hy: string, ru: string, en: string): Entry => ({ hy, ru, en });

const cats: Record<string, Entry> = {
  sofa: e("Բազմոց", "Диван", "Sofa"), armchair: e("Բազկաթոռ", "Кресло", "Armchair"), coffee_table: e("Սուրճի սեղան", "Журнальный стол", "Coffee table"),
  tv_unit: e("Հեռուստացույցի տումբա", "ТВ-тумба", "TV unit"), dining_table: e("Ճաշասեղան", "Обеденный стол", "Dining table"), dining_chair: e("Աթոռ", "Обеденный стул", "Dining chair"),
  bed: e("Մահճակալ", "Кровать", "Bed"), kids_bed: e("Մանկական մահճակալ", "Детская кровать", "Kids bed"), nightstand: e("Կողատումբա", "Прикроватная тумба", "Nightstand"),
  wardrobe: e("Զգեստապահարան", "Шкаф", "Wardrobe"), dresser: e("Կոմոդ", "Комод", "Dresser"), desk: e("Գրասեղան", "Письменный стол", "Desk"),
  desk_chair: e("Աշխատանքային աթոռ", "Рабочее кресло", "Desk chair"), hallway_wardrobe: e("Նախասենյակի պահարան", "Шкаф в прихожую", "Hallway wardrobe"),
  shoe_cabinet: e("Կոշիկի պահարան", "Обувница", "Shoe cabinet"), bench: e("Նստարան", "Банкетка", "Bench"), storage_system: e("Հանդերձարանի համակարգ", "Гардеробная система", "Storage system"),
  kitchen_run: e("Խոհանոցային կահույք", "Кухонный гарнитур", "Kitchen run"), fridge: e("Սառնարան", "Холодильник", "Fridge"), cooktop: e("Եփման վահանակ", "Варочная панель", "Cooktop"),
  oven: e("Ջեռոց", "Духовой шкаф", "Oven"), hood: e("Օդաքարշ", "Вытяжка", "Hood"), dishwasher: e("Սպասք լվացող մեքենա", "Посудомоечная машина", "Dishwasher"),
  washer: e("Լվացքի մեքենա", "Стиральная машина", "Washing machine"), tv: e("Հեռուստացույց", "Телевизор", "TV"), toilet: e("Կախովի զուգարանակոնք", "Унитаз подвесной", "Wall-hung WC"),
  vanity: e("Լվացարանով տումբա", "Тумба с раковиной", "Vanity unit"), bathtub: e("Լոգարան", "Ванна", "Bathtub"), shower: e("Ցնցուղախցիկ", "Душевая зона", "Shower"),
  faucet: e("Ծորակ", "Смеситель", "Faucet"), towel_dryer: e("Սրբիչի տաքացուցիչ", "Полотенцесушитель", "Towel warmer"), installation: e("Ինստալյացիա", "Инсталляция", "WC frame"),
  pendant_light: e("Կախովի լուսատու", "Подвесной светильник", "Pendant light"), spot_light: e("Ներկառուցվող լուսատու", "Точечный светильник", "Downlight"),
  track_light: e("Թրեքային համակարգ", "Трековая система", "Track light"), led_strip: e("LED ժապավեն", "LED-лента", "LED strip"), wall_light: e("Պատի լուսատու", "Бра", "Wall light"),
  floor_lamp: e("Հատակի լամպ", "Торшер", "Floor lamp"), door_interior: e("Միջսենյակային դուռ", "Межкомнатная дверь", "Interior door"), door_sliding: e("Սահող դուռ", "Раздвижная дверь", "Sliding door"),
  door_entrance: e("Մուտքի դուռ", "Входная дверь", "Entrance door"), floor_parquet: e("Մանրահատակ / ինժեներական տախտակ", "Паркет / инженерная доска", "Engineered wood"),
  floor_laminate: e("Լամինատ", "Ламинат", "Laminate"), skirting: e("Շրիշակ", "Плинтус", "Skirting board"), floor_tile: e("Հատակի կերամոգրանիտ", "Керамогранит пол", "Floor porcelain"), wall_tile: e("Պատի սալիկ", "Плитка настенная", "Wall tile"),
  wall_paint: e("Ինտերիերի ներկ", "Краска интерьерная", "Interior paint"), wall_panel: e("Դեկորատիվ պանելներ", "Декоративные панели", "Wall panels"), putty: e("Ծեփամածիկ", "Шпаклёвка", "Putty"),
  tile_adhesive: e("Սալիկի սոսինձ", "Плиточный клей", "Tile adhesive"), drywall: e("Գիպսաստվարաթուղթ", "Гипсокартон", "Drywall"), rug: e("Գորգ", "Ковёр", "Rug"),
  curtains: e("Վարագույրներ", "Шторы", "Curtains"), artwork: e("Դեկոր / նկարներ", "Декор / картины", "Artwork"), mirror: e("Հայելի", "Зеркало", "Mirror"), plant: e("Բույսեր", "Растения", "Plants"),
  delivery: e("Առաքում", "Доставка", "Delivery"), contingency: e("Պահուստ", "Резерв", "Contingency"),
};
const groups: Record<string, Entry> = {
  furniture: e("Կահույք", "Мебель", "Furniture"), lighting: e("Լուսավորություն", "Освещение", "Lighting"), plumbing: e("Սանտեխնիկա", "Сантехника", "Plumbing"),
  finishing: e("Հարդարման նյութեր", "Отделочные материалы", "Finishing materials"), doors: e("Դռներ", "Двери", "Doors"), appliances: e("Կենցաղային տեխնիկա", "Техника", "Appliances"),
  decor: e("Դեկոր և տեքստիլ", "Декор и текстиль", "Decor & textile"), custom: e("Պատվերով արտադրանք", "Изделия на заказ", "Custom-made"), works: e("Աշխատանքներ", "Работы", "Works"),
  delivery: e("Առաքում", "Доставка", "Delivery"), installation: e("Մոնտաժ և հավաքում", "Монтаж и сборка", "Installation"), contingency: e("Պահուստ", "Резерв", "Contingency"),
};
const styles: Record<string, Entry> = {
  warm_minimal: e("Ջերմ մինիմալիզմ", "Тёплый минимализм", "Warm minimalism"), minimalism: e("Մինիմալիզմ", "Минимализм", "Minimalism"),
  modern_loft: e("Լոֆթ", "Лофт", "Loft"), high_tech: e("Հայ-տեկ", "Хай-тек", "High-tech"), soft_scandi: e("Սկանդինավյան", "Скандинавский", "Scandinavian"),
  contemporary: e("Կոնտեմպորարի", "Контемпорари", "Contemporary"), classic: e("Նեոդասական", "Неоклассика", "Neoclassic"), eco: e("Էկո ոճ", "Эко-стиль", "Eco style"),
  japandi: e("Ջապանդի", "Джапанди", "Japandi"), art_deco: e("Ար-դեկո", "Ар-деко", "Art Deco"), pop_art: e("Փոփ-արտ", "Поп-арт", "Pop art"),
  memphis: e("Մեմֆիս", "Мемфис", "Memphis"), brutalism: e("Բրուտալիզմ", "Брутализм", "Brutalism"), grunge: e("Գրանժ", "Гранж", "Grunge"),
  antique: e("Անտիկ", "Античный", "Antique"), gothic: e("Գոթական", "Готический", "Gothic"), baroque: e("Բարոկո", "Барокко", "Baroque"),
  rococo: e("Ռոկոկո", "Рококо", "Rococo"), classicism: e("Կլասիցիզմ", "Классицизм", "Classicism"), empire: e("Ամպիր", "Ампир", "Empire"),
  art_nouveau: e("Մոդեռն (ար-նուվո)", "Модерн (ар-нуво)", "Art Nouveau"), provence: e("Պրովանս", "Прованс", "Provence"), chalet: e("Շալե", "Шале", "Chalet"),
  rustic: e("Ռուստիկ", "Рустик", "Rustic"), english: e("Անգլիական", "Английский", "English"), japanese: e("Ճապոնական", "Японский", "Japanese"),
  moroccan: e("Մարոկկական", "Марокканский", "Moroccan"), mediterranean: e("Միջերկրածովյան", "Средиземноморский", "Mediterranean"),
  african: e("Աֆրիկյան", "Африканский", "African"), chinese: e("Չինական", "Китайский", "Chinese"), american: e("Ամերիկյան", "Американский", "American"),
  eclectic: e("Էկլեկտիկա", "Эклектика", "Eclectic"), fusion: e("Ֆյուժն", "Фьюжн", "Fusion"), kitsch: e("Քիչ", "Китч", "Kitsch"), boho: e("Բոհո", "Бохо", "Boho"),
};
const styleSub: Record<string, Entry> = {
  warm_minimal: e("Հանգիստ, հարմարավետ, ժամանակից դուրս", "Спокойный, уютный, вне времени", "Calm, cosy, timeless"),
  minimalism: e("Խիստ երկրաչափություն, նվազագույն կահույք, թաքնված պահոցներ", "Строгая геометрия, минимум мебели, скрытое хранение", "Strict geometry, little furniture, hidden storage"),
  modern_loft: e("Աղյուս, բետոն, բաց խողովակներ և բարձր առաստաղներ", "Кирпич, бетон, открытые трубы, высокие потолки", "Brick, concrete, exposed pipes, high ceilings"),
  high_tech: e("Քրոմ, ապակի, խելացի տեխնիկա և լուսավորում", "Хром, стекло, умная техника и подсветка", "Chrome, glass, smart devices and LED light"),
  soft_scandi: e("Բաց փայտ, տեքստիլ, սպիտակ հիմք և վառ շեշտեր", "Светлое дерево, текстиль, белая база и акценты", "Light wood, textiles, white base, bright accents"),
  contemporary: e("Լակոնիկ, չեզոք, մոդուլային կահույք", "Лаконично, нейтрально, модульная мебель", "Concise, neutral, modular furniture"),
  classic: e("Համաչափություն և կաղապարներ՝ ժամանակակից նյութերով", "Симметрия и молдинги в современных материалах", "Symmetry and mouldings in modern materials"),
  eco: e("Փայտ, քար, կավ, բամբուկ և կենդանի բույսեր", "Дерево, камень, глина, бамбук и живые растения", "Wood, stone, clay, bamboo and living plants"),
  japandi: e("Ճապոնական մինիմալիզմ և սկանդինավյան հարմարավետություն", "Японский минимализм и скандинавский уют, ваби-саби", "Japanese minimalism meets Scandinavian comfort"),
  art_deco: e("Երկրաչափություն, մարմար, արույր և փայլ", "Геометрия, мрамор, латунь и глянец", "Geometry, marble, brass and gloss"),
  pop_art: e("Թթվային գույներ, կոմիքսներ, փայլուն պլաստիկ", "Кислотные цвета, комиксы, глянцевый пластик", "Acid colours, comics, glossy plastic"),
  memphis: e("Վառ երկրաչափություն, անհամաչափություն, 80-ականներ", "Яркая геометрия, асимметрия, эстетика 80-х", "Bright geometry, asymmetry, 1980s spirit"),
  brutalism: e("Կոպիտ բետոն և մոնումենտալ ձևեր", "Грубый бетон и монументальные формы", "Raw concrete and monumental forms"),
  grunge: e("Հնեցված դասական՝ պարզ հարդարման վրա", "Состаренная классика на простой отделке", "Aged classic pieces on plain finishes"),
  antique: e("Սյուներ, կամարներ, ծեփանախշ և մարմար", "Колонны, арки, лепнина и мрамор", "Columns, arches, mouldings and marble"),
  gothic: e("Սլաքաձև պատուհաններ, մուգ փայտ, դարբնոցային տարրեր", "Стрельчатые окна, тёмное дерево, ковка", "Pointed windows, dark wood, wrought iron"),
  baroque: e("Պալատական շքեղություն, ոսկեզօծ, թավիշ և հայելիներ", "Дворцовая роскошь, позолота, бархат и зеркала", "Palatial luxury, gilding, velvet, mirrors"),
  rococo: e("Պաստել, գանգուրներ, ճենապակի և հայելիներ", "Пастель, завитки, фарфор и зеркала", "Pastels, curls, porcelain and mirrors"),
  classicism: e("Խիստ համաչափություն, սյուներ, զուսպ շքեղություն", "Строгая симметрия, колонны, сдержанная роскошь", "Strict symmetry, columns, restrained luxury"),
  empire: e("Զինանշաններ, ոսկեզօծ, ծանր վարագույրներ", "Гербы, позолота, тяжёлые драпировки", "Emblems, gilding, heavy drapery"),
  art_nouveau: e("Սահուն գծեր, բուսական զարդանախշեր, վիտրաժներ", "Плавные линии, растительные орнаменты, витражи", "Flowing lines, floral ornament, stained glass"),
  provence: e("Պաստել, արևից խունացած փայտ, վուշ և ծաղիկներ", "Пастель, выгоревшее дерево, лён и цветы", "Pastels, sun-bleached wood, linen and florals"),
  chalet: e("Փայտ, հեծաններ, քարե բուխարի և մորթիներ", "Дерево, балки, каменный камин и шкуры", "Timber, beams, stone fireplace and furs"),
  rustic: e("Գերաններ, հանգույցավոր տախտակներ, չմշակված քար", "Брёвна, сучковатые доски, необработанный камень", "Logs, knotty boards, rough stone"),
  english: e("Չեսթերֆիլդ, բուխարի, գրքեր և փայտե պանելներ", "Честерфилд, камин, книги, деревянные панели", "Chesterfield, fireplace, books, wood panels"),
  japanese: e("Զեն, սյոձի, տատամի, բամբուկ և քար", "Дзен, сёдзи, татами, бамбук и камень", "Zen, shoji, tatami, bamboo and stone"),
  moroccan: e("Զելիժ խճանկար, կամարներ, գորգեր և լապտերներ", "Мозаика зеллиж, арки, ковры и фонари", "Zellige mosaic, arches, rugs and lanterns"),
  mediterranean: e("Սպիտակ-կապույտ գամմա, հյուսված կահույք, կերամիկա", "Бело-синяя гамма, плетёная мебель, керамика", "White and blue, rattan furniture, ceramics"),
  african: e("Կենդանական նախշեր, դիմակներ, կաշի, տերակոտա", "Анималистичные принты, маски, кожа, терракота", "Animal prints, masks, leather, terracotta"),
  chinese: e("Կարմիր, սև և ոսկի, լաք, բամբուկե շիրմաներ", "Красный, чёрный и золото, лак, ширмы", "Red, black and gold, lacquer, screens"),
  american: e("Տարածք, խոհանոցային կղզի, մեծ կահույք և լույս", "Простор, кухонный остров, крупная мебель", "Open space, kitchen island, large furniture"),
  eclectic: e("2–3 մոտ ոճերի համադրություն՝ ընդհանուր գաղափարով", "Смешение 2–3 близких стилей с общей идеей", "Two or three related styles, one idea"),
  fusion: e("Հակադիր ոճերի համարձակ համադրություն", "Смелое сочетание противоположных стилей", "Bold mix of opposite styles"),
  kitsch: e("Հեգնական հակադիզայն՝ նեոն, պլաստիկ, «ոսկի»", "Ироничный антидизайн: неон, пластик, «позолота»", "Ironic anti-design: neon, plastic, fake gold"),
  boho: e("Ձեռքի աշխատանք, վինտաժ, գորգեր և բույսեր", "Хендмейд, винтаж, ковры и растения", "Handmade, vintage, rugs and plants"),
  economy: e("Խելամիտ բյուջե, նույն լուծումները", "Разумный бюджет, те же решения", "Sensible budget, same solutions"),
  premium: e("Բարձր դասի նյութեր և արտադրանք", "Материалы и изделия высокого класса", "High-end materials and pieces"),
};
const styleGroups: Record<string, Entry> = {
  modern: e("Ժամանակակից", "Современные", "Modern"), classic: e("Դասական և պատմական", "Классические и исторические", "Classic & historic"),
  ethnic: e("Էթնիկ և ազգային", "Этнические и национальные", "Ethnic & national"), mixed: e("Խառը", "Смешанные", "Mixed"),
};
const tiers: Record<string, Entry> = { economy: e("Էկոնոմ", "Эконом", "Economy"), comfort: e("Կոմֆորտ", "Комфорт", "Comfort"), business: e("Բիզնես", "Бизнес", "Business"), premium: e("Պրեմիում", "Премиум", "Premium"),
  optimal: e("Օպտիմալ", "Оптимальный", "Optimal") };
const rooms: Record<string, Entry> = {
  living: e("Հյուրասենյակ", "Гостиная", "Living room"), kitchen: e("Խոհանոց", "Кухня", "Kitchen"), kitchen_living: e("Խոհանոց-հյուրասենյակ", "Кухня-гостиная", "Kitchen-living"),
  bedroom: e("Ննջասենյակ", "Спальня", "Bedroom"), kids: e("Մանկական", "Детская", "Kids room"), bathroom: e("Սանհանգույց", "Санузел", "Bathroom"), wc: e("Զուգարան", "Туалет", "WC"),
  hallway: e("Նախասենյակ", "Прихожая", "Hallway"), wardrobe: e("Հանդերձարան", "Гардеробная", "Walk-in closet"), balcony: e("Պատշգամբ", "Балкон", "Balcony"),
  office: e("Աշխատասենյակ", "Кабинет", "Study"), storage: e("Պահեստ", "Кладовая", "Storage"), laundry: e("Լվացքատուն", "Постирочная", "Laundry"),
};
const roles: Record<string, Entry> = {
  platform_admin: e("Պլատֆորմի ադմինիստրատոր", "Администратор платформы", "Platform admin"), platform_ops: e("Կատալոգի օպերատոր", "Оператор каталога", "Catalogue operator"),
  designer: e("Բյուրոյի դիզայներ", "Дизайнер бюро", "Bureau designer"), bureau_admin: e("Բյուրոյի ղեկավար", "Руководитель бюро", "Bureau owner"),
  client: e("Պատվիրատու", "Заказчик", "Client"), collaborator: e("Համահեղինակ", "Участник", "Collaborator"), supplier_admin: e("Մատակարար", "Поставщик", "Supplier"),
  supplier_catalog: e("Կատալոգի մենեջեր", "Менеджер каталога", "Catalogue manager"), manufacturer: e("Արտադրող", "Производитель", "Manufacturer"),
  linguist: e("Լեզվաբան-խմբագիր", "Лингвист-редактор", "Linguist"), installer: e("Մոնտաժող", "Монтажник", "Installer"), verifier: e("Չափագրող մասնագետ", "Обмерщик", "Surveyor"), user: e("Օգտատեր", "Пользователь", "User"),
};

const out: Dict = {  "enum.order.in_production": e("Արտադրության մեջ", "В производстве", "In production"),
  "enum.order.installing": e("Մոնտաժ", "Монтаж", "Installing"),
  "enum.order.closed": e("Փակված", "Закрыт", "Closed"),
  "enum.order.disputed": e("Վեճ", "Спор", "Disputed"),
  "enum.order.refunded": e("Վերադարձված", "Возврат", "Refunded"),
};
for (const [k, v] of Object.entries(cats)) out[`enum.cat.${k}`] = v;
for (const [k, v] of Object.entries(groups)) out[`enum.group.${k}`] = v;
for (const [k, v] of Object.entries(styles)) out[`enum.style.${k}`] = v;
for (const [k, v] of Object.entries(styleSub)) out[`enum.style_sub.${k}`] = v;
for (const [k, v] of Object.entries(styleGroups)) out[`enum.style_group.${k}`] = v;
for (const [k, v] of Object.entries(tiers)) out[`enum.tier.${k}`] = v;
for (const [k, v] of Object.entries(rooms)) out[`enum.room.${k}`] = v;
for (const [k, v] of Object.entries(roles)) out[`enum.role.${k}`] = v;

Object.assign(out, {
  "enum.accuracy.concept": e("Concept Estimate · նախնական գնահատում", "Concept Estimate · ориентировочно", "Concept Estimate"),
  "enum.accuracy.verified": e("Verified Design · ստուգված նախագիծ", "Verified Design · проверенный проект", "Verified Design"),
  "enum.accuracy.production": e("Production Ready · արտադրության համար", "Production Ready · для производства", "Production Ready"),
  "enum.accuracy_hint.concept": e("Միայն լուսանկարներ/տեսանյութ․ երկրաչափությունը և արժեքը մոտավոր են", "Только фото/видео: геометрия и стоимость ориентировочные", "Photos/video only: geometry and cost are indicative"),
  "enum.accuracy_hint.verified": e("Հատակագիծ + ստուգիչ չափեր․ բարձր ճշգրտություն մասնագետի ստուգումից հետո", "План + контрольные размеры: повышенная точность после проверки специалистом", "Plan + control dimensions: higher accuracy after specialist review"),
  "enum.accuracy_hint.production": e("Հաստատված մասնագիտական չափագրություն․ թույլատրվում է պատվիրել ըստ չափերի", "Подтверждённый обмер: можно заказывать изделия по размерам", "Verified survey: made-to-measure orders allowed"),
  "enum.price.confirmed": e("Խանութի գին", "Цена магазина", "Store price"), "enum.price.estimated": e("Մոտավոր", "Ориентировочно", "Estimated"),
  "enum.price.quote_required": e("Ըստ հարցման", "По запросу", "On request"), "enum.price.demo": e("DEMO", "DEMO", "DEMO"), "enum.price.concept": e("Կոնցեպտ", "Концепт", "Concept"),
  "enum.project_status.draft": e("Սևագիր", "Черновик", "Draft"), "enum.project_status.intake": e("Նյութերի վերբեռնում", "Загрузка материалов", "Intake"),
  "enum.project_status.recognized": e("Երկրաչափությունը հաստատված է", "Геометрия подтверждена", "Geometry confirmed"), "enum.project_status.generating": e("ԱԲ-ն ստեղծում է", "ИИ генерирует", "AI is generating"),
  "enum.project_status.ready": e("Տարբերակները պատրաստ են", "Варианты готовы", "Variants ready"), "enum.project_status.approved": e("Հաստատված է", "Утверждён", "Approved"),
  "enum.project_status.ordered": e("Պատվիրված", "Заказ", "Ordered"),
  "enum.job.queued": e("Հերթում", "В очереди", "Queued"), "enum.job.running": e("Ընթացքում", "Выполняется", "Running"), "enum.job.succeeded": e("Ավարտված", "Готово", "Done"),
  "enum.job.failed": e("Ձախողված", "Ошибка", "Failed"), "enum.step.pending": e("սպասում", "ожидание", "pending"), "enum.step.running": e("ընթացքում", "выполняется", "running"),
  "enum.step.done": e("պատրաստ", "готово", "done"), "enum.step.warning": e("ուշադրություն", "внимание", "warning"), "enum.step.failed": e("սխալ", "ошибка", "failed"), "enum.step.skipped": e("բաց թողնված", "пропущено", "skipped"),
  "enum.rfq.draft": e("Սևագիր", "Черновик", "Draft"), "enum.rfq.sent": e("Ուղարկված", "Отправлен", "Sent"), "enum.rfq.quoted": e("Առաջարկը ստացված է", "Получено предложение", "Quoted"),
  "enum.rfq.declined": e("Մերժված", "Отказ", "Declined"), "enum.rfq.expired": e("Ժամկետանց", "Истёк", "Expired"),
  "enum.order.cart": e("Զամբյուղ", "Корзина", "Cart"), "enum.order.requested": e("Հայտ ուղարկված", "Запрошен", "Requested"), "enum.order.confirmed": e("Հաստատված", "Подтверждён", "Confirmed"),
  "enum.order.delivering": e("Առաքվում է", "Доставка", "Delivering"), "enum.order.installed": e("Մոնտաժված", "Смонтирован", "Installed"), "enum.order.cancelled": e("Չեղարկված", "Отменён", "Cancelled"),
  "enum.version_source.ai": e("ԱԲ ավտոպիլոտ", "AI Autopilot", "AI Autopilot"), "enum.version_source.command": e("ԱԲ հրաման", "AI-команда", "AI command"),
  "enum.version_source.manual": e("Ձեռքով", "Вручную", "Manual"), "enum.version_source.restore": e("Վերականգնում", "Восстановление", "Restore"),
  "enum.wall_status.existing": e("գոյություն ունեցող", "существующая", "existing"), "enum.wall_status.demolish": e("ապամոնտաժ", "демонтаж", "demolish"), "enum.wall_status.new": e("նոր", "новая", "new"),
  "enum.material.concrete": e("բետոն", "бетон", "concrete"), "enum.material.brick": e("աղյուս", "кирпич", "brick"), "enum.material.block": e("բլոկ", "блок", "block"),
  "enum.material.drywall": e("գիպսաստվարաթուղթ", "ГКЛ", "drywall"), "enum.material.glass": e("ապակի", "стекло", "glass"),
  "enum.wall_kind.exterior": e("արտաքին", "наружная", "exterior"), "enum.wall_kind.interior": e("ներքին", "внутренняя", "interior"), "enum.wall_kind.partition": e("միջնապատ", "перегородка", "partition"), "enum.wall_kind.balcony": e("պատշգամբի", "балконная", "balcony"),
  "enum.source_status.ok": e("Միակցիչն աշխատում է", "Коннектор работает", "Connector OK"), "enum.source_status.needs_audit": e("Պահանջվում է աուդիտ", "Требуется аудит", "Needs audit"),
  "enum.source_status.needs_feed": e("Անհրաժեշտ է մատակարարի ֆիդ", "Нужен фид поставщика", "Supplier feed needed"), "enum.source_status.rfq_only": e("Միայն հարցում (RFQ)", "Только RFQ", "RFQ only"),
  "enum.source_status.unreachable": e("Անհասանելի", "Недоступен", "Unreachable"), "enum.source_status.blocked": e("Արգելափակված", "Заблокирован", "Blocked"), "enum.source_status.disabled": e("Անջատված", "Выключен", "Disabled"),
  "enum.policy.approved": e("թույլատրված", "разрешён", "approved"), "enum.policy.pending": e("սպասման մեջ", "ожидает", "pending"), "enum.policy.restricted": e("սահմանափակված", "ограничен", "restricted"),
});
export const enums = out;
