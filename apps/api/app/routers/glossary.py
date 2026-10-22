"""Armenian terminology review (P1-10). A linguist (native-speaking architect) reviews every album
term next to its Russian and English versions, proposes a correction with a comment and approves it;
approved corrections override the album vocabulary immediately (no code change) and are listed in
the XLSX export for the UI dictionaries."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..album import glossary
from ..db import get_db
from ..errors import ApiError
from ..security import Principal, audit, require

router = APIRouter(prefix="/api/v1", tags=["glossary"])


def approved_overrides(db: Session) -> dict[str, str]:
    return {e.term_key: e.hy_proposed for e in db.scalars(select(m.GlossaryEntry).where(m.GlossaryEntry.status == "approved"))}


def glossary_stamp(db: Session) -> str:
    """Changes whenever an approved correction changes → album jobs are not served from the idempotency cache."""
    items = sorted(approved_overrides(db).items())
    return hashlib.sha1(repr(items).encode()).hexdigest()[:8] if items else "0"


def _terms() -> dict[str, dict]:
    return {f"{t['table']}.{t['key']}": t for t in glossary.terms()}


def entry_dict(term: dict, e: m.GlossaryEntry | None) -> dict:
    return {"term_key": f"{term['table']}.{term['key']}", "table": term["table"], "key": term["key"], "hy": term["hy"], "ru": term["ru"], "en": term["en"],
            "proposed": e.hy_proposed if e else None, "comment": e.comment if e else "", "status": e.status if e else "original",
            "author": e.author if e else "", "reviewed_by": e.reviewed_by if e else "", "updated_at": e.updated_at.isoformat() if e and e.updated_at else None}


@router.get("/glossary")
def list_terms(q: str = "", status: str = "", table: str = "", p: Principal = Depends(require("glossary:review")), db: Session = Depends(get_db)):
    entries = {e.term_key: e for e in db.scalars(select(m.GlossaryEntry))}
    out = []
    low = q.strip().lower()
    for k, t in _terms().items():
        row = entry_dict(t, entries.get(k))
        if table and t["table"] != table:
            continue
        if status and row["status"] != status:
            continue
        if low and not any(low in (str(row[f]) or "").lower() for f in ("key", "hy", "ru", "en", "proposed")):
            continue
        out.append(row)
    counts = {s: sum(1 for e in entries.values() if e.status == s) for s in ("proposed", "approved", "rejected")}
    return {"items": out, "total": len(_terms()), "counts": counts, "tables": sorted({t["table"] for t in _terms().values()})}


class ProposeIn(BaseModel):
    hy: str = Field(min_length=1, max_length=500)
    comment: str = Field(default="", max_length=1000)


@router.put("/glossary/{term_key}")
def propose(term_key: str, body: ProposeIn, p: Principal = Depends(require("glossary:review")), db: Session = Depends(get_db)):
    t = _terms().get(term_key)
    if not t:
        raise ApiError(404, "not_found")
    e = db.scalar(select(m.GlossaryEntry).where(m.GlossaryEntry.term_key == term_key))
    if body.hy.strip() == t["hy"]:  # back to the original wording
        if e:
            db.delete(e)
        audit(db, p, "glossary.revert", "glossary", term_key)
        db.commit()
        return entry_dict(t, None)
    e = e or m.GlossaryEntry(term_key=term_key, hy_original=t["hy"])
    e.hy_proposed, e.comment, e.status, e.author, e.reviewed_by = body.hy.strip(), body.comment.strip(), "proposed", p.user.email, ""
    db.add(e)
    audit(db, p, "glossary.propose", "glossary", term_key, data={"hy": e.hy_proposed})
    db.commit()
    return entry_dict(t, e)


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")


@router.post("/glossary/{term_key}/decision")
def decide(term_key: str, body: DecisionIn, p: Principal = Depends(require("glossary:review")), db: Session = Depends(get_db)):
    t = _terms().get(term_key)
    e = db.scalar(select(m.GlossaryEntry).where(m.GlossaryEntry.term_key == term_key))
    if not t or not e:
        raise ApiError(404, "not_found")
    e.status, e.reviewed_by, e.updated_at = body.decision, p.user.email, datetime.now(timezone.utc)
    audit(db, p, f"glossary.{body.decision}", "glossary", term_key, data={"hy": e.hy_proposed})
    db.commit()
    return entry_dict(t, e)


@router.get("/glossary/export.xlsx")
def export(p: Principal = Depends(require("glossary:review")), db: Session = Depends(get_db)):
    import io

    from openpyxl import Workbook

    entries = {e.term_key: e for e in db.scalars(select(m.GlossaryEntry))}
    wb = Workbook()
    ws = wb.active
    ws.append(["table", "key", "hy", "ru", "en", "hy_proposed", "status", "comment", "author", "reviewed_by"])
    for k, t in _terms().items():
        e = entries.get(k)
        ws.append([t["table"], t["key"], t["hy"], t["ru"], t["en"], e.hy_proposed if e else "", e.status if e else "", e.comment if e else "",
                   e.author if e else "", e.reviewed_by if e else ""])
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="album_terms_review.xlsx"'})


class GrantIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    role: str = Field(pattern="^(linguist|verifier)$")


@router.post("/admin/roles")
def grant_role(body: GrantIn, p: Principal = Depends(require("sources:manage")), db: Session = Depends(get_db)):
    """Platform admin grants a platform-level role (linguist / verifier) to an existing account."""
    u = db.scalar(select(m.User).where(m.User.email == body.email.strip().lower()))
    if not u:
        raise ApiError(404, "not_found")
    org = db.scalar(select(m.Organization).where(m.Organization.kind == "platform").limit(1))
    if not db.scalar(select(m.Membership).where(m.Membership.user_id == u.id, m.Membership.org_id == org.id, m.Membership.role == body.role)):
        db.add(m.Membership(user_id=u.id, org_id=org.id, role=body.role))
    audit(db, p, "role.grant", "user", u.id, data={"role": body.role})
    db.commit()
    return {"ok": True, "email": u.email, "role": body.role}
