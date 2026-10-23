"""External Catalog Discovery: Product Need List → source routing → connectors →
normalisation/dedup → scoring → isolated Project Catalog Snapshot. The AI design
step only ever receives the shortlist produced here."""
from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..config import get_settings
from ..scene.layout import PROGRAMS
from ..scene.model import Scene
from .candidates import Candidate, candidate_from_record, load_internal, score
from .connectors.base import NeedQuery, SearchFilters
from .connectors.others import RfqConnector, build_connector
from .normalize import fingerprint
from .schema import NormalizedExternalProduct
from .taxonomy import group_of, sources_for

MATERIAL_NEEDS = ["floor_parquet", "floor_tile", "wall_tile", "wall_paint", "wall_panel", "putty", "tile_adhesive", "drywall"]
LIGHT_NEEDS = ["spot_light", "pendant_light", "track_light", "led_strip", "wall_light"]
DOOR_NEEDS = {"door": "door_interior", "sliding_door": "door_sliding", "entrance_door": "door_entrance"}
DECOR_NEEDS = ["curtains"]


def build_needs(scene: Scene, brief: dict) -> list[dict]:
    """Product Need List with room-level constraints (addon §8 step 1)."""
    from ..scene.geometry import room_edges

    needs: list[dict] = []
    tier = brief.get("budget_tier", "comfort")
    for room in scene.rooms:
        edges = room_edges(scene, room)
        longest = max((t - s for e in edges for s, t in e.free_spans()), default=0)
        for cat, qty, req in PROGRAMS.get(room.type, []):
            if cat == "storage_system" and brief.get("storage_level") == "low":
                continue
            if cat == "desk" and room.type == "bedroom" and not brief.get("work_from_home"):
                continue
            needs.append({"key": f"{room.id}:{cat}", "room_id": room.id, "category": cat, "qty": qty, "required": req,
                          "max_width_mm": round(longest - 100) if longest and cat not in ("rug", "plant") else None, "tier": tier})
    for cat in MATERIAL_NEEDS + LIGHT_NEEDS + DECOR_NEEDS:
        needs.append({"key": f"_:{cat}", "room_id": None, "category": cat, "qty": 1, "required": False, "max_width_mm": None, "tier": tier})
    for op_type, cat in DOOR_NEEDS.items():
        if any(o.type == op_type for o in scene.openings):
            needs.append({"key": f"_:{cat}", "room_id": None, "category": cat, "qty": sum(1 for o in scene.openings if o.type == op_type), "required": False, "max_width_mm": None, "tier": tier})
    return needs


def _cache_lookup_factory(db: Session) -> Callable[[str, str], list[NormalizedExternalProduct]]:
    def lookup(source_id: str, category: str) -> list[NormalizedExternalProduct]:
        rows = db.scalars(select(m.ExternalProductRecord).where(m.ExternalProductRecord.source_id == source_id,
                                                                m.ExternalProductRecord.normalized_category == category,
                                                                m.ExternalProductRecord.review_status != "rejected"))
        # products found without JSON-LD (microdata / OpenGraph / HTML heuristics) are used only once approved
        return [NormalizedExternalProduct.model_validate(r.data) for r in rows
                if r.review_status == "approved" or not str((r.data or {}).get("parser_version", "")).startswith("layered-")]

    return lookup


