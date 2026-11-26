"""Authenticated catalogue bootstrap and incremental product pull.

The snapshot copies catalogue rows in one transaction, after the feed counter is locked.
Pages read that copy. A later product edit is a catalog_changes row, not a rewrite of the page.

The counter row is updated with value = value + n in the same transaction as the product write.
The next writer waits for that lock, so a commit cannot publish a higher sequence while a lower
one is still open. MAX(seq) is not the cursor.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, event, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.models.bootstrap import (
    BootstrapDatasetItem,
    BootstrapSession,
    BootstrapSettingSnapshot,
    BootstrapSnapshotItem,
    CatalogChange,
    CatalogFeedCounter,
)
from app.models.business_settings import BusinessSettings
from app.models.device import Device
from app.models.menu import MenuPriceOption, ModifierGroup, ModifierOption, ProductModifierGroup
from app.models.product import Product
from app.models.restaurant import DiningArea, DiningTable
from app.tenancy.scoping import active_tenant_id

SCHEMA_VERSION = 1
# Menu and floor share this feed's sequence. Floor rows carry store_id and are omitted for other branches.
DATASETS = frozenset({"products", "checkout_settings", "menu", "floor"})
PAGE_MAX = 100
SNAPSHOT_TTL = timedelta(minutes=30)


def _dump(record: dict[str, Any]) -> str:
    return json.dumps(record, separators=(",", ":"), default=str, sort_keys=True)


def _catalogue_record(db: Session, products: list[Product], store_id: uuid.UUID) -> list[dict[str, Any]]:
    """Snapshot rows. The branch quantity is the existing cache, not a quantity reserved for this till."""
    from app.services.inventory import products_out

    rows = products_out(db, products, store_id)
    records = []
    for row in rows:
        record = row.model_dump(mode="json")
        # The branch quantity already on the catalogue row. It is not reserved for this terminal.
        record["stock_authoritative"] = True
        record["store_id"] = str(store_id)
        records.append(record)
    if len(records) != len(products):
        raise ApiError(422, "bootstrap_record", "The catalogue row could not be read.")
    return records


def _change_record(product: Product) -> dict[str, Any]:
    return {
        "id": str(product.id),
        "sku": product.sku,
        "barcode": product.barcode,
        "name": product.name,
        "category": product.category,
        "price_cents": int(product.price_cents),
        "currency": product.currency,
        "is_serialized": bool(product.is_serialized),
        "is_active": bool(product.is_active),
        "stock_quantity": 0,
        "stock_authoritative": False,
    }


def _menu_body(obj: object) -> tuple[str, dict[str, Any]]:
    if isinstance(obj, ModifierGroup):
        return str(obj.id), {
            "id": str(obj.id),
            "kind": "group",
            "name": obj.name,
            "min_select": int(obj.min_select),
            "max_select": int(obj.max_select),
            "position": int(obj.position),
            "is_active": bool(obj.is_active),
        }
    if isinstance(obj, ModifierOption):
        return str(obj.id), {
            "id": str(obj.id),
            "kind": "option",
            "group_id": str(obj.group_id),
            "name": obj.name,
            "price_delta_cents": int(obj.price_delta_cents),
            "is_default": bool(obj.is_default),
            "is_active": bool(obj.is_active),
            "position": int(obj.position),
        }
    if isinstance(obj, MenuPriceOption):
        return str(obj.id), {
            "id": str(obj.id),
            "kind": "price_option",
            "product_id": str(obj.product_id),
            "name": obj.name,
            "price_cents": int(obj.price_cents),
            "sku": obj.sku,
            "is_active": bool(obj.is_active),
            "position": int(obj.position),
        }
    link = obj
    assert isinstance(link, ProductModifierGroup)
    record_id = f"{link.product_id}:{link.group_id}"
    return record_id, {
        "id": record_id,
        "kind": "link",
        "product_id": str(link.product_id),
        "group_id": str(link.group_id),
        "position": int(link.position),
    }


def _floor_body(session: Session, obj: object, operation: str) -> tuple[str, dict[str, Any]]:
    if isinstance(obj, DiningArea):
        body = {
            "id": str(obj.id),
            "kind": "area",
            "store_id": str(obj.store_id),
            "name": obj.name,
            "position": int(obj.position or 0),
            "is_active": bool(obj.is_active),
        }
        if operation == "delete":
            body = {"id": str(obj.id), "kind": "area", "store_id": str(obj.store_id)}
        return str(obj.id), body
    table = obj
    assert isinstance(table, DiningTable)
    area = session.get(DiningArea, table.area_id)
    store_id = str(area.store_id) if area is not None else ""
    if operation == "delete":
        return str(table.id), {"id": str(table.id), "kind": "table", "store_id": store_id}
    return str(table.id), {
        "id": str(table.id),
        "kind": "table",
        "store_id": store_id,
        "area_id": str(table.area_id),
        "label": table.label,
        "seats": int(table.seats or 0),
        "shape": table.shape,
        "x": int(table.x or 0),
        "y": int(table.y or 0),
        "w": int(table.w or 0),
        "h": int(table.h or 0),
        "is_active": bool(table.is_active),
    }


def _pending_menu(session: Session) -> list[tuple[str, str, str, str | None]]:
    rows: list[tuple[str, str, str, str | None]] = []
    for operation, bucket in (("upsert", list(session.new) + list(session.dirty)), ("delete", list(session.deleted))):
        for obj in bucket:
            if not isinstance(obj, (ModifierGroup, ModifierOption, ProductModifierGroup, MenuPriceOption)):
                continue
            if (
                operation == "upsert"
                and obj in session.dirty
                and not session.is_modified(obj, include_collections=False)
            ):
                continue
            record_id, body = _menu_body(obj)
            rows.append(("menu", operation, record_id, None if operation == "delete" else _dump(body)))
    return rows


def _pending_floor(session: Session) -> list[tuple[str, str, str, str | None]]:
    rows: list[tuple[str, str, str, str | None]] = []
    for operation, bucket in (("upsert", list(session.new) + list(session.dirty)), ("delete", list(session.deleted))):
        for obj in bucket:
            if not isinstance(obj, (DiningArea, DiningTable)):
                continue
            if (
                operation == "upsert"
                and obj in session.dirty
                and not session.is_modified(obj, include_collections=False)
            ):
                continue
            record_id, body = _floor_body(session, obj, operation)
            rows.append(("floor", operation, record_id, _dump(body)))
    return rows


def allocate_seqs(db: Session, count: int) -> int:
    """First new sequence, or the current value when count is 0. Holds the counter until commit."""
    if count < 0:
        raise ApiError(422, "bootstrap_record", "The catalogue feed could not be recorded.")
    tenant_id = active_tenant_id()
    for _ in range(4):
        counter = db.scalar(select(CatalogFeedCounter).where(CatalogFeedCounter.tenant_id == tenant_id))
        if counter is None:
            nested = db.begin_nested()
            try:
                db.add(CatalogFeedCounter(tenant_id=tenant_id, value=0, retain_after=0))
                db.flush()
                nested.commit()
            except IntegrityError:
                nested.rollback()
                continue
        new_value = db.execute(
            update(CatalogFeedCounter)
            .where(CatalogFeedCounter.tenant_id == tenant_id)
            .values(value=CatalogFeedCounter.value + count)
            .returning(CatalogFeedCounter.value)
        ).scalar_one()
        if count == 0:
            return int(new_value)
        return int(new_value) - count + 1
    raise ApiError(503, "bootstrap_busy", "The catalogue feed is busy. Try again.")


def note_retention(db: Session, seq: int) -> None:
    """Forget change rows at or below seq. A cursor older than that must bootstrap again."""
    tenant_id = active_tenant_id()
    allocate_seqs(db, 0)
    db.execute(update(CatalogFeedCounter).where(CatalogFeedCounter.tenant_id == tenant_id).values(retain_after=seq))
    db.execute(delete(CatalogChange).where(CatalogChange.tenant_id == tenant_id, CatalogChange.seq <= seq))


def _settings_record(row: BusinessSettings) -> dict[str, Any]:
    """Currency, tax, and receipt facts checkout needs. Credentials and payroll stay on the server."""
    return {
        "currency": row.currency,
        "legal_name": row.legal_name,
        "legal_name_ar": row.legal_name_ar,
        "prices_include_vat": bool(row.prices_include_vat),
        "receipt": row.receipt,
        "standard_rate_bps": int(row.standard_rate_bps or 0),
        "tax_authority": row.tax_authority,
        "trn": row.trn,
        "vat_registered": bool(row.vat_registered),
    }


def _seqs_in_flush(session: Session, count: int) -> int:
    """Next sequences for rows added in this flush. Does not flush again."""
    tenant_id = active_tenant_id()
    counter = session.scalar(select(CatalogFeedCounter).where(CatalogFeedCounter.tenant_id == tenant_id))
    if counter is None:
        session.add(CatalogFeedCounter(tenant_id=tenant_id, value=count, retain_after=0))
        return 1
    if counter in session.new:
        first = int(counter.value) + 1
        counter.value = int(counter.value) + count
        return first
    new_value = session.execute(
        update(CatalogFeedCounter)
        .where(CatalogFeedCounter.tenant_id == tenant_id)
        .values(value=CatalogFeedCounter.value + count)
        .returning(CatalogFeedCounter.value)
    ).scalar_one()
    return int(new_value) - count + 1


@event.listens_for(Session, "before_flush")
def _write_product_changes(session: Session, flush_context: object, instances: object) -> None:
    if session.info.get("bootstrap_recording"):
        return
    pending: list[tuple[str, Product]] = []
    settings: list[BusinessSettings] = []
    for obj in list(session.new):
        if isinstance(obj, Product):
            pending.append(("upsert", obj))
        elif isinstance(obj, BusinessSettings):
            settings.append(obj)
    for obj in list(session.dirty):
        if isinstance(obj, Product) and session.is_modified(obj, include_collections=False):
            pending.append(("upsert", obj))
        elif isinstance(obj, BusinessSettings) and session.is_modified(obj, include_collections=False):
            settings.append(obj)
    for obj in list(session.deleted):
        if isinstance(obj, Product):
            pending.append(("delete", obj))
    session.info["bootstrap_recording"] = True
    try:
        menu_rows = _pending_menu(session)
        floor_rows = _pending_floor(session)
        side = _pos_side_changes(session)
        if not pending and not settings and not menu_rows and not floor_rows and not side:
            return
        last_seq: int | None = None
        if pending or settings or menu_rows or floor_rows:
            first = _seqs_in_flush(session, len(pending) + len(settings) + len(menu_rows) + len(floor_rows))
            offset = 0
            for operation, product in pending:
                body = None if operation == "delete" else _dump(_change_record(product))
                session.add(
                    CatalogChange(
                        tenant_id=getattr(product, "tenant_id", None) or active_tenant_id(),
                        seq=first + offset,
                        dataset="products",
                        record_id=str(product.id),
                        operation=operation,
                        payload=body,
                    )
                )
                offset += 1
            for row in settings:
                session.add(
                    CatalogChange(
                        tenant_id=getattr(row, "tenant_id", None) or active_tenant_id(),
                        seq=first + offset,
                        dataset="checkout_settings",
                        record_id="checkout",
                        operation="settings",
                        payload=_dump(_settings_record(row)),
                    )
                )
                offset += 1
            for dataset, operation, record_id, body in menu_rows + floor_rows:
                session.add(
                    CatalogChange(
                        tenant_id=active_tenant_id(),
                        seq=first + offset,
                        dataset=dataset,
                        record_id=record_id,
                        operation=operation,
                        payload=body,
                    )
                )
                offset += 1
            last_seq = first + offset - 1
        _announce_catalogue(session, last_seq)
    finally:
        session.info["bootstrap_recording"] = False


def _pos_side_changes(session: Session) -> bool:
    """Category, promotion, and stock edits that the product feed does not already record.

    A category rename updates product rows with a bulk statement, so those products are not
    dirty ORM objects and would not move the register on their own.
    """
    from app.models.category import Category, SubCategory
    from app.models.inventory import InventoryLevel
    from app.models.promotion import Promotion

    watched = (Category, SubCategory, Promotion, InventoryLevel)
    for obj in list(session.new) + list(session.deleted):
        if isinstance(obj, watched):
            return True
    for obj in list(session.dirty):
        if isinstance(obj, watched) and session.is_modified(obj, include_collections=False):
            return True
    return False


def _announce_catalogue(session: Session, seq: int | None) -> None:
    """Tell each of this tenant's registers after the commit. A rollback drops the queued event."""
    from app.models.store import Store
    from app.websockets import rooms

    payload = {"type": "catalogue.changed", "seq": seq}
    for store_id in session.scalars(select(Store.id)):
        rooms.queue(session, rooms.pos_terminals_room(store_id), payload)


