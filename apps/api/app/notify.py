"""Notifications: who gets what, in-app rows, and the daily e-mail digest.

Kinds and recipients:
* job_done / job_failed      — the project owner (pipeline, album, render, recognition jobs)
* client_comment / client_approved / client_changes — project owner and the org's bureau admins
* rfq_reply                  — project owner
* price_stale                — project owner (selected products whose price TTL expired)
* catalog_alert              — platform admins / ops (result drop, parser change, circuit open)
Users switch kinds off and the digest on/off in Account → Notifications."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .scheduler import periodic

log = logging.getLogger("forma.notify")
KINDS = ["job_done", "job_failed", "client_comment", "client_approved", "client_changes", "rfq_reply", "price_stale", "catalog_alert", "order_update", "rfq_received"]
DIGEST_SUBJECT = {"hy": "Ձեր ծանուցումները — {brand}", "ru": "Ваши уведомления — {brand}", "en": "Your notifications — {brand}"}
DIGEST_LINE = {
    "job_done": {"hy": "Առաջադրանքը ավարտված է՝ {job}", "ru": "Задача завершена: {job}", "en": "Job finished: {job}"},
    "job_failed": {"hy": "Առաջադրանքը ձախողվել է՝ {job}", "ru": "Задача завершилась ошибкой: {job}", "en": "Job failed: {job}"},
    "client_comment": {"hy": "Հաճախորդի մեկնաբանություն՝ {name}", "ru": "Комментарий клиента: {name}", "en": "Client comment: {name}"},
    "client_approved": {"hy": "Հաճախորդը հաստատել է տարբերակը", "ru": "Клиент утвердил вариант", "en": "The client approved a variant"},
    "client_changes": {"hy": "Հաճախորդը խնդրում է փոփոխություններ", "ru": "Клиент просит правки", "en": "The client asked for changes"},
    "rfq_reply": {"hy": "Մատակարարի պատասխան՝ {supplier}", "ru": "Ответ поставщика: {supplier}", "en": "Supplier reply: {supplier}"},
    "price_stale": {"hy": "Գները հնացել են՝ {n} ապրանք", "ru": "Цены устарели: {n} товаров", "en": "Prices are out of date: {n} products"},
    "order_update": {"hy": "Պատվեր՝ {supplier} — {status}", "ru": "Заказ: {supplier} — {status}", "en": "Order: {supplier} — {status}"},
    "rfq_received": {"hy": "Նոր հարցում ձեր ապրանքների վերաբերյալ՝ {n} դիրք", "ru": "Новый запрос по вашим товарам: {n} поз.", "en": "New request for your products: {n} items"},
    "catalog_alert": {"hy": "Կատալոգի ահազանգ՝ {source} ({reason})", "ru": "Сигнал каталога: {source} ({reason})", "en": "Catalogue alert: {source} ({reason})"},
}

ALERT_REASON = {
    "result_drop": {"hy": "արդյունքները կրճատվել են >50%", "ru": "результатов меньше на >50%", "en": "results dropped by >50%"},
    "parser": {"hy": "քարտերի կառուցվածքը փոխվել է", "ru": "изменилась разметка карточек", "en": "product page markup changed"},
    "circuit": {"hy": "կայքը հասանելի չէ (circuit breaker)", "ru": "сайт недоступен (circuit breaker)", "en": "site unavailable (circuit breaker)"},
    "blocked": {"hy": "հարցումն արգելափակված է", "ru": "запрос заблокирован", "en": "request blocked"},
    "feed_guard": {"hy": "ֆիդը պահված է՝ գների զանգվածային փոփոխություն", "ru": "фид задержан: массовое изменение цен", "en": "feed held: mass price change"},
    "feed_error": {"hy": "ֆիդը չհաջողվեց կարդալ", "ru": "фид не прочитан", "en": "feed could not be read"},
    "team_added": {"hy": "ձեզ ավելացրել են թիմին", "ru": "вас добавили в команду", "en": "you were added to the team"},
    "supplier_review": {"hy": "մատակարարը սպասում է ստուգման", "ru": "поставщик ждёт проверки", "en": "supplier awaits verification"},
    "supplier_verified": {"hy": "մատակարարը հաստատված է", "ru": "поставщик подтверждён", "en": "supplier verified"},
    "supplier_rejected": {"hy": "մատակարարը մերժված է", "ru": "поставщик отклонён", "en": "supplier rejected"},
}


def _wants(u: m.User, kind: str) -> bool:
    return (u.notification_prefs or {}).get("kinds", {}).get(kind, True) and u.status == "active"


def notify(db: Session, users: list[m.User], kind: str, *, params: dict | None = None, link: str = "", project_id: str | None = None) -> int:
    n = 0
    for u in {u.id: u for u in users if u}.values():
        if _wants(u, kind):
            db.add(m.Notification(user_id=u.id, kind=kind, params=params or {}, link=link, project_id=project_id))
            n += 1
    return n


def project_people(db: Session, project: m.Project, *, with_admins: bool = False) -> list[m.User]:
    out = [db.get(m.User, project.owner_id)]
    if with_admins:
        out += [ms.user for ms in db.scalars(select(m.Membership).where(m.Membership.org_id == project.org_id, m.Membership.role == "bureau_admin"))]
    return [u for u in out if u]


def platform_staff(db: Session) -> list[m.User]:
    return [ms.user for ms in db.scalars(select(m.Membership).where(m.Membership.role.in_(("platform_admin", "platform_ops"))))]


def send_digests(db: Session, now: datetime | None = None) -> int:
    """Once a day per user: unread, not yet e-mailed notifications → one localised e-mail."""
    from .config import get_settings
    from .mail import get_sender

    now = now or datetime.now(timezone.utc)
    s = get_settings()
    sent = 0
    rows = db.scalars(select(m.Notification).where(m.Notification.read_at.is_(None), m.Notification.emailed_at.is_(None))).all()
    by_user: dict[str, list[m.Notification]] = {}
    for r in rows:
        by_user.setdefault(r.user_id, []).append(r)
    for uid, items in by_user.items():
        u = db.get(m.User, uid)
        prefs = dict(u.notification_prefs or {}) if u else {}
        last = prefs.get("digest_sent_at")
        if not u or u.status != "active" or prefs.get("email_digest") is False:
            continue
        if last and now - datetime.fromisoformat(last) < timedelta(hours=23):
            continue
        lang = u.locale if u.locale in ("hy", "ru", "en") else "en"
        lines = []
        for it in items[:30]:
            tpl = DIGEST_LINE.get(it.kind, {}).get(lang, it.kind)
            try:
                params = dict(it.params or {})
                if "reason" in params:
                    params["reason"] = ALERT_REASON.get(params["reason"], {}).get(lang, params["reason"])
                lines.append("• " + tpl.format(**params))
            except (KeyError, IndexError):
                lines.append("• " + it.kind)
        body = "\n".join(lines) + f"\n\n{s.public_base_url.rstrip('/')}/app\n— {s.brand_name}"
        try:
            get_sender().send(u.email, DIGEST_SUBJECT[lang].format(brand=s.brand_name), body)
        except Exception as e:  # noqa: BLE001
            log.error("digest to %s failed: %s", u.email, type(e).__name__)
            continue
        for it in items:
            it.emailed_at = now
        prefs["digest_sent_at"] = now.isoformat()
        u.notification_prefs = prefs
        sent += 1
    db.commit()
    return sent


_last_digest_check = 0.0


@periodic("digest")
def hourly_digest(db: Session) -> bool:
    """Checked hourly; `send_digests` itself keeps each user to one e-mail a day."""
    global _last_digest_check
    if time.time() - _last_digest_check < 3600:
        return False
    _last_digest_check = time.time()
    return send_digests(db) > 0
