"""One compressed bill image per expense, stored outside the public media folder."""

from __future__ import annotations

import base64
import hashlib
import io
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.expense import Expense, ExpenseAttachment
from app.schemas.expenses import ExpenseBillIn, ExpenseBillOut
from app.tenancy.context import current_tenant

MAX_BYTES = 8 * 1024 * 1024
MAX_EDGE = 2000
ROOT = Path(__file__).resolve().parents[2] / "storage" / "expense-bills"
Image.MAX_IMAGE_PIXELS = 40_000_000


def _magic(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def compress(data: bytes, declared: str) -> tuple[bytes, str]:
    if not data:
        raise ApiError(422, "empty_file", "The bill image could not be processed. Try another image.")
    if len(data) > MAX_BYTES:
        raise ApiError(413, "file_too_large", "The attachment exceeds the permitted size.")
    kind = _magic(data)
    declared_type = (declared or "").split(";")[0].strip().lower()
    if kind is None or declared_type not in {"image/jpeg", "image/png", "image/webp", ""}:
        raise ApiError(415, "unsupported_file", "Unsupported bill format. Upload a JPG, PNG or WebP image.")
    if declared_type and declared_type != kind:
        raise ApiError(415, "unsupported_file", "Unsupported bill format. Upload a JPG, PNG or WebP image.")
    try:
        Image.open(io.BytesIO(data)).verify()
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
        if image is None:
            raise UnidentifiedImageError("empty")
        image = image.convert("RGB")
        image.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, "WEBP", quality=85, method=4)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError, ValueError) as error:
        raise ApiError(422, "image_unreadable", "The bill image could not be processed. Try another image.") from error
    encoded = buffer.getvalue()
    if not encoded:
        raise ApiError(422, "image_unreadable", "The bill image could not be processed. Try another image.")
    return encoded, "image/webp"


def store(db: Session, expense: Expense, bill: ExpenseBillIn, user_id: uuid.UUID | None) -> Path:
    raw = _decode(bill.data_base64)
    encoded, content_type = compress(raw, bill.content_type)
    tenant = str(expense.tenant_id or (current_tenant().id if current_tenant() else "default"))
    key = f"{tenant}/{expense.id}.webp"
    path = (ROOT / key).resolve()
    if ROOT.resolve() not in path.parents:
        raise ApiError(422, "invalid_file", "The bill image could not be processed. Try another image.")
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    partial.write_bytes(encoded)
    partial.replace(path)
    existing = db.scalar(select(ExpenseAttachment).where(ExpenseAttachment.expense_id == expense.id))
    if existing is None:
        existing = ExpenseAttachment(expense_id=expense.id, store_id=expense.store_id, storage_key=key)
        db.add(existing)
    existing.file_name = Path(bill.file_name or "bill").name[:160] or "bill"
    existing.content_type = content_type
    existing.original_size_bytes = len(raw)
    existing.size_bytes = len(encoded)
    existing.storage_key = key
    existing.checksum = hashlib.sha256(encoded).hexdigest()
    existing.status = "STORED"
    existing.uploaded_by_id = user_id
    existing.store_id = expense.store_id
    return path


def read_for(db: Session, expense: Expense) -> ExpenseBillOut:
    row = db.scalar(select(ExpenseAttachment).where(ExpenseAttachment.expense_id == expense.id))
    if row is None or row.status != "STORED":
        raise ApiError(404, "not_found", "This expense has no bill image.")
    path = (ROOT / row.storage_key).resolve()
    if ROOT.resolve() not in path.parents or not path.is_file():
        raise ApiError(404, "not_found", "This expense has no bill image.")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != row.checksum:
        raise ApiError(409, "file_mismatch", "The stored bill does not match its record.")
    return ExpenseBillOut(
        file_name=row.file_name,
        content_type=row.content_type,
        original_size_bytes=row.original_size_bytes,
        size_bytes=len(data),
        data_base64=base64.b64encode(data).decode("ascii"),
    )


def bill_ids(db: Session, expense_ids: set[uuid.UUID]) -> set[uuid.UUID]:
    if not expense_ids:
        return set()
    return set(db.scalars(select(ExpenseAttachment.expense_id).where(ExpenseAttachment.expense_id.in_(expense_ids))))


def discard(path: Path | None) -> None:
    if path is None:
        return
    path.unlink(missing_ok=True)


def _decode(value: str) -> bytes:
    cleaned = "".join(value.split())
    if not cleaned:
        raise ApiError(422, "empty_file", "The bill image could not be processed. Try another image.")
    try:
        return base64.b64decode(cleaned + "=" * ((-len(cleaned)) % 4), validate=False)
    except (ValueError, TypeError) as error:
        raise ApiError(422, "image_unreadable", "The bill image could not be processed. Try another image.") from error
