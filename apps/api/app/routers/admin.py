"""Platform admin: external sources & connector health, jobs, AI usage, audit."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .. import models as m
from ..ai.orchestrator import get_orchestrator
from ..catalog.connectors.others import build_connector
from ..catalog.discovery import source_dict
from ..config import get_settings
from ..db import get_db
from ..errors import ApiError
from ..jobs.runner import enqueue, job_dict
from ..security import Principal, audit, require

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def src_dict(db: Session, s: m.ExternalSource) -> dict:
    runs = db.scalars(select(m.ExternalConnectorRun).where(m.ExternalConnectorRun.source_id == s.id).order_by(m.ExternalConnectorRun.created_at.desc()).limit(50)).all()
    ok = sum(1 for r in runs if r.status == "ok")
    recs = db.scalar(select(func.count(m.ExternalProductRecord.id)).where(m.ExternalProductRecord.source_id == s.id)) or 0
    pend = db.scalar(select(func.count(m.ExternalProductRecord.id)).where(m.ExternalProductRecord.source_id == s.id, m.ExternalProductRecord.review_status == "pending_review")) or 0
    return {"id": s.id, "key": s.key, "name": s.name, "domain": s.domain, "enabled": s.enabled, "canonical_domain": s.canonical_domain,
            "connector_type": s.connector_type, "live_enabled": s.live_enabled, "policy_status": s.policy_status, "health_status": s.health_status, "categories": s.categories, "languages": s.languages, "method": s.method,
            "connector_status": s.connector_status, "policy": s.policy, "rate_limit_s": s.rate_limit_s, "ttl_h": s.ttl_h, "notes": s.notes,
            "last_check_at": s.last_check_at.isoformat() if s.last_check_at else None, "last_success_at": s.last_success_at.isoformat() if s.last_success_at else None,
            "runs": len(runs), "success_rate": round(ok / len(runs), 2) if runs else None, "avg_latency_ms": round(sum(r.latency_ms for r in runs) / len(runs)) if runs else None,
            "found": sum(r.found for r in runs), "validated": sum(r.validated for r in runs), "rejected": sum(r.rejected for r in runs), "records": recs, "pending_review": pend,
            "last_errors": [e for r in runs[:5] for e in r.errors][:5]}


@router.get("/sources")
def sources(p: Principal = Depends(require("sources:manage")), db: Session = Depends(get_db)):
    return [src_dict(db, s) for s in db.scalars(select(m.ExternalSource).order_by(m.ExternalSource.name))]


class SourcePatch(BaseModel):
    enabled: bool | None = None
    live_enabled: bool | None = None
    policy_status: str | None = None
    rate_limit_s: float | None = None
    ttl_h: dict | None = None
    connector_status: str | None = None
    notes: str | None = None


@router.patch("/sources/{sid}")
def patch_source(sid: str, body: SourcePatch, p: Principal = Depends(require("sources:manage")), db: Session = Depends(get_db)):
    s = db.get(m.ExternalSource, sid)
    if not s:
        raise ApiError(404, "not_found")
    if body.rate_limit_s is not None and body.rate_limit_s < 1:
        raise ApiError(422, "validation", fields=["rate_limit_s"])
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(s, k, v)
    audit(db, p, "source.update", "external_source", sid, data=body.model_dump(exclude_none=True))
    db.commit()
    return src_dict(db, s)


@router.post("/sources/{sid}/test")
def test_source(sid: str, p: Principal = Depends(require("sources:manage")), db: Session = Depends(get_db)):
    s = db.get(m.ExternalSource, sid)
    if not s:
        raise ApiError(404, "not_found")
    conn = build_connector(source_dict(s), live=get_settings().external_fetch_live, cache_lookup=None)
    h = conn.get_connector_health()
    s.last_check_at = datetime.now(timezone.utc)
    if h.status == "ok":
        s.last_success_at = s.last_check_at
    db.add(m.ExternalConnectorRun(source_id=s.id, kind="health", status=h.status, latency_ms=h.latency_ms, errors=[] if h.status == "ok" else [h.message]))
    db.commit()
    return {"status": h.status, "message": h.message, "latency_ms": h.latency_ms, "policy": conn.get_policy_status()}


@router.get("/sources/{sid}/history")
def source_history(sid: str, p: Principal = Depends(require("sources:manage")), db: Session = Depends(get_db)):
    """Connector health history: the last 50 runs and the alert log."""
    s = db.get(m.ExternalSource, sid)
    if not s:
        raise ApiError(404, "not_found")
    runs = db.scalars(select(m.ExternalConnectorRun).where(m.ExternalConnectorRun.source_id == sid).order_by(m.ExternalConnectorRun.created_at.desc()).limit(50)).all()
    return {"runs": [{"at": r.created_at.isoformat(), "kind": r.kind, "status": r.status, "found": r.found, "validated": r.validated, "latency_ms": r.latency_ms,
                      "errors": (r.errors or [])[:2]} for r in runs],
            "alerts": (s.stats or {}).get("alert_log", []), "index": (s.stats or {}).get("index", {}),
            "schedule": {"index_interval_min": (s.policy or {}).get("index_interval_min", 30) if s.connector_type == "jsonld_index" else None,
                         "price_ttl_h": (s.ttl_h or {}).get("price")}}


class IndexIn(BaseModel):
    batch: int = Field(default=60, ge=1, le=300)


@router.post("/sources/{sid}/index")
def index_source(sid: str, body: IndexIn, p: Principal = Depends(require("sources:manage")), db: Session = Depends(get_db)):
    """Queue one background index batch (crawl-delay respected; ~batch × 3 s)."""
    s = db.get(m.ExternalSource, sid)
    if not s:
        raise ApiError(404, "not_found")
    if s.connector_type != "jsonld_index":
        raise ApiError(422, "validation", fields=["connector_type"])

    job = enqueue(db, "source_index", project_id=None, params={"source_id": s.id, "batch": body.batch})
    audit(db, p, "source.index", "external_source", sid, data={"batch": body.batch})
    db.commit()
    return job_dict(job)


@router.get("/quarantine")
def quarantine(p: Principal = Depends(require("audit:read")), db: Session = Depends(get_db)):
    """Uploads rejected by the antivirus (kept 30 days for review; never served)."""
    rows = db.scalars(select(m.AuditEvent).where(m.AuditEvent.action == "asset.quarantined").order_by(m.AuditEvent.created_at.desc()).limit(100))
    return [{"at": e.created_at.isoformat(), "project_id": e.project_id, "user_id": e.user_id, **{k: e.data.get(k) for k in ("filename", "sha256", "signature")}}
            for e in rows]


@router.get("/jobs")
def jobs(p: Principal = Depends(require("jobs:read")), db: Session = Depends(get_db)):
    return [job_dict(j) for j in db.scalars(select(m.GenerationJob).order_by(m.GenerationJob.created_at.desc()).limit(100))]


@router.get("/ai")
def ai(p: Principal = Depends(require("jobs:read")), db: Session = Depends(get_db)):
    rows = db.execute(select(m.AIUsage.task, m.AIUsage.provider, m.AIUsage.model, func.count(), func.sum(m.AIUsage.input_tokens), func.sum(m.AIUsage.output_tokens),
                             func.sum(m.AIUsage.cost_usd), func.avg(m.AIUsage.latency_ms), func.sum(case((m.AIUsage.ok.is_(False), 1), else_=0)))
                      .group_by(m.AIUsage.task, m.AIUsage.provider, m.AIUsage.model)).all()
    return {"providers": get_orchestrator().status(),
            "usage": [{"task": r[0], "provider": r[1], "model": r[2], "calls": r[3], "input_tokens": r[4] or 0, "output_tokens": r[5] or 0, "cost_usd": round(r[6] or 0, 4),
                       "avg_latency_ms": round(r[7] or 0), "failures": r[8] or 0} for r in rows]}


@router.get("/audit")
def audit_log(p: Principal = Depends(require("audit:read")), db: Session = Depends(get_db)):
    return [{"action": a.action, "entity": a.entity, "entity_id": a.entity_id, "project_id": a.project_id, "user_id": a.user_id, "data": a.data, "created_at": a.created_at.isoformat()}
            for a in db.scalars(select(m.AuditEvent).order_by(m.AuditEvent.created_at.desc()).limit(300))]


@router.get("/stats")
def stats(p: Principal = Depends(require("jobs:read")), db: Session = Depends(get_db)):
    def count(model, *where):
        return db.scalar(select(func.count()).select_from(model).where(*where)) or 0

    return {"projects": count(m.Project), "variants": count(m.DesignVariant), "products": count(m.ProductVariant),
            "demo_products": count(m.ProductVariant, m.ProductVariant.price_status == "demo"), "external_records": count(m.ExternalProductRecord),
            "jobs_failed": count(m.GenerationJob, m.GenerationJob.status == "failed"), "documents": count(m.Document), "rfqs": count(m.RFQ),
            "integrations": {"aps": get_settings().aps_enabled, "external_fetch_live": get_settings().external_fetch_live, "ai": get_orchestrator().status()}}
