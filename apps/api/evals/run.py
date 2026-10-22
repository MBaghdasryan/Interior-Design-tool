"""AI evaluation harness → EVAL_REPORT.md.

    docker compose exec api python -m evals.run [--providers gemini,stub] [--suite all|commands|plans] [--limit N] [--out ../../EVAL_REPORT.md]

* commands (32, hy/ru/en): schema-valid rate, operation recall/precision, category and room
  accuracy, stability (two runs → same operations), budget compliance and "no invented SKU"
  after applying the plan to the demo project (in a rolled-back transaction).
* plans (30 synthetic plans, 6 quality modes, exact ground truth): room-count error, room-type
  accuracy, area error (MAPE), door / window count error, scale source.
Each provider is called directly — no silent fallback to the deterministic stub — so failures
(quota, credits, invalid output) show up as failures."""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from app.ai import stub
from app.ai.orchestrator import Orchestrator, load_prompt
from app.ai.providers import AnthropicProvider, GeminiProvider, ImageInput, LLMRequest, OpenAIProvider, StubProvider
from app.ai.schemas import ChangePlan, FloorplanRecognition

HERE = Path(__file__).parent
PROVIDERS = {"gemini": GeminiProvider, "openai": OpenAIProvider, "anthropic": AnthropicProvider, "stub": lambda: StubProvider(stub.HANDLERS)}


def call(provider, task: str, schema, payload: dict, images=None, retries: int = 2):
    from app.ai.orchestrator import TASKS

    req = LLMRequest(task=task, system=load_prompt(task, TASKS[task][1]), user=json.dumps(payload, ensure_ascii=False), schema_name=schema.__name__,
                     json_schema=schema.model_json_schema(), images=images or [])
    err = None
    for attempt in range(retries + 1):
        try:
            t = time.time()
            r = provider.complete_json(req)
            return schema.model_validate(r.data), int((time.time() - t) * 1000), provider.cost(r), None
        except Exception as e:  # noqa: BLE001 - recorded as a failed sample
            err = f"{type(e).__name__}: {str(e)[:160]}"
            time.sleep(2 * (attempt + 1))
    return None, 0, 0.0, err


# ------------------------------------------------------------------ commands
def _demo_context(db):
    from app import models as m
    from app.scene.model import Scene

    proj = db.query(m.Project).filter(m.Project.title.like("Демо%")).first()
    v = db.query(m.DesignVariant).filter_by(project_id=proj.id).first()
    ver = db.get(m.DesignVersion, v.current_version_id)
    sc = Scene.model_validate(ver.scene)
    ctx = {"room_types": sorted({r.type for r in sc.rooms}), "rooms": [{"id": r.id, "type": r.type, "name": r.name} for r in sc.rooms],
           "categories": sorted({o.category for o in sc.objects}), "locked": []}
    return proj, v, ver, ctx


def _sig(plan: ChangePlan) -> list[tuple]:
    return sorted((o.op, o.category or "", o.room_type or "") for o in plan.operations)