def start_session(db: Session, device: Device) -> BootstrapSession:
    from app.tenancy.scoping import bind_request_scope

    bind_request_scope(db, device.store_id, device.id)
    tenant_id = active_tenant_id()
    watermark = allocate_seqs(db, 0)
    products = list(db.scalars(select(Product).where(Product.tenant_id == tenant_id).order_by(Product.id)))
    session = BootstrapSession(
        tenant_id=tenant_id,
        device_id=device.id,
        store_id=device.store_id,
        schema_version=SCHEMA_VERSION,
        status="open",
        product_count=len(products),
        watermark=str(watermark),
        since_seq=watermark,
    )
    db.add(session)
    db.flush()
    for position, record in enumerate(_catalogue_record(db, products, device.store_id)):
        db.add(
            BootstrapSnapshotItem(
                tenant_id=tenant_id,
                session_id=session.id,
                position=position,
                product_id=uuid.UUID(str(record["id"])),
                payload=_dump(record),
            )
        )
    settings = db.scalar(select(BusinessSettings).where(BusinessSettings.tenant_id == tenant_id).limit(1))
    if settings is not None:
        db.add(
            BootstrapSettingSnapshot(
                tenant_id=tenant_id,
                session_id=session.id,
                payload=_dump(_settings_record(settings)),
            )
        )
    _freeze_config(db, session, device.store_id)
    db.commit()
    return session


