"""Keyset (cursor) pagination for list endpoints. The cursor is opaque to clients: base64url of
"<iso timestamp>|<id>" of the last row; the next page continues strictly after it in
(timestamp desc, id desc) order, so inserts between requests never duplicate or skip rows.
List bodies stay JSON arrays (backwards compatible); the next cursor travels in `X-Next-Cursor`."""
from __future__ import annotations

import base64
from datetime import datetime

from fastapi import Response
from sqlalchemy import Select, and_, or_
from sqlalchemy.orm import Session

from .errors import ApiError

NEXT_HEADER = "X-Next-Cursor"


def encode(ts: datetime, row_id: str) -> str:
    return base64.urlsafe_b64encode(f"{ts.isoformat()}|{row_id}".encode()).decode().rstrip("=")


def decode(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        ts, row_id = raw.rsplit("|", 1)
        return datetime.fromisoformat(ts), row_id
    except (ValueError, UnicodeDecodeError):
        raise ApiError(422, "validation", fields=["cursor"]) from None


def page(db: Session, stmt: Select, ts_col, id_col, *, cursor: str | None, limit: int, response: Response | None = None) -> tuple[list, str | None]:
    if cursor:
        ts, row_id = decode(cursor)
        # stored timestamps may be naive (SQLite) — compare like with like
        if ts.tzinfo is not None and db.bind is not None and db.bind.dialect.name == "sqlite":
            ts = ts.replace(tzinfo=None)
        stmt = stmt.where(or_(ts_col < ts, and_(ts_col == ts, id_col < row_id)))
    rows = list(db.scalars(stmt.order_by(ts_col.desc(), id_col.desc()).limit(limit + 1)))
    nxt = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        nxt = encode(getattr(last, ts_col.key), getattr(last, id_col.key))
    if response is not None and nxt:
        response.headers[NEXT_HEADER] = nxt
    return rows, nxt
