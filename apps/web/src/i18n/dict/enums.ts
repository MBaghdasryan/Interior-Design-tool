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
  floor_laminate: e("Լամինատ", "Ламинат", "Laminate"), floor_tile: e("Հատակի կերամոգրանիտ", "Керамогранит пол", "Floor porcelain"), wall_tile: e("Պատի սալիկ", "Плитка настенная", "Wall tile"),
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
  warm_minimal: e("Ջերմ մինիմալիզմ", "Тёплый минимализм", "Warm minimalism"), modern_loft: e("Ժամանակակից լոֆթ", "Современный лофт", "Modern loft"),
  soft_scandi: e("Փափուկ սկանդինավյան", "Мягкий сканди", "Soft Scandi"), contemporary: e("Ժամանակակից", "Современный", "Contemporary"), classic: e("Նեոդասական", "Неоклассика", "Neoclassic"),
};
const styleSub: Record<string, Entry> = {
  warm_minimal: e("Հանգիստ, հարմարավետ, ժամանակից դուրս", "Спокойный, уютный, вне времени", "Calm, cosy, timeless"),
  modern_loft: e("Բնավորություն և տարածության ազատություն", "Характер и свобода пространства", "Character and open space"),
  soft_scandi: e("Թեթևություն, լույս և բնական նյութեր", "Лёгкость, свет и натуральные материалы", "Lightness, daylight and natural materials"),
  contemporary: e("Մաքուր գծեր և ֆունկցիոնալություն", "Чистые линии и функциональность", "Clean lines and function"),
  classic: e("Կաղապարներ, համաչափություն, ազնիվ երանգներ", "Молдинги, симметрия, благородные оттенки", "Mouldings, symmetry, noble tones"),
  economy: e("Խելամիտ բյուջե, նույն լուծումները", "Разумный бюджет, те же решения", "Sensible budget, same solutions"),
  premium: e("Բարձր դասի նյութեր և արտադրանք", "Материалы и изделия высокого класса", "High-end materials and pieces"),
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
