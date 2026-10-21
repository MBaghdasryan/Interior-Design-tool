"""`python -m app.reclassify_external` — re-run the current classifier/accessory filter
over stored external records (after classifier fixes). Accessories are rejected,
unrecognised items go to the manual review queue."""
from sqlalchemy import select

from . import models as m
from .catalog.normalize import classify, is_accessory
from .db import SessionLocal


def main() -> None:
    changed = rejected = review = 0
    with SessionLocal() as db:
        for r in db.scalars(select(m.ExternalProductRecord)):
            d = dict(r.data)
            name = d.get("name") or ""
            if is_accessory(name):
                if r.review_status != "rejected":
                    r.review_status = "rejected"
                    rejected += 1
                continue
            cat = classify(name, d.get("category"), d.get("description_summary"))
            if cat != r.normalized_category:
                r.normalized_category = cat
                d["normalized_category"] = cat
                d["validation_warnings"] = [w for w in d.get("validation_warnings", []) if "страниц" not in w]
                r.data = d
                changed += 1
                if cat is None:
                    r.review_status = "pending_review"
                    review += 1
        db.commit()
    print(f"reclassified={changed} rejected_accessories={rejected} to_manual_review={review}")


if __name__ == "__main__":
    main()
