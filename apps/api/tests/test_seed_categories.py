import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.category import Category
from app.seed import catalog_path, seed_categories
from app.services.category_service import resolve_by_name


def test_default_categories_are_seeded_once_and_keep_existing_rows(session: Session) -> None:
    existing, _ = resolve_by_name(session, "accessories", "Cables")
    existing.description = "Our own wording"
    session.commit()

    first = seed_categories(session)
    assert seed_categories(session) == []

    session.expire_all()
    taxonomy = json.loads(catalog_path().read_text(encoding="utf-8"))["categories"]
    rows = {row.name.lower(): row for row in session.scalars(select(Category)).all()}
    assert len(rows) == len(taxonomy)
    for spec in taxonomy:
        assert {sub.name for sub in rows[spec["name"].lower()].sub_categories} == set(spec["sub_categories"])
    assert rows["accessories"].id == existing.id
    assert rows["accessories"].description == "Our own wording"
    assert len([sub for sub in rows["accessories"].sub_categories if sub.name.lower() == "cables"]) == 1
    assert any(line.startswith("accessories: added") for line in first)
