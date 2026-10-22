"""Outgoing e-mail behind one interface. `console` writes RFC-822 files to MAIL_DIR
(development, E2E tests read links from there); `smtp` sends through the configured
relay. Only the recipient and subject are logged — never the body (it carries tokens)."""
from __future__ import annotations

import logging
import smtplib
import time
from email.message import EmailMessage
from pathlib import Path

from .config import get_settings

log = logging.getLogger("forma.mail")

# Localised templates: (subject, body). Bodies are plain text with {placeholders}.
TEMPLATES: dict[str, dict[str, tuple[str, str]]] = {
    "verify_email": {
        "hy": ("Հաստատեք ձեր էլ. հասցեն — {brand}", "Բարև, {name}։\n\nՀաշիվը ակտիվացնելու համար բացեք հղումը (գործում է {hours} ժամ)՝\n{link}\n\nԵթե դուք չեք գրանցվել, պարզապես անտեսեք այս նամակը։\n— {brand}"),
        "ru": ("Подтвердите e-mail — {brand}", "Здравствуйте, {name}!\n\nЧтобы подтвердить адрес, откройте ссылку (действует {hours} ч):\n{link}\n\nЕсли вы не регистрировались, просто проигнорируйте письмо.\n— {brand}"),
        "en": ("Confirm your e-mail — {brand}", "Hello {name},\n\nOpen this link to confirm your address (valid for {hours} h):\n{link}\n\nIf you did not sign up, just ignore this message.\n— {brand}"),
    },
    "password_reset": {
        "hy": ("Գաղտնաբառի վերականգնում — {brand}", "Բարև, {name}։\n\nՆոր գաղտնաբառ սահմանելու համար բացեք հղումը (գործում է {minutes} րոպե)՝\n{link}\n\nԵթե հարցումը դուք չեք արել, անտեսեք նամակը — գաղտնաբառը չի փոխվի։\n— {brand}"),
        "ru": ("Восстановление пароля — {brand}", "Здравствуйте, {name}!\n\nЧтобы задать новый пароль, откройте ссылку (действует {minutes} мин):\n{link}\n\nЕсли вы не запрашивали сброс, проигнорируйте письмо — пароль не изменится.\n— {brand}"),
        "en": ("Reset your password — {brand}", "Hello {name},\n\nOpen this link to set a new password (valid for {minutes} min):\n{link}\n\nIf you did not request this, ignore the message — your password stays the same.\n— {brand}"),
    },
    "password_changed": {
        "hy": ("Գաղտնաբառը փոխվել է — {brand}", "Բարև, {name}։\n\nՁեր գաղտնաբառը փոխվել է, բոլոր սեսիաները դադարեցվել են։ Եթե դա դուք չեք արել, անմիջապես կապվեք մեզ հետ։\n— {brand}"),
        "ru": ("Пароль изменён — {brand}", "Здравствуйте, {name}!\n\nВаш пароль изменён, все сессии завершены. Если это были не вы — срочно свяжитесь с нами.\n— {brand}"),
        "en": ("Password changed — {brand}", "Hello {name},\n\nYour password was changed and all sessions were signed out. If this was not you, contact us immediately.\n— {brand}"),
    },
}


def render(template: str, lang: str, **params) -> tuple[str, str]:
    t = TEMPLATES[template].get(lang) or TEMPLATES[template]["en"]
    params.setdefault("brand", get_settings().brand_name)
    return t[0].format(**params), t[1].format(**params)


class EmailSender:
    def send(self, to: str, subject: str, body: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class ConsoleSender(EmailSender):
    def __init__(self, directory: Path):
        self.dir = directory

    def send(self, to: str, subject: str, body: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        msg = _message(to, subject, body)
        safe = "".join(ch if ch.isalnum() else "_" for ch in to)[:60]
        (self.dir / f"{time.time_ns()}_{safe}.eml").write_bytes(bytes(msg))
        log.info("mail (console) to=%s subject=%s", to, subject)


class SmtpSender(EmailSender):
    def send(self, to: str, subject: str, body: str) -> None:
        s = get_settings()
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
            if s.smtp_starttls:
                smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password or "")
            smtp.send_message(_message(to, subject, body))
        log.info("mail (smtp) to=%s subject=%s", to, subject)


def _message(to: str, subject: str, body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = get_settings().mail_from, to, subject
    msg.set_content(body)
    return msg


def get_sender() -> EmailSender:
    s = get_settings()
    if s.mail_backend == "smtp" and s.smtp_host:
        return SmtpSender()
    return ConsoleSender(s.mail_dir)


def send_template(to: str, template: str, lang: str, **params) -> None:
    subject, body = render(template, lang, **params)
    try:
        get_sender().send(to, subject, body)
    except Exception as e:  # mail failure must not leak tokens or break the request
        log.error("mail failed to=%s template=%s: %s", to, template, type(e).__name__)