def upsert_record(db: Session, p: NormalizedExternalProduct, existing: m.ExternalProductRecord | None = None) -> m.ExternalProductRecord:
    """`existing` = the record being refreshed (updated in place even if its key was derived differently)."""
    key = p.sku or p.external_product_id or fingerprint(p.source_key, p.brand, p.name, p.color)
    rec = existing or db.scalar(select(m.ExternalProductRecord).where(m.ExternalProductRecord.source_id == p.external_source_id, m.ExternalProductRecord.external_key == key))
    data = p.model_dump(mode="json")
    if rec:
        prev = rec.data
        # keep both values when a critical field changes inconsistently
        if prev.get("price_amd") and p.price_amd and abs(prev["price_amd"] - p.price_amd) / prev["price_amd"] > 0.5:
            data.setdefault("disputed_fields", {})["price_amd"] = {"previous": prev["price_amd"], "current": p.price_amd}
            data["manual_confirmation_required"] = True
        rec.data = data
        rec.price_amd = p.price_amd
        rec.normalized_category = p.normalized_category
        rec.confidence = p.confidence
        rec.canonical_url = p.canonical_url
        rec.retrieved_at = p.retrieved_at
    else:
        rec = m.ExternalProductRecord(source_id=p.external_source_id, external_key=key, canonical_url=p.canonical_url, data=data,
                                      price_amd=p.price_amd, normalized_category=p.normalized_category, confidence=p.confidence,
                                      review_status="pending_review" if p.manual_confirmation_required else "auto")
        db.add(rec)
    db.flush()
    return rec


def source_dict(s: m.ExternalSource) -> dict:
    return {"id": s.id, "key": s.key, "name": s.name, "domain": s.domain, "allowed_hosts": s.allowed_hosts, "categories": s.categories,
            "method": s.method, "connector_type": s.connector_type, "live_enabled": s.live_enabled, "connector_status": s.connector_status, "policy": s.policy, "rate_limit_s": s.rate_limit_s, "stats": s.stats}


