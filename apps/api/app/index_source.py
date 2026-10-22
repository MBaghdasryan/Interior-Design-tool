"""Run one index batch for a background-indexed source.

    docker compose exec api python -m app.index_source vlv --batch 60
"""
from __future__ import annotations

import argparse
import json

from sqlalchemy import select

from . import models as m
from .catalog.indexer import crawl_batch
from .db import SessionLocal


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("key")
    ap.add_argument("--batch", type=int, default=60)
    a = ap.parse_args()
    with SessionLocal() as db:
        src = db.scalar(select(m.ExternalSource).where(m.ExternalSource.key == a.key))
        if not src:
            raise SystemExit(f"unknown source {a.key}")
        r = crawl_batch(db, src, batch=a.batch)
        print(json.dumps({k: v for k, v in r.items() if k != "errors"}, ensure_ascii=False))
        for e in r.get("errors", [])[:5]:
            print("  !", e)


if __name__ == "__main__":
    main()