def _freeze_config(db: Session, session: BootstrapSession, store_id: uuid.UUID) -> None:
    """Copy this branch's floor and the tenant menu into the snapshot. Later edits are feed rows."""
    tenant_id = session.tenant_id
    position = 0
    groups = select(ModifierGroup).where(ModifierGroup.tenant_id == tenant_id).order_by(ModifierGroup.id)
    for group in db.scalars(groups):
        record_id, body = _menu_body(group)
        db.add(
            BootstrapDatasetItem(
                tenant_id=tenant_id,
                session_id=session.id,
                dataset="menu",
                position=position,
                record_id=record_id,
                payload=_dump(body),
            )
        )
        position += 1
    options = select(ModifierOption).where(ModifierOption.tenant_id == tenant_id).order_by(ModifierOption.id)
    for option in db.scalars(options):
        record_id, body = _menu_body(option)
        db.add(
            BootstrapDatasetItem(
                tenant_id=tenant_id,
                session_id=session.id,
                dataset="menu",
                position=position,
                record_id=record_id,
                payload=_dump(body),
            )
        )
        position += 1
    for link in db.scalars(
        select(ProductModifierGroup)
        .where(ProductModifierGroup.tenant_id == tenant_id)
        .order_by(ProductModifierGroup.product_id)
    ):
        record_id, body = _menu_body(link)
        db.add(
            BootstrapDatasetItem(
                tenant_id=tenant_id,
                session_id=session.id,
                dataset="menu",
                position=position,
                record_id=record_id,
                payload=_dump(body),
            )
        )
        position += 1
    priced = select(MenuPriceOption).where(MenuPriceOption.tenant_id == tenant_id).order_by(MenuPriceOption.id)
    for option in db.scalars(priced):
        record_id, body = _menu_body(option)
        db.add(
            BootstrapDatasetItem(
                tenant_id=tenant_id,
                session_id=session.id,
                dataset="menu",
                position=position,
                record_id=record_id,
                payload=_dump(body),
            )
        )
        position += 1
    floor_at = 0
    areas = list(
        db.scalars(
            select(DiningArea)
            .where(DiningArea.tenant_id == tenant_id, DiningArea.store_id == store_id)
            .order_by(DiningArea.id)
        ).all()
    )
    area_ids = [area.id for area in areas]
    for area in areas:
        record_id, body = _floor_body(db, area, "upsert")
        db.add(
            BootstrapDatasetItem(
                tenant_id=tenant_id,
                session_id=session.id,
                dataset="floor",
                position=floor_at,
                record_id=record_id,
                payload=_dump(body),
            )
        )
        floor_at += 1
    if area_ids:
        tables = db.scalars(
            select(DiningTable).where(DiningTable.area_id.in_(area_ids)).order_by(DiningTable.id)
        ).all()
        for table in tables:
            record_id, body = _floor_body(db, table, "upsert")
            db.add(
                BootstrapDatasetItem(
                    tenant_id=tenant_id,
                    session_id=session.id,
                    dataset="floor",
                    position=floor_at,
                    record_id=record_id,
                    payload=_dump(body),
                )
            )
            floor_at += 1


