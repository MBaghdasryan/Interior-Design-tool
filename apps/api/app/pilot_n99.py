"""Create (idempotently) and print the N99 pilot workspace status.

    docker compose exec api python -m app.pilot_n99
"""
from __future__ import annotations

from .db import SessionLocal
from .pilot import ensure_workspace, status


def main() -> None:
    with SessionLocal() as db:
        proj, created = ensure_workspace(db)
        st = status(db, proj)
        print(f"N99 project {proj.id} ({'created' if created else 'exists'}) — validated={st['validated']} progress={st['progress']:.0%}")
        print("manifest:")
        for i in st["manifest"]:
            print(f"  [{'x' if i['ok'] else ' '}] {i['code']}{' (auto)' if i['auto'] else ''}")
        print("flow:")
        for s in st["flow"]:
            print(f"  [{'x' if s['ok'] else ' '}] {s['code']}")


if __name__ == "__main__":
    main()