def eval_commands(provider, limit: int | None) -> dict:
    from app.catalog.candidates import resolve
    from app.db import SessionLocal
    from app.design.changes import apply_plan
    from app.scene.model import Scene

    cases = json.loads((HERE / "datasets" / "commands.json").read_text(encoding="utf-8"))[:limit]
    rows = []
    with SessionLocal() as db:
        proj, v, ver, ctx = _demo_context(db)
        base_total = (ver.estimate or {}).get("totals", {}).get("known", 0)
        for c in cases:
            plan, ms, cost, err = call(provider, "change_command", ChangePlan, {**ctx, "command": c["command"]})
            row = {"id": c["id"], "lang": c["lang"], "ok": plan is not None, "ms": ms, "cost": cost, "error": err}
            if plan:
                pred = {(o.op, o.category, o.room_type) for o in plan.operations}
                exp = c["expect"]
                hit_op = sum(1 for e in exp if any(p[0] == e["op"] for p in pred))
                hit_cat = sum(1 for e in exp if e["category"] and any(p[0] == e["op"] and p[1] == e["category"] for p in pred))
                hit_room = sum(1 for e in exp if e["room_type"] and any(p[0] == e["op"] and (p[2] or "").startswith(e["room_type"].split("_")[0]) for p in pred))
                row.update(op_recall=hit_op / len(exp), op_precision=(sum(1 for p in pred if any(p[0] == e["op"] for e in exp)) / len(pred)) if pred else 0,
                           cat_acc=(hit_cat / sum(1 for e in exp if e["category"])) if any(e["category"] for e in exp) else None,
                           room_acc=(hit_room / sum(1 for e in exp if e["room_type"])) if any(e["room_type"] for e in exp) else None)
                again, *_ = call(provider, "change_command", ChangePlan, {**ctx, "command": c["command"]})
                row["stable"] = again is not None and _sig(again) == _sig(plan)
                try:  # apply in a transaction that is rolled back: budget + invented-SKU checks
                    res = apply_plan(db, proj, v, ver, Scene.model_validate(ver.scene), plan)["result"]
                    refs = [o.product_variant_id for o in res.scene.objects if o.product_variant_id]
                    row["invented_sku"] = sum(1 for r in refs if resolve(db, r) is None)
                    if c["budget_delta"]:
                        after = res.estimate["totals"]["known"]
                        row["budget_ok"] = after <= base_total  # cheaper or equal; the exact delta is bounded by the catalogue
                        row["budget_saved"] = base_total - after
                except Exception as e:  # noqa: BLE001
                    row["apply_error"] = str(e)[:160]
                finally:
                    db.rollback()
            rows.append(row)
    ok = [r for r in rows if r["ok"]]

    def avg(k):
        vals = [r[k] for r in ok if r.get(k) is not None]
        return round(sum(vals) / len(vals), 3) if vals else None
    budget = [r for r in ok if "budget_ok" in r]
    return {"n": len(rows), "valid_rate": round(len(ok) / len(rows), 3) if rows else 0, "op_recall": avg("op_recall"), "op_precision": avg("op_precision"),
            "category_acc": avg("cat_acc"), "room_acc": avg("room_acc"), "stability": round(sum(1 for r in ok if r.get("stable")) / len(ok), 3) if ok else None,
            "invented_sku_total": sum(r.get("invented_sku", 0) for r in ok), "budget_compliance": f"{sum(1 for r in budget if r['budget_ok'])}/{len(budget)}",
            "by_lang": {lg: avg_lang(ok, lg) for lg in ("hy", "ru", "en")}, "latency_ms": avg("ms"), "cost_usd": round(sum(r["cost"] for r in rows), 4),
            "errors": [f"{r['id']}: {r['error']}" for r in rows if r["error"]][:5], "rows": rows}


def avg_lang(rows, lang):
    vals = [r["op_recall"] for r in rows if r["lang"] == lang and r.get("op_recall") is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


# ------------------------------------------------------------------ plans
def _area(poly) -> float:
    return abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly)))) / 2 / 1e6


TYPE_GROUPS = {"kitchen_living": {"kitchen_living", "living", "kitchen"}, "living": {"living", "kitchen_living"}, "kitchen": {"kitchen", "kitchen_living"},
               "wc": {"wc", "bathroom"}, "bathroom": {"bathroom", "wc"}, "kids": {"kids", "bedroom"}, "bedroom": {"bedroom", "kids"}}