def _own_session(db: Session, device: Device, session_id: uuid.UUID) -> BootstrapSession:
    row = db.get(BootstrapSession, session_id)
    if (
        row is None
        or row.tenant_id != active_tenant_id()
        or row.device_id != device.id
        or row.store_id != device.store_id
    ):
        raise ApiError(404, "bootstrap_not_found", "That bootstrap session is not available to this register.")
    if row.schema_version != SCHEMA_VERSION:
        raise ApiError(409, "bootstrap_version", "This register does not understand that bootstrap version.")
    created = row.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    if datetime.now(UTC) - created > SNAPSHOT_TTL:
        raise ApiError(409, "snapshot_expired", "This catalogue snapshot expired. Start the download again.")
    return row


def _dataset_page(
    db: Session,
    device: Device,
    row: BootstrapSession,
    dataset: str,
    after_position: int,
    limit: int,
) -> dict[str, Any]:
    total = int(
        db.scalar(
            select(func.count())
            .select_from(BootstrapDatasetItem)
            .where(BootstrapDatasetItem.session_id == row.id, BootstrapDatasetItem.dataset == dataset)
        )
        or 0
    )
    items = db.scalars(
        select(BootstrapDatasetItem)
        .where(
            BootstrapDatasetItem.session_id == row.id,
            BootstrapDatasetItem.dataset == dataset,
            BootstrapDatasetItem.position > after_position,
        )
        .order_by(BootstrapDatasetItem.position)
        .limit(limit)
    ).all()
    records = []
    last = after_position
    for item in items:
        last = item.position
        records.append(
            {
                "position": item.position,
                "operation": "upsert",
                "id": item.record_id,
                "record": json.loads(item.payload),
            }
        )
    done = total == 0 or last >= total - 1
    return {
        "session_id": str(row.id),
        "dataset": dataset,
        "schema_version": row.schema_version,
        "product_count": row.product_count,
        "after_position": after_position,
        "next_position": last,
        "done": done,
        "records": records,
        "since_seq": row.since_seq,
        "cursor": issue_cursor(device, row.since_seq, row.id),
    }


