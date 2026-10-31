"""Menu modifiers. The portal edits groups and links them to products; registers cache the menu and send each
line's choices, which the server re-prices from this catalogue (names in the payload are informational)."""

import uuid
from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.capabilities import FOOD_AND_BEVERAGE, Capability, resolve
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

# Editable starter groups for a food business. Prices stay at zero until the tenant sets them.
# A group the tenant has renamed or edited is left alone; seeding matches the original name.
_FOOD = frozenset(FOOD_AND_BEVERAGE)
_TEMPLATES: tuple[tuple[str, str, int, int, tuple[str, ...], frozenset[str]], ...] = (
    ("size", "Size", 0, 1, ("Regular", "Medium", "Large"), _FOOD),
    (
        "addons",
        "Add-ons",
        0,
        5,
        ("Extra cheese", "Extra sauce", "Extra toppings", "Extra vegetables", "Extra meat"),
        _FOOD,
    ),
    ("spice", "Spice level", 0, 1, ("Mild", "Medium", "Hot", "Extra hot"), _FOOD),
    ("sauces", "Sauces", 0, 5, ("Ketchup", "Mayonnaise", "BBQ", "Garlic sauce", "Hot sauce"), _FOOD),
    ("milk", "Milk", 0, 1, ("Whole milk", "Skimmed milk", "Oat milk", "Almond milk", "Soy milk"), frozenset({"cafe"})),
)
_MARKER = "modifier_templates"


def templates_for(profile: str) -> list[tuple[str, str, int, int, tuple[str, ...]]]:
    return [
        (key, name, minimum, maximum, options)
        for key, name, minimum, maximum, options, profiles in _TEMPLATES
        if profile in profiles
    ]


def _food_modifiers(row) -> bool:
    if row.business_profile not in FOOD_AND_BEVERAGE:
        return False
    enabled = resolve(row.business_profile, row.capabilities, row.managed_capabilities, row.purchased_capabilities)
    return Capability.MENU_MODIFIERS in enabled.enabled


def ensure_default_groups(db: Session, *, commit: bool = True) -> int:
    """Create any missing starter groups for this store's real business type.

    Runs once per profile. A later edit, rename, or deletion is kept. Sample practice groups do not count,
    so Go live can remove them and the next visit still fills whatever is missing."""
    from app.services.settings_service import load_settings

    row = load_settings(db)
    if not _food_modifiers(row):
        return 0
    profile = row.business_profile
    raw = dict(row.guided_onboarding) if isinstance(row.guided_onboarding, dict) else {}
    if raw.get(_MARKER) == profile:
        return 0
    specs = templates_for(profile)
    groups = db.scalars(select(ModifierGroup)).all()
    real = {group.name.strip().casefold() for group in groups if not group.is_sample}
    taken = real | {group.name.strip().casefold() for group in groups}
    position = max((group.position for group in groups), default=-1)
    created = 0
    for _key, name, minimum, maximum, options in specs:
        if name.casefold() in taken:
            continue
        position += 1
        group = ModifierGroup(
            name=name,
            min_select=minimum,
            max_select=maximum,
            position=position,
            is_active=True,
            is_sample=False,
        )
        group.options = [
            ModifierOption(name=option, price_delta_cents=0, is_default=False, is_active=True, position=index)
            for index, option in enumerate(options)
        ]
        db.add(group)
        real.add(name.casefold())
        taken.add(name.casefold())
        created += 1
    if all(name.casefold() in real for _key, name, _minimum, _maximum, _options in specs):
        raw[_MARKER] = profile
        row.guided_onboarding = raw
    elif created == 0:
        return 0
    db.flush()
    if commit:
        db.commit()
    return created


def list_templates(db: Session) -> list[dict[str, object]]:
    from app.services.settings_service import load_settings

    row = load_settings(db)
    if not _food_modifiers(row):
        return []
    rows = db.scalars(select(ModifierGroup)).all()
    present = {group.name.strip().casefold() for group in rows if not group.is_sample}
    return [
        {
            "key": key,
            "name": name,
            "min_select": minimum,
            "max_select": maximum,
            "options": list(options),
            "present": name.casefold() in present,
        }
        for key, name, minimum, maximum, options in templates_for(row.business_profile)
    ]


def create_from_template(db: Session, key: str) -> ModifierGroupOut:
    from app.services.settings_service import load_settings

    row = load_settings(db)
    if not _food_modifiers(row):
        raise ApiError(422, "invalid_request", "This business does not use menu modifiers.")
    spec = next((item for item in templates_for(row.business_profile) if item[0] == key), None)
    if spec is None:
        raise ApiError(404, "not_found", "That template is not available for this business.")
    _key, name, minimum, maximum, options = spec
    existing = db.scalar(
        select(ModifierGroup).where(ModifierGroup.is_sample.is_(False), ModifierGroup.name.ilike(name))
    )
    if existing is not None:
        raise ApiError(409, "already_exists", f"{name} is already on this menu.")
    position = db.scalar(select(ModifierGroup.position).order_by(ModifierGroup.position.desc()).limit(1))
    group = ModifierGroup(
        name=name,
        min_select=minimum,
        max_select=maximum,
        position=int(position or 0) + 1,
        is_active=True,
        is_sample=False,
    )
    group.options = [
        ModifierOption(name=option, price_delta_cents=0, is_default=False, is_active=True, position=index)
        for index, option in enumerate(options)
    ]
    db.add(group)
    db.commit()
    db.refresh(group)
    return _out(group)


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
    ensure_default_groups(db)
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


def duplicate_group(db: Session, group_id: uuid.UUID) -> ModifierGroupOut:
    source = db.get(ModifierGroup, group_id)
    if source is None:
        raise ApiError(404, "not_found", "Modifier group was not found.")
    position = db.scalar(select(ModifierGroup.position).order_by(ModifierGroup.position.desc()).limit(1))
    copy = ModifierGroup(
        name=f"{source.name} copy"[:80],
        min_select=source.min_select,
        max_select=source.max_select,
        position=int(position or 0) + 1,
        is_active=source.is_active,
        is_sample=False,
    )
    copy.options = [
        ModifierOption(
            name=option.name,
            price_delta_cents=option.price_delta_cents,
            is_default=option.is_default,
            is_active=option.is_active,
            position=option.position,
        )
        for option in source.options
        if option.is_active
    ]
    if not copy.options:
        raise ApiError(422, "invalid_request", "Add an active option before copying this group.")
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return _out(copy)


def delete_group(db: Session, group_id: uuid.UUID, *, detach: bool) -> None:
    group = db.get(ModifierGroup, group_id)
    if group is None:
        raise ApiError(404, "not_found", "Modifier group was not found.")
    links = db.scalars(select(ProductModifierGroup).where(ProductModifierGroup.group_id == group.id)).all()
    if links and not detach:
        raise ApiError(
            409,
            "group_in_use",
            "This group is still offered on products. Remove those links, then delete it.",
        )
    if links:
        db.execute(delete(ProductModifierGroup).where(ProductModifierGroup.group_id == group.id))
    db.delete(group)
    db.commit()


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