def run_discovery(db: Session, project: m.Project, scene: Scene, brief: dict, *, job_id: str | None = None,
                  progress: Callable[[str, dict], None] | None = None) -> m.ProjectCatalogSnapshot:
    s = get_settings()
    ext = project.external_settings or {}
    filters = SearchFilters(max_price_amd=ext.get("max_price_amd"), only_priced=bool(ext.get("only_priced")),
                            only_available=bool(ext.get("only_available")), allow_quote=ext.get("allow_quote", True), city=ext.get("city", "Ереван"))
    wanted = set(ext.get("sources") or [])
    sources = [x for x in db.scalars(select(m.ExternalSource).where(m.ExternalSource.enabled.is_(True)))
               if not wanted or x.key in wanted]
    by_key = {x.key: x for x in sources}
    needs = build_needs(scene, brief)
    db.query(m.ProjectProductNeed).filter(m.ProjectProductNeed.project_id == project.id).delete()
    need_rows = {}
    for n in needs:
        row = m.ProjectProductNeed(project_id=project.id, key=n["key"], category=n["category"], room_id=n["room_id"], qty=n["qty"],
                                   constraints={"max_width_mm": n["max_width_mm"], "required": n["required"]})
        db.add(row)
        need_rows[n["key"]] = row
    db.flush()
    counters = {"sources_checked": 0, "sources_total": len(sources), "found": 0, "validated": 0, "no_price": 0, "quote_required": 0, "stale_or_doubtful": 0,
                "needs_total": len(needs), "needs_covered": 0, "rfq_needs": 0}
    if progress:
        progress("needs", counters)
    lookup = _cache_lookup_factory(db)
    snap = m.ProjectCatalogSnapshot(project_id=project.id, job_id=job_id, expires_at=datetime.now(timezone.utc) + timedelta(hours=s.external_price_ttl_h),
                                    settings={**ext, "sources": [x.key for x in sources]}, counters={})
    db.add(snap)
    db.flush()
    from .net import SafeFetcher

    fetcher = SafeFetcher()
    fetcher.max_requests = s.external_discovery_max_requests
    connectors = {x.key: build_connector(source_dict(x), live=s.external_fetch_live, cache_lookup=lookup, fetcher=fetcher) for x in sources}
    checked: set[str] = set()
    for n in needs:
        routed = [k for k in sources_for(n["category"]) if k in connectors]
        found_any = False
        for k in routed:
            conn = connectors[k]
            checked.add(k)
            t = time.time()
            try:
                items = conn.search_products(NeedQuery(key=n["key"], category=n["category"], max_width_mm=n["max_width_mm"]), filters)
                status = "ok"
                errs: list = []
            except Exception as e:  # connector failure never breaks the pipeline
                items, status, errs = [], "error", [str(e)[:300]]
            if isinstance(conn, RfqConnector) and conn.rfq_supported(n["category"]):
                db.add(m.ProjectCatalogSnapshotItem(snapshot_id=snap.id, need_id=need_rows[n["key"]].id, status="quote_required",
                                                    reason=f"{by_key[k].name}: индивидуальное изделие — цена по запросу (RFQ)", risk="Цена неизвестна до ответа поставщика"))
                counters["rfq_needs"] += 1
                counters["quote_required"] += 1
            for p in items:
                rec = upsert_record(db, p)
                cand = candidate_from_record(rec, by_key[k])
                sc, br = score(cand, category=n["category"], style=None, tier=n["tier"], target_price=None, max_width=n["max_width_mm"])
                st = "quote_required" if p.quote_required else ("validated" if p.confidence >= 0.6 and not p.manual_confirmation_required else "discovered")
                db.add(m.ProjectCatalogSnapshotItem(snapshot_id=snap.id, need_id=need_rows[n["key"]].id, record_id=rec.id, status=st, score=sc, score_breakdown=br,
                                                    reason=f"{by_key[k].name}: {p.name[:120]}", risk="; ".join(p.validation_warnings[:2])))
                counters["found"] += 1
                counters["validated"] += st == "validated"
                counters["no_price"] += p.price_value is None
                counters["quote_required"] += p.quote_required
                counters["stale_or_doubtful"] += bool(p.disputed_fields) or p.confidence < 0.5
                found_any = True
            run = m.ExternalConnectorRun(source_id=by_key[k].id, project_id=project.id, kind="discovery", status=status, found=len(items),
                                         validated=sum(1 for p in items if p.confidence >= 0.6), latency_ms=int((time.time() - t) * 1000), errors=errs)
            db.add(run)
            db.flush()
            from .maintenance import evaluate_run

            evaluate_run(db, by_key[k], run)
        counters["needs_covered"] += found_any
        counters["sources_checked"] = len(checked)
        if progress:
            progress("search", counters)
    # rank items per need and mark the top-1 as selected, next 2 as alternatives
    items_by_need: dict[str, list[m.ProjectCatalogSnapshotItem]] = {}
    db.flush()
    for it in db.scalars(select(m.ProjectCatalogSnapshotItem).where(m.ProjectCatalogSnapshotItem.snapshot_id == snap.id)):
        items_by_need.setdefault(it.need_id or "", []).append(it)
    for lst in items_by_need.values():
        lst.sort(key=lambda x: -x.score)
        for rank, it in enumerate(lst):
            it.rank = rank
            if rank == 0 and it.status == "validated":
                it.status = "selected"
    counters["live_requests"] = fetcher.requests_made
    snap.counters = counters
    db.flush()
    if progress:
        progress("snapshot", counters)
    return snap


def snapshot_candidates(db: Session, snap: m.ProjectCatalogSnapshot | None) -> dict[str, list[Candidate]]:
    """Candidates from the snapshot keyed by category (usable statuses only)."""
    out: dict[str, list[Candidate]] = {}
    if not snap:
        return out
    for it in snap.items:
        if not it.record_id or it.status in ("rejected", "unavailable", "stale"):
            continue
        rec = db.get(m.ExternalProductRecord, it.record_id)
        if not rec:
            continue
        c = candidate_from_record(rec, db.get(m.ExternalSource, rec.source_id))
        out.setdefault(c.category, []).append(c)
    return out


def internal_candidates(db: Session, include_demo: bool = True) -> dict[str, list[Candidate]]:
    out: dict[str, list[Candidate]] = {}
    for c in load_internal(db, include_demo=include_demo):
        out.setdefault(c.category, []).append(c)
    return out


def group_for_need(cat: str) -> str:
    return group_of(cat)
