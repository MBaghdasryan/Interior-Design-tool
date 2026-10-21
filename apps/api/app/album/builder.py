"""Album assembly from DB entities."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..config import get_settings
from ..scene.model import Scene
from .draw import AlbumMeta
from .sheets import AlbumBuilder

# bump when sheet rendering changes, so an album job for the same version is not served from the idempotency cache
RENDERER_VERSION = "2026-10-22.4"
ACCURACY = {"concept": "Concept Estimate", "verified": "Verified Design", "production": "Production Ready"}


def build_album(db: Session, project: m.Project, variant: m.DesignVariant, version: m.DesignVersion, *, lang: str = "hy",
                sections: set[int] | None = None) -> tuple[bytes, list[dict]]:
    s = get_settings()
    org = db.get(m.Organization, project.org_id)
    tb = (org.settings or {}).get("title_block", {}) if org else {}
    base_row = db.scalar(select(m.BaseScene).where(m.BaseScene.project_id == project.id).order_by(m.BaseScene.version.desc()).limit(1))
    scene = Scene.model_validate(version.scene)
    base = Scene.model_validate(base_row.data) if base_row else scene
    est = version.estimate or {}
    approvals = [{"created_at": a.created_at.isoformat(), "actor_name": a.actor_name, "actor_role": a.actor_role, "decision": a.decision}
                 for a in db.scalars(select(m.Approval).where(m.Approval.project_id == project.id).order_by(m.Approval.created_at))]
    meta = AlbumMeta(
        lang=lang, company=tb.get("company") or (org.name if org else s.brand_name), tagline=tb.get("tagline", "interior design"),
        phone=tb.get("phone", ""), address=tb.get("address", ""), email=tb.get("email", ""), project_address=project.address or project.title,
        client=project.client_name, designer=project.designer_name, brand=s.brand_name, accuracy_label=ACCURACY.get(project.accuracy_level, project.accuracy_level),
        demo=any(ln.get("price_status") == "demo" for ln in est.get("lines", [])),
    )
    viewer_url = f"{s.public_base_url}/client/{project.share_token}"
    builder = AlbumBuilder(scene, base, est, version.issues or [], meta, project={"confidence": project.confidence},
                           variant={"title": variant.title, "style": variant.style, "tier": variant.tier}, viewer_url=viewer_url, approvals=approvals)
    return builder.build(sections)
