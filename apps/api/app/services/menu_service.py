"""Menu modifiers. The portal edits groups and links them to products; registers cache the menu and send each
line's choices, which the server re-prices from this catalogue (names in the payload are informational)."""

import uuid
from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, SyncRejected
from app.models.menu import ModifierGroup, ModifierOption, ProductModifierGroup
from app.models.product import Product
from app.schemas.menu import (
    ModifierGroupIn,
    ModifierGroupOut,
    ModifierOptionOut,
    ProductGroupsIn,
    RegisterMenu,
)
from app.schemas.payloads import ModifierChoice


def _links(db: Session) -> dict[uuid.UUID, list[ProductModifierGroup]]:
    by_group: dict[uuid.UUID, list[ProductModifierGroup]] = defaultdict(list)
    for link in db.scalars(select(ProductModifierGroup).order_by(ProductModifierGroup.position)):
        by_group[link.group_id].append(link)
    return by_group


def _out(group: ModifierGroup, links: Sequence[ProductModifierGroup] = ()) -> ModifierGroupOut:
    return ModifierGroupOut(
        id=group.id,
        name=group.name,
        min_select=group.min_select,
        max_select=group.max_select,
        position=group.position,
        is_active=group.is_active,
        options=[
            ModifierOptionOut(
                id=option.id,
                name=option.name,
                price_delta_cents=option.price_delta_cents,
                is_default=option.is_default,
                is_active=option.is_active,
                position=option.position,
            )
            for option in group.options
        ],
        product_ids=[link.product_id for link in links],
    )


def list_groups(db: Session) -> list[ModifierGroupOut]:
    links = _links(db)
    groups = db.scalars(select(ModifierGroup).order_by(ModifierGroup.position, ModifierGroup.name)).all()
    return [_out(group, links.get(group.id, [])) for group in groups]


def _apply(group: ModifierGroup, data: ModifierGroupIn) -> None:
    group.name = data.name.strip()
    group.min_select = data.min_select
    group.max_select = data.max_select
    group.position = data.position
    group.is_active = data.is_active
    existing = {option.id: option for option in group.options}
    kept: list[ModifierOption] = []
    for position, item in enumerate(data.options):
        option = existing.get(item.id) if item.id is not None else None
        if item.id is not None and option is None:
            raise ApiError(422, "invalid_request", "An option does not belong to this group.")
        if option is None:
            option = ModifierOption()
        option.name = item.name.strip()
        option.price_delta_cents = item.price_delta_cents
        option.is_default = item.is_default
        option.is_active = item.is_active
        option.position = position
        kept.append(option)
    # Options removed from the list are deactivated, not deleted: past sale lines name them.
    for option in group.options:
        if option not in kept:
            option.is_active = False
            option.position = len(kept) + option.position
            kept.append(option)
    group.options = kept


def create_group(db: Session, data: ModifierGroupIn) -> ModifierGroupOut:
    group = ModifierGroup()
    _apply(group, data)
    db.add(group)
    db.commit()
    db.refresh(group)
    return _out(group)


def update_group(db: Session, group_id: uuid.UUID, data: ModifierGroupIn) -> ModifierGroupOut:
    group = db.get(ModifierGroup, group_id)
    if group is None:
        raise ApiError(404, "not_found", "Modifier group was not found.")
    _apply(group, data)
    db.commit()
    db.refresh(group)
    return _out(group, _links(db).get(group.id, []))


def set_product_groups(db: Session, product_id: uuid.UUID, data: ProductGroupsIn) -> list[uuid.UUID]:
    product = db.get(Product, product_id)
    if product is None:
        raise ApiError(404, "not_found", "Product was not found.")
    wanted = list(dict.fromkeys(data.group_ids))
    if wanted:
        found = set(db.scalars(select(ModifierGroup.id).where(ModifierGroup.id.in_(wanted))).all())
        if len(found) != len(wanted):
            raise ApiError(422, "invalid_request", "A modifier group does not exist.")
        if product.is_serialized or product.sold_by_weight:
            raise ApiError(422, "invalid_request", "Serialized and weighed products cannot take modifiers.")
    db.execute(delete(ProductModifierGroup).where(ProductModifierGroup.product_id == product_id))
    for position, group_id in enumerate(wanted):
        db.add(ProductModifierGroup(product_id=product_id, group_id=group_id, position=position))
    db.commit()
    return wanted


def register_menu(db: Session) -> RegisterMenu:
    groups = db.scalars(
        select(ModifierGroup).where(ModifierGroup.is_active.is_(True)).order_by(ModifierGroup.position)
    ).all()
    active = {group.id for group in groups}
    products: dict[str, list[uuid.UUID]] = defaultdict(list)
    for link in db.scalars(select(ProductModifierGroup).order_by(ProductModifierGroup.position)):
        if link.group_id in active:
            products[str(link.product_id)].append(link.group_id)
    out = []
    for group in groups:
        row = _out(group)
        row.options = [option for option in row.options if option.is_active]
        out.append(row)
    from app.services import combo_service

    return RegisterMenu(groups=out, products=dict(products), combos=combo_service.register_combos(db))


def price_choices(db: Session, product: Product, choices: list[ModifierChoice]) -> tuple[int, list[dict] | None]:
    """The price delta of a line's modifiers and the snapshot stored on the sale line.

    Rejects options that do not belong to the product's active groups, and selections outside a group's
    minimum/maximum. Deltas come from the catalogue, never from the payload."""
    links = db.scalars(
        select(ProductModifierGroup)
        .where(ProductModifierGroup.product_id == product.id)
        .order_by(ProductModifierGroup.position)
    ).all()
    if not links:
        if choices:
            raise SyncRejected(f"{product.name} has no modifiers.")
        return 0, None
    groups = {
        group.id: group
        for group in db.scalars(select(ModifierGroup).where(ModifierGroup.id.in_([link.group_id for link in links])))
    }
    picked: dict[uuid.UUID, list[ModifierOption]] = defaultdict(list)
    for choice in choices:
        group = groups.get(choice.group_id)
        option = next((item for item in group.options if item.id == choice.option_id), None) if group else None
        # Options retired after an offline register cached the menu still price as they were sold.
        if group is None or option is None:
            raise SyncRejected(f"A modifier on {product.name} is not on this menu.")
        if option in picked[group.id]:
            raise SyncRejected(f"{option.name} was picked twice on {product.name}.")
        picked[group.id].append(option)
    for group in groups.values():
        if not group.is_active:
            continue
        count = len(picked.get(group.id, []))
        if count < group.min_select:
            raise SyncRejected(f"{product.name} needs a choice of {group.name}.")
        if count > group.max_select:
            raise SyncRejected(f"{product.name} allows at most {group.max_select} {group.name}.")
    snapshot = [
        {
            "group_id": str(group_id),
            "group": groups[group_id].name,
            "option_id": str(option.id),
            "option": option.name,
            "price_delta_cents": option.price_delta_cents,
        }
        for group_id, options in picked.items()
        for option in options
    ]
    return sum(option.price_delta_cents for options in picked.values() for option in options), snapshot or None
