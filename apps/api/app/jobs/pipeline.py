"""AI Autopilot pipeline job. Every step reports real numbers produced by the
step itself — no decorative progress."""
from __future__ import annotations

from sqlalchemy import select

from .. import models as m
from ..ai.orchestrator import get_orchestrator
from ..ai.providers import ProviderError
from ..catalog.discovery import run_discovery
from ..catalog.taxonomy import STYLES
from ..design.engine import TIER_TITLES, generate_variants
from ..scene.geometry import polygon_area
from ..scene.model import Scene
from ..scene.rules import run_rules
from .runner import JobContext, handler

CATALOG_STEPS = [
    ("cat_needs", "Определяем, какие товары нужны", "catalog"),
    ("cat_search", "Ищем в выбранных магазинах", "catalog"),
    ("cat_compare", "Сравниваем цены и размеры", "catalog"),
    ("cat_availability", "Проверяем доступность", "catalog"),
    ("cat_snapshot", "Создаём каталог проекта", "catalog"),
]
DESIGN_STEPS = [
    ("normalize", "Загрузка и нормализация", "design"),
    ("rooms", "Распознавание помещений", "design"),
    ("geometry", "Реконструкция геометрии", "design"),
    ("conflicts", "Поиск противоречий", "design"),
    ("brief", "Формирование технического задания", "design"),
    ("layout", "Построение планировки", "design"),
    ("style", "Создание стиля и палитры", "design"),
    ("products", "Подбор реальных товаров", "design"),
    ("dims", "Проверка габаритов", "design"),
    ("materials", "Расчёт материалов", "design"),
    ("prices", "Проверка цен и наличия", "design"),
    ("delivery", "Расчёт доставки и монтажа", "design"),
    ("visuals", "Генерация визуализаций", "design"),
    ("assemble", "Сборка результата", "design"),
]


def latest_base(db, project_id: str) -> m.BaseScene | None:
    return db.scalar(select(m.BaseScene).where(m.BaseScene.project_id == project_id).order_by(m.BaseScene.version.desc()).limit(1))