def eval_plans(provider, limit: int | None, plans_dir: Path | None = None) -> dict:
    d = plans_dir or HERE / "datasets" / "plans"
    if not d.exists() and plans_dir is None:
        from .plans import build

        build(d)
    truths = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("plan_*.json"))][:limit]
    rows = []
    for t in truths:
        img = (d / f"{t['id']}.{'jpg' if t['mime'] == 'image/jpeg' else 'png'}").read_bytes()
        rec, ms, cost, err = call(provider, "floorplan_vision", FloorplanRecognition, {"control_dimension": None, "filename": f"{t['id']}.png"},
                                  images=[ImageInput(img, t["mime"])])
        row = {"id": t["id"], "quality": t["quality"], "lang": t["lang"], "ok": rec is not None, "ms": ms, "cost": cost, "error": err}
        if rec:
            pred = [{"type": r.type, "area": r.area_label_m2 or _area(r.polygon)} for r in rec.rooms]
            truth = [{"type": r["type"], "area": r["area_m2"]} for r in t["rooms"]]
            used, type_hits, errs = set(), 0, []
            for tr in sorted(truth, key=lambda x: -x["area"]):  # greedy: closest area among unused predictions
                cand = sorted((abs(p["area"] - tr["area"]), i) for i, p in enumerate(pred) if i not in used)
                if not cand:
                    continue
                _, i = cand[0]
                used.add(i)
                errs.append(abs(pred[i]["area"] - tr["area"]) / tr["area"])
                type_hits += pred[i]["type"] in TYPE_GROUPS.get(tr["type"], {tr["type"]})
            ptotal = sum(p["area"] for p in pred)
            row.update(rooms_true=len(truth), rooms_pred=len(pred), room_count_err=abs(len(pred) - len(truth)), type_acc=type_hits / len(truth),
                       area_mape=sum(errs) / len(errs) if errs else 1.0, total_area_err=abs(ptotal - t["total_area_m2"]) / t["total_area_m2"],
                       doors_err=abs(sum(1 for o in rec.openings if "door" in o.type) - t["doors"]) if t["doors"] is not None else None,
                       windows_err=abs(sum(1 for o in rec.openings if o.type == "window") - t["windows"]) if t["windows"] is not None else None,
                       scale=rec.scale_source)
        rows.append(row)
    ok = [r for r in rows if r["ok"]]

    def avg(k, rs=None):
        rs = ok if rs is None else rs
        vals = [r[k] for r in rs if r.get(k) is not None]
        return round(sum(vals) / len(vals), 3) if vals else None
    return {"n": len(rows), "valid_rate": round(len(ok) / len(rows), 3) if rows else 0, "room_count_exact": round(sum(1 for r in ok if r["room_count_err"] == 0) / len(ok), 3) if ok else None,
            "type_acc": avg("type_acc"), "area_mape": avg("area_mape"), "total_area_err": avg("total_area_err"), "doors_err": avg("doors_err"), "windows_err": avg("windows_err"),
            "scale_from_dimension_text": round(sum(1 for r in ok if r.get("scale") == "dimension_text") / len(ok), 3) if ok else None,
            "by_quality": {q: {"type_acc": avg("type_acc", [r for r in ok if r["quality"] == q]), "area_mape": avg("area_mape", [r for r in ok if r["quality"] == q])}
                           for q in sorted({r["quality"] for r in rows})},
            "latency_ms": avg("ms"), "cost_usd": round(sum(r["cost"] for r in rows), 4), "errors": [f"{r['id']}: {r['error']}" for r in rows if r["error"]][:5], "rows": rows}


# ------------------------------------------------------------------ photos
def eval_photos(provider, photos_dir: Path) -> dict:
    from app.ai.schemas import PhotoElements, PhotoRooms, ViewGroups

    labels = json.loads((photos_dir / "labels.json").read_text(encoding="utf-8"))["photos"]
    images = [ImageInput((photos_dir / f"{x['id']}.jpg").read_bytes(), "image/jpeg") for x in labels]
    rooms, ms1, c1, e1 = call(provider, "photo_rooms", PhotoRooms, {"count": len(images)}, images=images)
    els, ms2, c2, e2 = call(provider, "photo_elements", PhotoElements, {"count": len(images)}, images=images)
    groups, ms3, c3, e3 = call(provider, "view_groups", ViewGroups, {"photos": [r.model_dump() for r in rooms.photos] if rooms else []}, images=images)
    out = {"n": len(labels), "errors": [e for e in (e1, e2, e3) if e], "cost_usd": round(c1 + c2 + c3, 4), "latency_ms": ms1 + ms2 + ms3}
    if rooms:
        pred = {r.index: r.room_type for r in rooms.photos}
        out["type_acc"] = round(sum(pred.get(i) == x["room_type"] for i, x in enumerate(labels)) / len(labels), 3)
        out["type_acc_lenient"] = round(sum(pred.get(i) in TYPE_GROUPS.get(x["room_type"], {x["room_type"]}) for i, x in enumerate(labels)) / len(labels), 3)
        out["per_photo"] = [{"id": x["id"], "truth": x["room_type"], "pred": pred.get(i)} for i, x in enumerate(labels)]
    if groups:
        gi = {}
        for k, g in enumerate(groups.rooms):
            for i in g.photo_indexes:
                gi[i] = k
        pairs = [(i, j) for i in range(len(labels)) for j in range(i + 1, len(labels))]
        same_t = {(i, j) for i, j in pairs if labels[i]["group"] == labels[j]["group"]}
        same_p = {(i, j) for i, j in pairs if i in gi and gi.get(i) == gi.get(j)}
        out["grouping_precision"] = round(len(same_t & same_p) / len(same_p), 3) if same_p else None
        out["grouping_recall"] = round(len(same_t & same_p) / len(same_t), 3) if same_t else None
        out["rooms_found"] = len(groups.rooms)
        out["rooms_true"] = len({x["group"] for x in labels})
    if els:
        win = {e.index: e.windows for e in els.photos}
        out["windows_detected_where_expected"] = f"{sum(1 for i, x in enumerate(labels) if x['room_type'] != 'hallway' and win.get(i, 0) > 0)}/{sum(1 for x in labels if x['room_type'] != 'hallway')}"
    return out


