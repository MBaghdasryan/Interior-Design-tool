"""Cross-project workspace sections: order registry (mockup 32), CRM clients and funnel, tasks and team workload,
project conversation (team-only notes and messages shown to the client)."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import false, func, or_, select
from sqlalchemy.orm import Session

from .. import models as m
from ..db import get_db
from ..errors import ApiError
from ..security import Principal, audit, current_principal, project_access
from .commerce import order_dict

router = APIRouter(prefix="/api/v1", tags=["workspace"])

ACTIVE = ("requested", "confirmed", "in_production", "delivering", "installing", "disputed")
# stage chain shown per order: the status that completes the stage, in order
STAGES = [("confirmed", "confirmed"), ("production", "in_production"), ("delivery", "delivering"), ("installation", "installing"), ("closed", "closed")]
RANK = {"requested": 0, "confirmed": 1, "in_production": 2, "delivering": 3, "installing": 4, "closed": 5}


def _order_scope(p: Principal, db: Session):
    """Platform admin: all orders; bureau staff: orders of their organisations' projects; supplier staff: orders to their supplier."""
    stmt = select(m.Order).where(m.Order.status != "cart")
    if p.is_platform_admin:
        return stmt
    sup_ids = list(db.scalars(select(m.Supplier.id).where(m.Supplier.org_id.in_(p.org_ids)))) if p.org_ids else []
    proj_ids = select(m.Project.id).where(m.Project.org_id.in_(p.org_ids))
    return stmt.where(or_(m.Order.project_id.in_(proj_ids), m.Order.supplier_id.in_(sup_ids) if sup_ids else false()))


def _amount(d: dict) -> int:
    if d.get("quote"):
        return int(d["quote"]["total_amd"] or 0)
    t = d.get("totals") or {}
    return int((t.get("goods") or 0) + (t.get("delivery") or 0) + (t.get("installation") or 0))


def _stages(o: m.Order) -> list[dict]:
    reached = {h.get("to"): h.get("at") for h in (o.history or [])}
    r = RANK.get(o.status, -1)
    out = []
    for key, status in STAGES:
        done = RANK.get(status, 99) <= r or status in reached
        cur = RANK.get(status) == r + 1 and o.status not in ("cancelled", "refunded", "disputed")
        out.append({"key": key, "state": "done" if done else ("current" if cur else "planned"), "at": reached.get(status)})
    return out