@handler("pipeline")
def pipeline(ctx: JobContext) -> dict:
    db = ctx.db
    project = db.get(m.Project, ctx.job.project_id)
    external = project.product_source == "external"
    ctx.define_steps((CATALOG_STEPS if external else []) + DESIGN_STEPS)
    base_row = latest_base(db, project.id)
    if not base_row:
        raise RuntimeError("Нет геометрии квартиры: загрузите план и подтвердите помещения")
    base = Scene.model_validate(base_row.data)
    orch = get_orchestrator()

    # ---------------- brief (needed for the need list) ----------------
    brief_payload = {"preferences": project.preferences or {}, "interview": (project.preferences or {}).get("interview", ""),
                     "rooms": [{"type": r.type, "name": r.name} for r in base.rooms]}
    try:
        brief_model, brief_provider = orch.run("design_brief", brief_payload, db=db, project_id=project.id, stub_on_quota=True)
        brief = brief_model.model_dump()
    except ProviderError as e:
        brief, brief_provider = {"budget_tier": (project.preferences or {}).get("budget_tier", "comfort"), "styles": [], "assumptions": [str(e)[:200]]}, "fallback"
    prefs = project.preferences or {}
    if prefs.get("styles"):
        brief["styles"] = prefs["styles"]
    if prefs.get("budget_tier"):
        brief["budget_tier"] = prefs["budget_tier"]
    if prefs.get("budget_amd"):
        brief["budget_amd"] = prefs["budget_amd"]
    project.brief = brief
    db.commit()

    # ---------------- external catalog phase ----------------
    snap = None
    if external:
        def prog(stage: str, c: dict):
            ctx.counters(**c)
        ctx.start("cat_needs")
        ctx.start("cat_search")
        snap = run_discovery(db, project, base, brief, job_id=ctx.job.id, progress=prog)
        c = snap.counters
        ctx.done("cat_needs", f"{c['needs_total']} потребностей по {len(base.rooms)} помещениям", needs=c["needs_total"], rooms=len(base.rooms))
        ctx.done("cat_search", f"Источников проверено: {c['sources_checked']} из {c['sources_total']}; найдено товаров: {c['found']}",
                 status="done" if c["found"] else "warning", checked=c["sources_checked"], total=c["sources_total"], found=c["found"])
        ctx.start("cat_compare")
        ctx.done("cat_compare", f"Прошли проверку: {c['validated']}; без цены: {c['no_price']}; сомнительные: {c['stale_or_doubtful']}",
                 status="done" if c["validated"] else "warning", validated=c["validated"], no_price=c["no_price"], doubtful=c["stale_or_doubtful"])
        ctx.start("cat_availability")
        ctx.done("cat_availability", "Наличие подтверждено только разметкой магазина — перед заказом требуется перепроверка" if c["found"] else
                 "Нет внешних позиций для проверки", status="warning", found=c["found"])
        ctx.start("cat_snapshot")
        msg = f"Снимок каталога проекта: {len(snap.items)} позиций, покрыто потребностей {c['needs_covered']}/{c['needs_total']}"
        if c["needs_covered"] < c["needs_total"]:
            msg += ". Недостающие позиции будут взяты из DEMO-каталога и помечены"
        ctx.done("cat_snapshot", msg, status="done" if c["needs_covered"] == c["needs_total"] else "warning", items=len(snap.items), covered=c["needs_covered"], total=c["needs_total"])

    # ---------------- design phase ----------------
    assets = db.scalars(select(m.SourceAsset).where(m.SourceAsset.project_id == project.id)).all()
    ctx.start("normalize")
    ctx.done("normalize", f"Исходных файлов: {len(assets)}; геометрия v{base_row.version}" + (" (подтверждена)" if base_row.confirmed else " (не подтверждена)"),
             status="done" if base_row.confirmed else "warning", files=len(assets), version=base_row.version, confirmed=base_row.confirmed)
    ctx.start("rooms")
    area = sum(polygon_area(r.polygon) for r in base.rooms if r.type != "balcony") / 1e6
    ctx.done("rooms", f"{len(base.rooms)} помещений, {area:.1f} м²: " + ", ".join(r.name for r in base.rooms), n=len(base.rooms), area=round(area, 1), room_types=[r.type for r in base.rooms])
    ctx.counters(rooms=len(base.rooms), area_m2=round(area, 1))
    ctx.start("geometry")
    low = [w.id for w in base.walls if w.confidence < 0.75]
    ctx.done("geometry", f"Стен: {len(base.walls)}, проёмов: {len(base.openings)}; низкая уверенность: {', '.join(low) or 'нет'}",
             status="warning" if low else "done", walls=len(base.walls), openings=len(base.openings), low=low)
    ctx.start("conflicts")
    struct = [i for i in run_rules(base, {}, only=["structure"]) if i["severity"] != "pass"]
    crit = [a for a in base.assumptions if a.severity == "critical"]
    ctx.done("conflicts", f"Предупреждений по конструктиву: {len(struct)}; критических допущений: {len(crit)}",
             status="warning" if struct or crit else "done", structural=len(struct), critical=len(crit))
    ctx.start("brief")
    ctx.done("brief", f"ТЗ сформировано ({'правила разработки' if brief_provider == 'stub' else brief_provider}); стили: "
             + (", ".join(STYLES[s]["ru"] for s in brief.get("styles", []) if s in STYLES) or "на выбор ИИ")
             + f"; бюджет: {TIER_TITLES.get(brief.get('budget_tier', 'comfort'))}", provider=brief_provider, styles=brief.get("styles", []), tier=brief.get("budget_tier", "comfort"))

    ctx.start("layout")
    results = generate_variants(db, project, base, brief, snap)
    ctx.done("layout", "; ".join(f"{r.plan.title}: {len(r.scene.objects)} предметов" for r in results), variants=[{"style": r.plan.style, "tier": r.plan.tier, "items": len(r.scene.objects)} for r in results])
    ctx.start("style")
    ctx.done("style", "; ".join(f"{r.plan.title} — палитра {len(STYLES[r.plan.style]['palette'])} цветов" for r in results), variants=[{"style": r.plan.style, "colors": len(STYLES[r.plan.style]["palette"])} for r in results])
    ctx.start("products")
    src = results[0].sourcing
    ctx.counters(products=sum(len(r.scene.objects) for r in results) // len(results), demo_fallback=src["demo_fallback"], external_used=src["external"])
    ctx.done("products", f"Из внешнего каталога: {src['external']}, из внутреннего: {src['internal']}, DEMO-подстановки: {src['demo_fallback']}"
             + (f"; не найдено: {', '.join(sorted(set(src['missing'])))}" if src["missing"] else ""),
             status="warning" if src["demo_fallback"] or src["missing"] else "done", external=src["external"], internal=src["internal"], demo=src["demo_fallback"], missing=sorted(set(src["missing"])))
    ctx.start("dims")
    unplaced = sum(len(r.unplaced) for r in results)
    blocks = sum(r.metrics["issues"]["block"] for r in results)
    ctx.done("dims", f"Правил эргономики: {results[0].metrics['issues']['rules']}; блокирующих: {blocks}; не поместилось предметов: {unplaced}",
             status="warning" if unplaced or blocks else "done", rules=results[0].metrics["issues"]["rules"], blocks=blocks, unplaced=unplaced)
    ctx.start("materials")
    a = results[0].estimate["areas"]
    ctx.done("materials", f"Пол {a['floor_m2']} м², стены {a['walls_m2']} м², плитка {a['tile_m2']} м², окраска {a['paint_m2']} м²", floor=a["floor_m2"], walls=a["walls_m2"], tile=a["tile_m2"], paint=a["paint_m2"])
    ctx.start("prices")
    t = results[0].estimate["totals"]
    ctx.done("prices", f"Подтверждённых цен: {t['confirmed']:,} AMD; DEMO: {t['demo']:,}; по запросу: {t['quote_required_lines']} поз.".replace(",", " "),
             status="warning" if t["demo"] or t["quote_required_lines"] else "done", confirmed=t["confirmed"], demo=t["demo"], quote=t["quote_required_lines"])
    ctx.start("delivery")
    dl = [ln for ln in results[0].estimate["lines"] if ln["group"] in ("delivery", "installation")]
    ctx.done("delivery", f"Поставщиков: {sum(1 for ln in dl if ln['group'] == 'delivery')}; макс. срок поставки {results[0].metrics['lead_days_max']} дн.", suppliers=sum(1 for ln in dl if ln["group"] == "delivery"), lead=results[0].metrics["lead_days_max"])
    ctx.start("visuals")
    ctx.done("visuals", "Провайдер изображений не подключён — сформированы схематические 3D-виды из сцены (без выдуманных товаров)", status="warning", provider="none")

    ctx.start("assemble")
    for old in db.scalars(select(m.DesignVariant).where(m.DesignVariant.project_id == project.id, m.DesignVariant.status != "archived")):
        if old.status != "approved":
            old.status = "archived"
    ids = []
    for i, r in enumerate(results):
        copy_payload = {"style_title": STYLES[r.plan.style]["ru"], "style_subtitle": STYLES[r.plan.style]["subtitle"], "tier_title": TIER_TITLES[r.plan.tier]}
        try:
            copy, _ = orch.run("variant_copy", copy_payload, db=db, project_id=project.id, stub_on_quota=True)
            desc = copy.description
        except ProviderError:
            desc = ""
        v = m.DesignVariant(project_id=project.id, key=r.plan.key, title=r.plan.title, subtitle=r.plan.subtitle, description=desc, style=r.plan.style,
                            tier=r.plan.tier, mode="concept" if project.product_source == "concept" else "real", status="selected" if i == 0 else "draft",
                            palette=STYLES[r.plan.style]["palette"], metrics=r.metrics)
        db.add(v)
        db.flush()
        ver = m.DesignVersion(variant_id=v.id, number=1, scene=r.scene.model_dump(mode="json"), estimate=r.estimate, issues=r.issues,
                              change_summary={"selection": r.selection, "extras": {}, "note": "Сгенерировано AI Autopilot"}, source="ai")
        db.add(ver)
        db.flush()
        v.current_version_id = ver.id
        ids.append(v.id)
    project.status = "ready"
    db.commit()
    ctx.done("assemble", f"Создано вариантов: {len(results)}", n=len(results))
    return {"variant_ids": ids, "snapshot_id": snap.id if snap else None}
