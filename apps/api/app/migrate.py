"""Idempotent schema migration entrypoint: `python -m app.migrate`.

* empty database                      → alembic upgrade head
* database created by the first MVP iteration with `create_all` (tables exist, no
  alembic_version)                    → stamp 0001_baseline, then upgrade head
* already versioned                   → upgrade head (no-op when current)
"""
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from .db import engine


def main() -> None:
    cfg = Config("alembic.ini")
    tables = set(inspect(engine).get_table_names())
    if "alembic_version" not in tables and "projects" in tables:
        command.stamp(cfg, "0001_baseline")
    command.upgrade(cfg, "head")


if __name__ == "__main__":
    main()