@router.get("/orders")
def order_registry(status: str = "", supplier_id: str = "", project_id: str = "", q: str = "", days: int = Query(0, ge=0, le=3650),
                   p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    stmt = _order_scope(p, db)
    if status == "active":
        stmt = stmt.where(m.Order.status.in_(ACTIVE))
    elif status:
        stmt = stmt.where(m.Order.status == status)
    if supplier_id:
        stmt = stmt.where(m.Order.supplier_id == supplier_id)
    if project_id:
        stmt = stmt.where(m.Order.project_id == project_id)
    if days:
        stmt = stmt.where(m.Order.created_at >= datetime.now(timezone.utc) - timedelta(days=days))
    orders = db.scalars(stmt.order_by(m.Order.created_at.desc()).limit(500)).all()
    projects = {x.id: x for x in db.scalars(select(m.Project).where(m.Project.id.in_({o.project_id for o in orders})))} if orders else {}
    items = []
    for o in orders:
        pr = projects.get(o.project_id)
        if q and q.lower() not in f"{o.supplier_name} {pr.title if pr else ''} {o.id[:6]}".lower():
            continue
        d = order_dict(db, o)
        d.update(number=o.id[:6].upper(), project_id=o.project_id, project_title=pr.title if pr else "", city=pr.city if pr else "", amount_amd=_amount(d),
                 stages=_stages(o), positions=len(d["items"]))
        items.append(d)
    by_supplier: dict[str, dict] = defaultdict(lambda: {"name": "", "count": 0, "amount_amd": 0})
    for d in items:
        g = by_supplier[d["supplier_id"] or d["supplier_name"]]
        g["name"], g["count"], g["amount_amd"] = d["supplier_name"], g["count"] + 1, g["amount_amd"] + d["amount_amd"]
    now = datetime.now(timezone.utc)

    def monthly(pred) -> list[int]:
        out = [0] * 6
        for d in items:
            if not pred(d):
                continue
            c = datetime.fromisoformat(d["created_at"])
            c = c if c.tzinfo else c.replace(tzinfo=timezone.utc)
            k = (now.year - c.year) * 12 + now.month - c.month
            if 0 <= k < 6:
                out[5 - k] += 1
        return out
    kpi = {"active": sum(1 for d in items if d["status"] in ACTIVE), "in_production": sum(1 for d in items if d["status"] == "in_production"),
           "delivering": sum(1 for d in items if d["status"] == "delivering"), "installing": sum(1 for d in items if d["status"] == "installing"),
           "closed": sum(1 for d in items if d["status"] == "closed"), "amount_amd": sum(d["amount_amd"] for d in items if d["status"] not in ("cancelled", "refunded")),
           "series": {"active": monthly(lambda d: d["status"] in ACTIVE), "all": monthly(lambda d: True)}}
    return {"items": items, "kpi": kpi, "suppliers": [{"key": k, **v} for k, v in sorted(by_supplier.items(), key=lambda x: -x[1]["amount_amd"])]}


# ------------------------------------------------------------------ helpers: the caller's bureau


STAGES_CRM = ("lead", "contacted", "brief", "proposal", "contract", "in_work", "done", "lost")
SOURCES = ("referral", "instagram", "facebook", "site", "walk_in", "partner", "other")


def _bureau(p: Principal, db: Session, org_id: str | None = None) -> m.Organization:
    """CRM and tasks belong to a bureau. Platform admins may open any bureau by org_id."""
    if org_id and p.is_platform_admin:
        org = db.get(m.Organization, org_id)
        if org and org.kind == "bureau":
            return org
    org = next((o for o in (db.get(m.Organization, i) for i in p.org_ids) if o and o.kind == "bureau" and p.can("project:read", o.id)), None)
    if not org:
        raise ApiError(403, "auth.forbidden")
    return org


def _user_names(db: Session, ids) -> dict[str, str]:
    ids = {i for i in ids if i}
    return {u.id: u.name for u in db.scalars(select(m.User).where(m.User.id.in_(ids)))} if ids else {}


def _iso(d):
    return d.isoformat() if d else None


# ------------------------------------------------------------------ CRM
def client_dict(c: m.Client, names: dict[str, str], projects: int = 0, open_tasks: int = 0) -> dict:
    return {"id": c.id, "name": c.name, "phone": c.phone, "email": c.email, "source": c.source, "stage": c.stage, "budget_amd": c.budget_amd, "area_m2": c.area_m2,
            "address": c.address, "notes": c.notes, "owner_id": c.owner_id, "owner_name": names.get(c.owner_id or "", ""), "next_action": c.next_action,
            "next_action_at": _iso(c.next_action_at), "lost_reason": c.lost_reason, "created_at": _iso(c.created_at), "updated_at": _iso(c.updated_at),
            "projects": projects, "open_tasks": open_tasks}


@router.get("/crm/clients")
def list_clients(stage: str = "", q: str = "", owner: str = "", org_id: str | None = None, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    org = _bureau(p, db, org_id)
    stmt = select(m.Client).where(m.Client.org_id == org.id)
    if stage:
        stmt = stmt.where(m.Client.stage == stage)
    if owner:
        stmt = stmt.where(m.Client.owner_id == (p.user.id if owner == "me" else owner))
    rows = db.scalars(stmt.order_by(m.Client.updated_at.desc()).limit(1000)).all()
    if q:
        rows = [c for c in rows if q.lower() in f"{c.name} {c.phone} {c.email} {c.address}".lower()]
    names = _user_names(db, (c.owner_id for c in rows))
    ids = [c.id for c in rows]
    pcount: dict[str, int] = defaultdict(int)
    tcount: dict[str, int] = defaultdict(int)
    if ids:
        for cid in db.scalars(select(m.Project.client_id).where(m.Project.client_id.in_(ids))):
            pcount[cid] += 1
        for cid in db.scalars(select(m.Task.client_id).where(m.Task.client_id.in_(ids), m.Task.status != "done")):
            tcount[cid] += 1
    all_rows = db.scalars(select(m.Client).where(m.Client.org_id == org.id)).all()
    counts = {s: sum(1 for c in all_rows if c.stage == s) for s in STAGES_CRM}
    pipeline = sum(c.budget_amd or 0 for c in all_rows if c.stage not in ("done", "lost"))
    won, lost = counts["done"] + counts["in_work"], counts["lost"]
    return {"items": [client_dict(c, names, pcount[c.id], tcount[c.id]) for c in rows], "counts": counts, "pipeline_amd": pipeline,
            "conversion": round(won / (won + lost), 3) if won + lost else None, "stages": list(STAGES_CRM), "sources": list(SOURCES),
            "members": [{"id": ms.user_id, "name": ms.user.name} for ms in db.scalars(select(m.Membership).where(m.Membership.org_id == org.id))]}


class ClientIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(default="", max_length=40)
    email: str = Field(default="", max_length=320)
    source: str = Field(default="other", pattern="^(" + "|".join(SOURCES) + ")$")
    stage: str = Field(default="lead", pattern="^(" + "|".join(STAGES_CRM) + ")$")
    budget_amd: int | None = Field(default=None, ge=0)
    area_m2: float | None = Field(default=None, ge=0, le=100000)
    address: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=5000)
    owner_id: str | None = None
    next_action: str = Field(default="", max_length=300)
    next_action_at: datetime | None = None
    lost_reason: str = Field(default="", max_length=300)


class ClientPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=320)
    source: str | None = Field(default=None, pattern="^(" + "|".join(SOURCES) + ")$")
    stage: str | None = Field(default=None, pattern="^(" + "|".join(STAGES_CRM) + ")$")
    budget_amd: int | None = Field(default=None, ge=0)
    area_m2: float | None = Field(default=None, ge=0, le=100000)
    address: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=5000)
    owner_id: str | None = None
    next_action: str | None = Field(default=None, max_length=300)
    next_action_at: datetime | None = None
    lost_reason: str | None = Field(default=None, max_length=300)