def page(
    db: Session,
    device: Device,
    session_id: uuid.UUID,
    dataset: str,
    after_position: int,
    limit: int,
) -> dict[str, Any]:
    if dataset not in DATASETS:
        raise ApiError(403, "dataset_forbidden", "That dataset is not available to this register.")
    if limit < 1 or limit > PAGE_MAX:
        raise ApiError(422, "page_size", "Page size is out of range.")
    if after_position < -1:
        raise ApiError(422, "page_cursor", "The page cursor is not valid.")
    row = _own_session(db, device, session_id)
    if dataset in {"menu", "floor"}:
        return _dataset_page(db, device, row, dataset, after_position, limit)
    if dataset == "checkout_settings":
        snap = db.get(BootstrapSettingSnapshot, row.id)
        records = []
        if snap is not None and after_position < 0:
            records.append(
                {"position": 0, "operation": "settings", "id": "checkout", "record": json.loads(snap.payload)}
            )
        return {
            "session_id": str(row.id),
            "dataset": dataset,
            "schema_version": row.schema_version,
            "product_count": row.product_count,
            "after_position": after_position,
            "next_position": 0 if records else after_position,
            "done": True,
            "records": records,
            "since_seq": row.since_seq,
            "cursor": issue_cursor(device, row.since_seq, row.id),
        }
    items = db.scalars(
        select(BootstrapSnapshotItem)
        .where(
            BootstrapSnapshotItem.session_id == row.id,
            BootstrapSnapshotItem.position > after_position,
        )
        .order_by(BootstrapSnapshotItem.position)
        .limit(limit)
    ).all()
    records = []
    last = after_position
    for item in items:
        last = item.position
        record = json.loads(item.payload)
        records.append({"position": item.position, "operation": "upsert", "id": str(item.product_id), "record": record})
    done = row.product_count == 0 or last == row.product_count - 1
    if done and row.status == "open":
        row.status = "complete"
        db.commit()
    return {
        "session_id": str(row.id),
        "dataset": dataset,
        "schema_version": row.schema_version,
        "product_count": row.product_count,
        "after_position": after_position,
        "next_position": last,
        "done": done,
        "records": records,
        "since_seq": row.since_seq,
        "cursor": issue_cursor(device, row.since_seq, row.id),
    }


def _sign(body: str) -> str:
    secret = get_settings().jwt_secret.encode("utf-8")
    return hmac.new(secret, body.encode("utf-8"), hashlib.sha256).hexdigest()