# ------------------------------------------------------------------ report
def pct(v):
    return "—" if v is None else f"{v * 100:.0f}%"


def report(results: dict, out: Path) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    L = [f"# EVAL_REPORT — оценка качества AI ({now})", "",
         "Набор: `apps/api/evals` (команды — `datasets/commands.json`, планы — `evals/plans.py`, синтетические с точной разметкой).",
         "Каждый провайдер вызывается напрямую, без подмены детерминированной заглушкой. Ошибки (квота, кредиты, невалидный JSON) учитываются как провалы.",
         "Стоимость — оценка по числу токенов × `AI_PRICES`, не счёт провайдера.", ""]
    for prov, r in results.items():
        L.append(f"## {prov}")
        if "unavailable" in r:
            L += [f"**Недоступен:** {r['unavailable']}", ""]
            continue
        if "commands" in r:
            c = r["commands"]
            L += ["### AI-команды изменения (hy/ru/en)", "", "| Метрика | Значение |", "|---|---|",
                  f"| Валидный structured output | {pct(c['valid_rate'])} ({c['n']} команд) |", f"| Полнота операций (recall) | {pct(c['op_recall'])} |",
                  f"| Точность операций (precision) | {pct(c['op_precision'])} |", f"| Категория предмета | {pct(c['category_acc'])} |", f"| Помещение | {pct(c['room_acc'])} |",
                  f"| Стабильность (2 прогона → те же операции) | {pct(c['stability'])} |", f"| Выдуманные SKU после применения | {c['invented_sku_total']} |",
                  f"| Соблюдение бюджета (команды «сократи бюджет») | {c['budget_compliance']} |",
                  f"| Полнота по языкам hy / ru / en | {pct(c['by_lang']['hy'])} / {pct(c['by_lang']['ru'])} / {pct(c['by_lang']['en'])} |",
                  f"| Задержка, мс (среднее) | {c['latency_ms']} |", f"| Стоимость прогона, USD | {c['cost_usd']} |", ""]
            if c["errors"]:
                L += ["Ошибки: " + "; ".join(c["errors"]), ""]
        if "plans" in r:
            p = r["plans"]
            L += ["### Распознавание синтетических планов (30, 6 режимов качества)", "", "| Метрика | Значение |", "|---|---|",
                  f"| Валидный structured output | {pct(p['valid_rate'])} ({p['n']} планов) |", f"| Точное число помещений | {pct(p['room_count_exact'])} |",
                  f"| Тип помещения | {pct(p['type_acc'])} |", f"| Ошибка площади помещений (MAPE) | {pct(p['area_mape'])} |",
                  f"| Ошибка общей площади | {pct(p['total_area_err'])} |", f"| Ошибка числа дверей / окон (шт., среднее) | {p['doors_err']} / {p['windows_err']} |",
                  f"| Масштаб взят из размерной строки | {pct(p['scale_from_dimension_text'])} |", f"| Задержка, мс | {p['latency_ms']} |", f"| Стоимость прогона, USD | {p['cost_usd']} |", "",
                  "| Режим качества | Тип помещения | Ошибка площади |", "|---|---|---|"]
            L += [f"| {q} | {pct(v['type_acc'])} | {pct(v['area_mape'])} |" for q, v in p["by_quality"].items()]
            L.append("")
            if p["errors"]:
                L += ["Ошибки: " + "; ".join(p["errors"]), ""]
        if "real_plans" in r:
            p = r["real_plans"]
            L += ["### Реальные планы (6 листов одной реальной квартиры, эталон — экспликация альбома)", "",
                  "Таблица экспликации и штамп вырезаны из изображения; эталон: 5 помещений, 58,13 м².", "", "| Лист | Помещений (эталон 5) | Тип помещения | Ошибка площади | Общая площадь |", "|---|---|---|---|---|"]
            L += [f"| {x['quality'].split(':')[1]} | {x.get('rooms_pred', '—')} | {pct(x.get('type_acc'))} | {pct(x.get('area_mape'))} | {pct(x.get('total_area_err'))} |"
                  if x["ok"] else f"| {x['quality'].split(':')[1]} | ошибка: {x['error']} | | | |" for x in p["rows"]]
            L += ["", f"Среднее: тип {pct(p['type_acc'])}, ошибка площади {pct(p['area_mape'])}, общая площадь {pct(p['total_area_err'])}, точное число помещений {pct(p['room_count_exact'])}.", ""]
        if "photos" in r:
            ph = r["photos"]
            L += ["### Фото квартиры «до ремонта» (8 СИНТЕТИЧЕСКИХ снимков Gemini Image с разметкой)", "", "| Метрика | Значение |", "|---|---|",
                  f"| Тип комнаты (строго / с близкими типами) | {pct(ph.get('type_acc'))} / {pct(ph.get('type_acc_lenient'))} |",
                  f"| Сопоставление ракурсов одной комнаты (precision / recall по парам) | {pct(ph.get('grouping_precision'))} / {pct(ph.get('grouping_recall'))} |",
                  f"| Найдено комнат / в разметке | {ph.get('rooms_found', '—')} / {ph.get('rooms_true', '—')} |",
                  f"| Окна найдены там, где они есть | {ph.get('windows_detected_where_expected', '—')} |",
                  "| Оценка глубины | модель не подключена (DepthProvider) — метрика не измеряется |", f"| Стоимость, USD | {ph['cost_usd']} |", ""]
            if ph.get("per_photo"):
                L += ["Ответы по фото: " + ", ".join(f"{x['id']} {x['truth']}→{x['pred']}" for x in ph["per_photo"]), ""]
            if ph["errors"]:
                L += ["Ошибки: " + "; ".join(ph["errors"]), ""]
    L += ["## Как воспроизвести", "", "```bash", "docker compose exec api python -m evals.run --providers gemini,stub --suite all", "```", "",
          "Синтетические планы проверяют чтение чертежа (стены, подписи, размеры); реальные сканы и фото квартир (N99) — отдельный набор, когда будут материалы."]
    out.write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--providers", default="gemini,stub")
    ap.add_argument("--suite", default="all")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=str(HERE.parent / "EVAL_REPORT.md"))
    ap.add_argument("--real", default=str(HERE / "datasets" / "real"), help="real plan sheets (evals.real_plans); skipped when absent")
    ap.add_argument("--photos", default=str(HERE / "datasets" / "photos"), help="labelled photo set (evals.photos); skipped when absent")
    a = ap.parse_args()
    Orchestrator  # noqa: B018 - imported to register prompts/tasks
    results: dict = {}
    for name in a.providers.split(","):
        p = PROVIDERS[name]()
        if not p.available():
            results[name] = {"unavailable": "нет ключа API"}
            continue
        results[name] = {}
        if a.suite in ("all", "commands"):
            results[name]["commands"] = eval_commands(p, a.limit)
            print(name, "commands", {k: v for k, v in results[name]["commands"].items() if k not in ("rows", "by_lang")})
        if a.suite in ("all", "plans", "real") and Path(a.real).exists() and name != "stub":
            results[name]["real_plans"] = eval_plans(p, None, Path(a.real))
            print(name, "real", {k: v for k, v in results[name]["real_plans"].items() if k not in ("rows", "by_quality")})
        if a.suite in ("all", "photos") and (Path(a.photos) / "labels.json").exists() and name != "stub":
            results[name]["photos"] = eval_photos(p, Path(a.photos))
            print(name, "photos", {k: v for k, v in results[name]["photos"].items() if k != "per_photo"})
        if a.suite in ("all", "plans"):
            results[name]["plans"] = eval_plans(p, a.limit)
            print(name, "plans", {k: v for k, v in results[name]["plans"].items() if k not in ("rows", "by_quality")})
    out = Path(a.out)
    report(results, out)
    (out.with_suffix(".json")).write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("report:", out)


if __name__ == "__main__":
    main()