def _client(p: Principal, db: Session, cid: str) -> m.Client:
    c = db.get(m.Client, cid)
    if not c or c.org_id not in p.org_ids and not p.is_platform_admin:
        raise ApiError(404, "not_found")
    if not p.is_platform_admin and not p.can("project:read", c.org_id):
        raise ApiError(404, "not_found")
    return c


def _check_member(db: Session, org_id: str, user_id: str | None) -> None:
    if user_id and not db.scalar(select(m.Membership.id).where(m.Membership.org_id == org_id, m.Membership.user_id == user_id).limit(1)):
        raise ApiError(422, "validation", fields=["owner_id"])


@router.post("/crm/clients")
def create_client(body: ClientIn, org_id: str | None = None, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    org = _bureau(p, db, org_id)
    _check_member(db, org.id, body.owner_id)
    c = m.Client(org_id=org.id, **{**body.model_dump(), "owner_id": body.owner_id or p.user.id})
    db.add(c)
    db.flush()
    db.add(m.ClientActivity(client_id=c.id, user_id=p.user.id, kind="stage", body=c.stage))
    audit(db, p, "crm.client_create", "client", c.id, org_id=org.id)
    db.commit()
    return client_dict(c, _user_names(db, [c.owner_id]))


@router.get("/crm/clients/{cid}")
def get_client(cid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    c = _client(p, db, cid)
    acts = db.scalars(select(m.ClientActivity).where(m.ClientActivity.client_id == cid).order_by(m.ClientActivity.created_at.desc()).limit(200)).all()
    projects = db.scalars(select(m.Project).where(m.Project.client_id == cid)).all()
    tasks = db.scalars(select(m.Task).where(m.Task.client_id == cid).order_by(m.Task.created_at.desc())).all()
    names = _user_names(db, [c.owner_id, *(a.user_id for a in acts), *(t.assignee_id for t in tasks)])
    return {**client_dict(c, names, len(projects)), "activities": [{"id": a.id, "kind": a.kind, "body": a.body, "user": names.get(a.user_id or "", ""), "at": _iso(a.created_at)} for a in acts],
            "project_list": [{"id": x.id, "title": x.title, "status": x.status, "updated_at": _iso(x.updated_at)} for x in projects],
            "tasks": [task_dict(x, names, {}) for x in tasks]}


@router.patch("/crm/clients/{cid}")
def patch_client(cid: str, body: ClientPatch, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    c = _client(p, db, cid)
    data = body.model_dump(exclude_unset=True)
    if "owner_id" in data:
        _check_member(db, c.org_id, data["owner_id"])
    if data.get("stage") and data["stage"] != c.stage:
        db.add(m.ClientActivity(client_id=c.id, user_id=p.user.id, kind="stage", body=f"{c.stage}→{data['stage']}"))
    for k, v in data.items():
        setattr(c, k, v)
    db.commit()
    return client_dict(c, _user_names(db, [c.owner_id]))


@router.delete("/crm/clients/{cid}")
def delete_client(cid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    c = _client(p, db, cid)
    for pr in db.scalars(select(m.Project).where(m.Project.client_id == cid)):
        pr.client_id = None  # projects stay; only the CRM card goes
    for t in db.scalars(select(m.Task).where(m.Task.client_id == cid)):
        t.client_id = None
    audit(db, p, "crm.client_delete", "client", cid, org_id=c.org_id, data={"name": c.name})
    db.delete(c)
    db.commit()
    return {"ok": True}


class ActivityIn(BaseModel):
    kind: str = Field(default="note", pattern="^(note|call|meeting)$")
    body: str = Field(min_length=1, max_length=5000)


@router.post("/crm/clients/{cid}/activities")
def add_activity(cid: str, body: ActivityIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    c = _client(p, db, cid)
    db.add(m.ClientActivity(client_id=c.id, user_id=p.user.id, kind=body.kind, body=body.body))
    c.updated_at = datetime.now(timezone.utc)
    db.commit()
    return get_client(cid, p, db)


class LinkIn(BaseModel):
    project_id: str | None = None  # link an existing project, or create one from the client card
    title: str = Field(default="", max_length=200)


@router.post("/crm/clients/{cid}/projects")
def link_project(cid: str, body: LinkIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    c = _client(p, db, cid)
    if body.project_id:
        pr = project_access(body.project_id, "project:write", p, db)
        if pr.org_id != c.org_id:
            raise ApiError(404, "project.not_found")
    else:
        if not p.can("project:write", c.org_id):
            raise ApiError(403, "auth.forbidden")
        from ..commerce.tariffs import check_project_quota

        check_project_quota(db, c.org_id)
        pr = m.Project(org_id=c.org_id, owner_id=p.user.id, title=body.title.strip() or c.name, address=c.address, area_m2=c.area_m2,
                       designer_name=p.user.name, preferences={"budget_amd": c.budget_amd} if c.budget_amd else {})
        db.add(pr)
        db.flush()
    pr.client_id, pr.client_name = c.id, pr.client_name or c.name
    db.add(m.ClientActivity(client_id=c.id, user_id=p.user.id, kind="project", body=pr.title))
    if c.stage in ("lead", "contacted", "brief", "proposal", "contract"):
        c.stage = "in_work"
    db.commit()
    return {"project_id": pr.id}


# ------------------------------------------------------------------ tasks and team workload
TASK_STATUS = ("todo", "in_progress", "review", "done")


def task_dict(t: m.Task, names: dict[str, str], titles: dict[str, str]) -> dict:
    now = datetime.now(timezone.utc)
    due = t.due_at.replace(tzinfo=timezone.utc) if t.due_at and t.due_at.tzinfo is None else t.due_at
    return {"id": t.id, "title": t.title, "description": t.description, "status": t.status, "priority": t.priority, "due_at": _iso(t.due_at),
            "overdue": bool(due and due < now and t.status != "done"), "estimate_h": t.estimate_h, "assignee_id": t.assignee_id, "assignee_name": names.get(t.assignee_id or "", ""),
            "project_id": t.project_id, "project_title": titles.get(t.project_id or "", ""), "client_id": t.client_id, "created_at": _iso(t.created_at), "done_at": _iso(t.done_at)}


@router.get("/tasks")
def list_tasks(assignee: str = "", status: str = "", project_id: str = "", org_id: str | None = None, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    org = _bureau(p, db, org_id)
    stmt = select(m.Task).where(m.Task.org_id == org.id)
    if assignee:
        stmt = stmt.where(m.Task.assignee_id == (p.user.id if assignee == "me" else assignee))
    if status:
        stmt = stmt.where(m.Task.status == status)
    if project_id:
        stmt = stmt.where(m.Task.project_id == project_id)
    rows = db.scalars(stmt.order_by(m.Task.due_at.is_(None), m.Task.due_at, m.Task.created_at.desc()).limit(1000)).all()
    names = _user_names(db, (t.assignee_id for t in rows))
    titles = {x.id: x.title for x in db.scalars(select(m.Project).where(m.Project.id.in_({t.project_id for t in rows if t.project_id})))} if rows else {}
    return {"items": [task_dict(t, names, titles) for t in rows],
            "members": [{"id": ms.user_id, "name": ms.user.name} for ms in db.scalars(select(m.Membership).where(m.Membership.org_id == org.id))],
            "projects": [{"id": x.id, "title": x.title} for x in db.scalars(select(m.Project).where(m.Project.org_id == org.id).order_by(m.Project.updated_at.desc()).limit(200))]}


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=5000)
    assignee_id: str | None = None
    status: str = Field(default="todo", pattern="^(todo|in_progress|review|done)$")
    priority: str = Field(default="normal", pattern="^(low|normal|high)$")
    due_at: datetime | None = None
    estimate_h: float | None = Field(default=None, ge=0, le=1000)
    project_id: str | None = None
    client_id: str | None = None


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    assignee_id: str | None = None
    status: str | None = Field(default=None, pattern="^(todo|in_progress|review|done)$")
    priority: str | None = Field(default=None, pattern="^(low|normal|high)$")
    due_at: datetime | None = None
    estimate_h: float | None = Field(default=None, ge=0, le=1000)
    project_id: str | None = None


def _task_refs(p: Principal, db: Session, org: m.Organization, data: dict) -> None:
    if data.get("assignee_id"):
        _check_member(db, org.id, data["assignee_id"])
    if data.get("project_id"):
        pr = db.get(m.Project, data["project_id"])
        if not pr or pr.org_id != org.id:
            raise ApiError(422, "validation", fields=["project_id"])
    if data.get("client_id"):
        cl = db.get(m.Client, data["client_id"])
        if not cl or cl.org_id != org.id:
            raise ApiError(422, "validation", fields=["client_id"])


def _notify_assignee(db: Session, p: Principal, t: m.Task) -> None:
    if t.assignee_id and t.assignee_id != p.user.id:
        from ..notify import notify

        notify(db, [db.get(m.User, t.assignee_id)], "task_assigned", params={"task": t.title[:80], "by": p.user.name}, link="/app/tasks", project_id=t.project_id)


@router.post("/tasks")
def create_task(body: TaskIn, org_id: str | None = None, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    org = _bureau(p, db, org_id)
    data = body.model_dump()
    _task_refs(p, db, org, data)
    t = m.Task(org_id=org.id, created_by=p.user.id, **data)
    if t.status == "done":
        t.done_at = datetime.now(timezone.utc)
    db.add(t)
    db.flush()
    _notify_assignee(db, p, t)
    db.commit()
    return task_dict(t, _user_names(db, [t.assignee_id]), {})


def _task(p: Principal, db: Session, tid: str) -> m.Task:
    t = db.get(m.Task, tid)
    if not t or (t.org_id not in p.org_ids and not p.is_platform_admin):
        raise ApiError(404, "not_found")
    return t


@router.patch("/tasks/{tid}")
def patch_task(tid: str, body: TaskPatch, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    t = _task(p, db, tid)
    data = body.model_dump(exclude_unset=True)
    _task_refs(p, db, db.get(m.Organization, t.org_id), data)
    reassigned = "assignee_id" in data and data["assignee_id"] != t.assignee_id
    if data.get("status") == "done" and t.status != "done":
        t.done_at = datetime.now(timezone.utc)
    elif data.get("status") and data["status"] != "done":
        t.done_at = None
    for k, v in data.items():
        setattr(t, k, v)
    if reassigned:
        _notify_assignee(db, p, t)
    db.commit()
    return task_dict(t, _user_names(db, [t.assignee_id]), {})


@router.delete("/tasks/{tid}")
def delete_task(tid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    t = _task(p, db, tid)
    db.delete(t)
    db.commit()
    return {"ok": True}


@router.get("/team/workload")
def workload(org_id: str | None = None, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Per member: open tasks by status, overdue, due this week, planned hours, done in 30 days, active projects."""
    org = _bureau(p, db, org_id)
    now = datetime.now(timezone.utc)
    week = now + timedelta(days=7)
    tasks = db.scalars(select(m.Task).where(m.Task.org_id == org.id)).all()
    projects = db.scalars(select(m.Project).where(m.Project.org_id == org.id, m.Project.status.notin_(("approved", "ordered")))).all()

    def aware(d):
        return d.replace(tzinfo=timezone.utc) if d and d.tzinfo is None else d
    out = []
    for ms in db.scalars(select(m.Membership).where(m.Membership.org_id == org.id)):
        mine = [t for t in tasks if t.assignee_id == ms.user_id]
        open_ = [t for t in mine if t.status != "done"]
        out.append({"user_id": ms.user_id, "name": ms.user.name, "role": ms.role,
                    "todo": sum(1 for t in open_ if t.status == "todo"), "in_progress": sum(1 for t in open_ if t.status == "in_progress"),
                    "review": sum(1 for t in open_ if t.status == "review"), "overdue": sum(1 for t in open_ if t.due_at and aware(t.due_at) < now),
                    "due_week": sum(1 for t in open_ if t.due_at and now <= aware(t.due_at) <= week), "planned_h": round(sum(t.estimate_h or 0 for t in open_), 1),
                    "done_30d": sum(1 for t in mine if t.done_at and aware(t.done_at) >= now - timedelta(days=30)),
                    "projects": sum(1 for x in projects if x.owner_id == ms.user_id)})
    unassigned = sum(1 for t in tasks if not t.assignee_id and t.status != "done")
    return {"members": sorted({x["user_id"]: x for x in out}.values(), key=lambda x: -(x["todo"] + x["in_progress"] + x["review"])), "unassigned": unassigned}


# ------------------------------------------------------------------ project conversation (team + client)
class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    visibility: str = Field(default="team", pattern="^(team|client)$")


def message_dict(c: m.Comment, me: str) -> dict:
    return {"id": c.id, "body": c.body, "author": c.author_name, "from_client": c.author_id is None, "mine": c.author_id == me, "visibility": c.visibility,
            "variant_id": c.variant_id, "anchor": c.anchor, "at": _iso(c.created_at)}


@router.get("/projects/{pid}/messages")
def project_messages(pid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:read", p, db)
    rows = db.scalars(select(m.Comment).where(m.Comment.project_id == pid).order_by(m.Comment.created_at).limit(1000)).all()
    return [message_dict(c, p.user.id) for c in rows]


@router.post("/projects/{pid}/messages")
def post_message(pid: str, body: MessageIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    proj = project_access(pid, "project:write", p, db)
    c = m.Comment(project_id=pid, author_name=p.user.name, author_id=p.user.id, body=body.body.strip(), visibility=body.visibility)
    db.add(c)
    db.merge(m.ProjectRead(user_id=p.user.id, project_id=pid, last_read_at=datetime.now(timezone.utc)))
    from ..notify import notify

    team = [ms.user for ms in db.scalars(select(m.Membership).where(m.Membership.org_id == proj.org_id)) if ms.user_id != p.user.id and ms.role in ("bureau_admin", "designer")]
    notify(db, team, "message", params={"author": p.user.name, "project": proj.title}, link=f"/app/messages?project={pid}", project_id=pid)
    db.commit()
    return message_dict(c, p.user.id)


@router.post("/projects/{pid}/messages/read")
def mark_read(pid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:read", p, db)
    db.merge(m.ProjectRead(user_id=p.user.id, project_id=pid, last_read_at=datetime.now(timezone.utc)))
    db.commit()
    return {"ok": True}


def _after(at: datetime, seen: datetime | None) -> bool:
    at = at.replace(tzinfo=timezone.utc) if at.tzinfo is None else at
    return seen is None or at > seen


@router.get("/messages/inbox")
def inbox(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Projects of the caller's organisations with their latest message and the unread count."""
    stmt = select(m.Project)
    if not p.is_platform_admin:
        stmt = stmt.where(m.Project.org_id.in_(p.org_ids))
    projects = db.scalars(stmt.order_by(m.Project.updated_at.desc()).limit(300)).all()
    reads = {r.project_id: r.last_read_at for r in db.scalars(select(m.ProjectRead).where(m.ProjectRead.user_id == p.user.id))}
    out = []
    for pr in projects:
        msgs = db.scalars(select(m.Comment).where(m.Comment.project_id == pr.id).order_by(m.Comment.created_at.desc()).limit(50)).all()
        if not msgs:
            continue
        seen = reads.get(pr.id)
        seen = seen.replace(tzinfo=timezone.utc) if seen and seen.tzinfo is None else seen

        last = msgs[0]
        out.append({"project_id": pr.id, "title": pr.title, "client_name": pr.client_name, "last": message_dict(last, p.user.id),
                    "unread": sum(1 for c in msgs if c.author_id != p.user.id and _after(c.created_at, seen))})
    out.sort(key=lambda x: x["last"]["at"] or "", reverse=True)
    return {"items": out, "unread": sum(x["unread"] for x in out)}


# ------------------------------------------------------------------ analytics (mockup 19) — computed from the organisation's own records
def _months(n: int) -> list[str]:
    now = datetime.now(timezone.utc)
    out = []
    y, mo = now.year, now.month
    for _ in range(n):
        out.append(f"{y:04d}-{mo:02d}")
        mo -= 1
        if not mo:
            y, mo = y - 1, 12
    return out[::-1]


def _bucket(d: datetime | None) -> str | None:
    return f"{d.year:04d}-{d.month:02d}" if d else None


@router.get("/analytics")
def analytics(months: int = Query(6, ge=3, le=24), org_id: str | None = None, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Bureau: its projects, estimates, orders, clients and tasks. Platform admin without org_id: the whole platform plus revenue and catalogue."""
    from statistics import median

    scope_all = p.is_platform_admin and not org_id
    org = None if scope_all else _bureau(p, db, org_id)
    labels = _months(months)
    pq = select(m.Project) if scope_all else select(m.Project).where(m.Project.org_id == org.id)
    projects = db.scalars(pq).all()
    pids = [x.id for x in projects]
    per_month = {k: 0 for k in labels}
    for x in projects:
        k = _bucket(x.created_at)
        if k in per_month:
            per_month[k] += 1
    status = defaultdict(int)
    for x in projects:
        status[x.status] += 1
    # chosen / approved variants: budget, cost per m², spend by group, suppliers
    variants = db.scalars(select(m.DesignVariant).where(m.DesignVariant.project_id.in_(pids), m.DesignVariant.status.in_(("selected", "approved")))).all() if pids else []
    by_proj = {v.project_id: v for v in variants}
    totals = [(v.metrics or {}).get("total") or 0 for v in by_proj.values()]
    area = {x.id: x.area_m2 for x in projects}
    per_m2 = [t / area[pid] for pid, t in ((v.project_id, (v.metrics or {}).get("total") or 0) for v in by_proj.values()) if area.get(pid) and t]
    groups, suppliers = defaultdict(int), defaultdict(int)
    real = demo = concept = 0
    for v in by_proj.values():
        ver = db.get(m.DesignVersion, v.current_version_id) if v.current_version_id else None
        for ln in ((ver.estimate or {}).get("lines") or []) if ver else []:
            tot = ln.get("total") or 0
            groups[ln.get("group") or "other"] += tot
            if ln.get("supplier") and ln.get("ref"):
                suppliers[ln["supplier"]] += tot
                if ln.get("is_demo"):
                    demo += 1
                elif str(ln.get("ref", "")).startswith("concept:"):
                    concept += 1
                else:
                    real += 1
    # time from project creation to the first approval
    days_to_approve = []
    if pids:
        firsts = {}
        for a in db.scalars(select(m.Approval).where(m.Approval.project_id.in_(pids), m.Approval.decision == "approved").order_by(m.Approval.created_at)):
            firsts.setdefault(a.project_id, a.created_at)
        created = {x.id: x.created_at for x in projects}
        for pid, at in firsts.items():
            if created.get(pid) and at:
                days_to_approve.append((at - created[pid]).total_seconds() / 86400)
    # orders
    oq = select(m.Order).where(m.Order.status != "cart") if scope_all else select(m.Order).where(m.Order.status != "cart", m.Order.project_id.in_(pids or [""]))
    orders = db.scalars(oq).all()
    o_month = {k: 0 for k in labels}
    for o in orders:
        k = _bucket(o.created_at)
        if k in o_month:
            o_month[k] += sum((o.totals or {}).get(x) or 0 for x in ("goods", "delivery", "installation"))
    # CRM and tasks (bureau scope)
    crm = tasks = None
    if org:
        clients = db.scalars(select(m.Client).where(m.Client.org_id == org.id)).all()
        src = defaultdict(lambda: {"clients": 0, "won": 0, "lost": 0})
        for c in clients:
            s = src[c.source]
            s["clients"] += 1
            s["won"] += c.stage in ("in_work", "done")
            s["lost"] += c.stage == "lost"
        crm = {"by_stage": {s: sum(1 for c in clients if c.stage == s) for s in STAGES_CRM}, "by_source": [{"source": k, **v} for k, v in sorted(src.items(), key=lambda x: -x[1]["clients"])]}
        ts = db.scalars(select(m.Task).where(m.Task.org_id == org.id)).all()
        done = {k: 0 for k in labels}
        for t in ts:
            k = _bucket(t.done_at)
            if k in done:
                done[k] += 1
        now = datetime.now(timezone.utc)
        tasks = {"done_by_month": [done[k] for k in labels], "open": sum(1 for t in ts if t.status != "done"),
                 "overdue": sum(1 for t in ts if t.status != "done" and t.due_at and (t.due_at.replace(tzinfo=timezone.utc) if t.due_at.tzinfo is None else t.due_at) < now)}
    # AI spend per project (variable cost)
    ai_rows = db.execute(select(m.AIUsage.project_id, func.coalesce(func.sum(m.AIUsage.cost_usd), 0.0)).where(m.AIUsage.project_id.in_(pids or [""]), m.AIUsage.provider != "stub")
                         .group_by(m.AIUsage.project_id)).all()
    ai = [float(c) for _, c in ai_rows if c]
    out = {"scope": "platform" if scope_all else "bureau", "months": labels,
           "projects": {"total": len(projects), "by_month": [per_month[k] for k in labels], "by_status": dict(status),
                        "accuracy": {lvl: sum(1 for x in projects if x.accuracy_level == lvl) for lvl in ("concept", "verified", "production")},
                        "median_days_to_approval": round(median(days_to_approve), 1) if days_to_approve else None},
           "estimates": {"projects": len(totals), "average_amd": round(sum(totals) / len(totals)) if totals else None, "median_amd": round(median(totals)) if totals else None,
                         "per_m2_amd": round(median(per_m2)) if per_m2 else None, "by_group": dict(sorted(groups.items(), key=lambda x: -x[1])),
                         "top_suppliers": [{"name": k, "amount_amd": v} for k, v in sorted(suppliers.items(), key=lambda x: -x[1])[:8]],
                         "sourcing": {"real": real, "demo": demo, "concept": concept}},
           "orders": {"count": len(orders), "amount_by_month": [o_month[k] for k in labels], "by_status": dict((s, sum(1 for o in orders if o.status == s)) for s in {o.status for o in orders})},
           "crm": crm, "tasks": tasks,
           "ai": {"projects_with_ai": len(ai), "avg_usd": round(sum(ai) / len(ai), 3) if ai else None, "median_usd": round(median(ai), 3) if ai else None}}
    if scope_all:
        from ..commerce import tariffs

        fresh_cut = datetime.now(timezone.utc) - timedelta(days=7)
        variants_all = db.scalars(select(m.ProductVariant).join(m.Product).where(m.Product.status == "active", m.Product.is_demo.is_(False))).all()

        def fresh(v):
            c = v.price_checked_at
            return c is not None and (c.replace(tzinfo=timezone.utc) if c.tzinfo is None else c) >= fresh_cut
        out["platform"] = {"orgs": {k: db.scalar(select(func.count(m.Organization.id)).where(m.Organization.kind == k)) or 0 for k in ("bureau", "supplier")},
                           "users": db.scalar(select(func.count(m.User.id)).where(m.User.status == "active")) or 0,
                           "revenue": tariffs.revenue_report(db)["totals"],
                           "catalogue": {"skus": len(variants_all), "priced": sum(1 for v in variants_all if v.price is not None), "fresh_7d": sum(1 for v in variants_all if fresh(v)),
                                         "external_records": db.scalar(select(func.count(m.ExternalProductRecord.id))) or 0}}
    return out
