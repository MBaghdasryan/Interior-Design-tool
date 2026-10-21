"""`python -m app.seed_sources` — apply the idempotent ExternalSource seed and print
the registry (verification output for EXTERNAL_CATALOG_REPORT.md)."""
from sqlalchemy import func, select

from . import models as m
from .catalog.connectors.others import build_connector
from .catalog.discovery import source_dict
from .config import get_settings
from .db import SessionLocal
from .seed import seed_external_sources


def main() -> None:
    s = get_settings()
    with SessionLocal() as db:
        report = seed_external_sources(db)
        db.commit()
        total = db.scalar(select(func.count(m.ExternalSource.id)))
        print(f"EXTERNAL_FETCH_LIVE={s.external_fetch_live}  rows={total}")
        print(f"{'key':12} {'canonical_domain':20} {'connector':15} {'enabled':8} {'live':5} {'policy':9} {'health':12} seed")
        acts = {r['key']: r['action'] for r in report}
        for src in db.scalars(select(m.ExternalSource).order_by(m.ExternalSource.key)):
            health = build_connector(source_dict(src), live=s.external_fetch_live, cache_lookup=None).get_connector_health().status if src.enabled else "disabled"
            src.health_status = health
            print(f"{src.key:12} {src.canonical_domain or '-':20} {src.connector_type:15} {str(src.enabled):8} {str(src.live_enabled and s.external_fetch_live):5} {src.policy_status:9} {health:12} {acts.get(src.key, '-')}")
        db.commit()


if __name__ == "__main__":
    main()