def issue_cursor(device: Device, seq: int, session_id: uuid.UUID) -> str:
    body = json.dumps(
        {
            "branch_id": str(device.store_id),
            "schema_version": SCHEMA_VERSION,
            "seq": seq,
            "session_id": str(session_id),
            "tenant_id": str(active_tenant_id()),
            "terminal_id": str(device.id),
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    token = json.dumps({"body": body, "mac": _sign(body)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("ascii")


def _read_cursor(device: Device, token: str) -> tuple[int, uuid.UUID]:
    try:
        decoded = json.loads(base64.urlsafe_b64decode(token.encode("ascii")))
        body = decoded["body"]
        if not hmac.compare_digest(_sign(body), decoded["mac"]):
            raise ValueError("mac")
        payload = json.loads(body)
    except Exception as exc:
        raise ApiError(401, "invalid_cursor", "The pull cursor is not valid.") from exc
    if payload.get("tenant_id") != str(active_tenant_id()) or payload.get("branch_id") != str(device.store_id):
        raise ApiError(403, "cursor_scope", "The pull cursor is not valid for this register.")
    if payload.get("terminal_id") != str(device.id) or payload.get("schema_version") != SCHEMA_VERSION:
        raise ApiError(403, "cursor_scope", "The pull cursor is not valid for this register.")
    seq = payload.get("seq")
    try:
        parsed_session = uuid.UUID(str(payload.get("session_id")))
    except (TypeError, ValueError) as exc:
        raise ApiError(401, "invalid_cursor", "The pull cursor is not valid.") from exc
    if not isinstance(seq, int) or seq < 0:
        raise ApiError(401, "invalid_cursor", "The pull cursor is not valid.")
    return seq, parsed_session


def _session_for_cursor(db: Session, device: Device, session_id: uuid.UUID) -> BootstrapSession:
    row = db.get(BootstrapSession, session_id)
    if (
        row is None
        or row.tenant_id != active_tenant_id()
        or row.device_id != device.id
        or row.store_id != device.store_id
    ):
        raise ApiError(403, "cursor_scope", "The pull cursor is not valid for this register.")
    latest = db.scalar(
        select(BootstrapSession)
        .where(BootstrapSession.device_id == device.id, BootstrapSession.tenant_id == active_tenant_id())
        .order_by(BootstrapSession.created_at.desc())
    )
    if latest is None or latest.id != row.id:
        raise ApiError(409, "cursor_generation", "The pull cursor is not for this register's current download.")
    return row


def pull(db: Session, device: Device, token: str, limit: int) -> dict[str, Any]:
    from app.tenancy.scoping import bind_request_scope

    bind_request_scope(db, device.store_id, device.id)
    if limit < 1 or limit > PAGE_MAX:
        raise ApiError(422, "page_size", "Page size is out of range.")
    seq, session_id = _read_cursor(device, token)
    tenant_id = active_tenant_id()
    counter = db.scalar(select(CatalogFeedCounter).where(CatalogFeedCounter.tenant_id == tenant_id))
    if counter is not None and seq < int(counter.retain_after):
        raise ApiError(409, "rebootstrap_required", "This register must download the catalogue again.")
    owned = _session_for_cursor(db, device, session_id)
    rows = list(
        db.scalars(
            select(CatalogChange)
            .where(CatalogChange.tenant_id == tenant_id, CatalogChange.seq > seq)
            .order_by(CatalogChange.seq)
            .limit(limit)
        ).all()
    )
    if rows and int(rows[0].seq) > seq + 1:
        raise ApiError(409, "rebootstrap_required", "This register must download the catalogue again.")
    changes = []
    next_seq = seq
    expected = seq
    for row in rows:
        if row.dataset not in DATASETS:
            continue
        if int(row.seq) != expected + 1:
            raise ApiError(409, "rebootstrap_required", "This register must download the catalogue again.")
        expected = int(row.seq)
        record = json.loads(row.payload) if row.payload else None
        operation = row.operation
        record_id = row.record_id
        if row.dataset == "floor":
            store_id = str(record.get("store_id")) if isinstance(record, dict) else ""
            if store_id != str(device.store_id):
                operation = "omit"
                record = None
                record_id = ""
        elif isinstance(record, dict) and row.dataset == "products":
            record["store_id"] = str(device.store_id)
        changes.append(
            {
                "seq": row.seq,
                "dataset": row.dataset,
                "record_id": record_id,
                "operation": operation,
                "record": record,
            }
        )
        next_seq = int(row.seq)
    return {
        "changes": changes,
        "cursor": issue_cursor(device, next_seq, owned.id),
        "more": len(rows) == limit,
        "session_id": str(owned.id),
    }
