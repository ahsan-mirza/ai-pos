"""Read a spreadsheet or PDF the user attached to the assistant.

The parser is the existing purchase-file reader. It does not run spreadsheet formulas or macros.
Nothing in this module inserts products, stock, or customers. Cell text is data, not an instruction.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.product import Product
from app.services import assistant_scope, import_parser
from app.services.media_storage import ROOT, tenant_slug

_ALLOWED = {".csv": b"", ".xlsx": b"PK", ".pdf": b"%PDF"}


@dataclass(frozen=True)
class DocumentAnalysis:
    id: str
    file_name: str
    source: str
    columns: list[str]
    row_count: int
    duplicate_codes: int
    missing_prices: int
    missing_codes: int
    existing_products: int
    new_products: int
    warnings: list[str]
    committed: bool = False


def _kind(file_name: str, data: bytes) -> str:
    suffix = Path(file_name or "").suffix.lower()
    if suffix not in _ALLOWED:
        raise ApiError(422, "unsupported_file", "Attach an Excel (.xlsx), CSV, or PDF file.")
    if suffix == ".csv":
        if data.startswith(b"PK") or data.startswith(b"%PDF"):
            raise ApiError(422, "unsupported_file", "This file is not a CSV.")
        return suffix
    magic = _ALLOWED[suffix]
    if not data.startswith(magic):
        raise ApiError(422, "unreadable_file", "The file contents do not match its type.")
    return suffix


def _index(headers: list[str], column: str | None) -> int | None:
    if not column:
        return None
    try:
        return headers.index(column)
    except ValueError:
        return None


def _codes(rows: list[list[str]], index: int | None) -> list[str]:
    if index is None:
        return []
    found: list[str] = []
    for row in rows:
        value = row[index].strip() if index < len(row) else ""
        if value:
            found.append(value.upper())
    return found


def _catalog_codes(db: Session) -> set[str]:
    codes: set[str] = set()
    for sku, barcode in db.execute(select(Product.sku, Product.barcode)):
        if isinstance(sku, str) and sku.strip():
            codes.add(sku.strip().upper())
        if isinstance(barcode, str) and barcode.strip():
            codes.add(barcode.strip().upper())
    return codes


def analyze(db: Session, file_name: str, data: bytes) -> DocumentAnalysis:
    """Count real rows and match codes already in this store. The file is kept; products are not."""
    if not data:
        raise ApiError(422, "empty_file", "The uploaded file is empty.")
    _kind(file_name, data)
    parsed = import_parser.parse(file_name, data)
    mapping = import_parser.suggest_mapping(parsed.headers)
    code_at = _index(parsed.headers, mapping.get("code"))
    price_at = _index(parsed.headers, mapping.get("price"))
    codes = _codes(parsed.rows, code_at)
    counts: dict[str, int] = {}
    for code in codes:
        counts[code] = counts.get(code, 0) + 1
    known = _catalog_codes(db) if code_at is not None else set()
    distinct = set(codes)
    warnings = list(parsed.warnings)
    if code_at is None:
        warnings.append("No SKU or barcode column was detected.")
    if price_at is None:
        warnings.append("No selling price column was detected.")
    missing_prices = 0
    if price_at is not None:
        for row in parsed.rows:
            raw = row[price_at].strip() if price_at < len(row) else ""
            if import_parser.parse_money(raw) is None:
                missing_prices += 1
    else:
        missing_prices = len(parsed.rows)
    document_id = uuid.uuid4().hex
    analysis = DocumentAnalysis(
        id=document_id,
        file_name=Path(file_name or "upload").name[:255] or "upload",
        source=parsed.source,
        columns=parsed.headers[:40],
        row_count=len(parsed.rows),
        duplicate_codes=sum(1 for count in counts.values() if count > 1),
        missing_prices=missing_prices,
        missing_codes=(len(parsed.rows) - len(codes)) if code_at is not None else len(parsed.rows),
        existing_products=len(distinct & known),
        new_products=len(distinct - known),
        warnings=warnings[:12],
    )
    _store(document_id, file_name, data, analysis)
    return analysis


def _store(document_id: str, file_name: str, data: bytes, analysis: DocumentAnalysis) -> None:
    tenant_id = assistant_scope.require_tenant_id()
    folder = ROOT / tenant_slug() / "assistant"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{document_id}.bin"
    partial = target.with_suffix(".part")
    partial.write_bytes(data)
    partial.replace(target)
    meta = {
        "tenant_id": tenant_id,
        "file_name": analysis.file_name,
        "checksum": hashlib.sha256(data).hexdigest(),
        "analysis": _as_dict(analysis),
    }
    (folder / f"{document_id}.json").write_text(json.dumps(meta), encoding="utf-8")


def _as_dict(analysis: DocumentAnalysis) -> dict:
    return {
        "id": analysis.id,
        "file_name": analysis.file_name,
        "source": analysis.source,
        "columns": analysis.columns,
        "row_count": analysis.row_count,
        "duplicate_codes": analysis.duplicate_codes,
        "missing_prices": analysis.missing_prices,
        "missing_codes": analysis.missing_codes,
        "existing_products": analysis.existing_products,
        "new_products": analysis.new_products,
        "warnings": analysis.warnings,
        "committed": False,
    }


def load_analysis(document_id: str) -> DocumentAnalysis | None:
    if len(document_id) != 32 or any(char not in "0123456789abcdef" for char in document_id):
        return None
    path = ROOT / tenant_slug() / "assistant" / f"{document_id}.json"
    if not path.is_file():
        return None
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if meta.get("tenant_id") != assistant_scope.require_tenant_id():
        return None
    raw = meta.get("analysis")
    if not isinstance(raw, dict):
        return None
    return DocumentAnalysis(
        id=str(raw.get("id") or document_id),
        file_name=str(raw.get("file_name") or ""),
        source=str(raw.get("source") or ""),
        columns=[str(item) for item in raw.get("columns") or []],
        row_count=int(raw.get("row_count") or 0),
        duplicate_codes=int(raw.get("duplicate_codes") or 0),
        missing_prices=int(raw.get("missing_prices") or 0),
        missing_codes=int(raw.get("missing_codes") or 0),
        existing_products=int(raw.get("existing_products") or 0),
        new_products=int(raw.get("new_products") or 0),
        warnings=[str(item) for item in raw.get("warnings") or []],
        committed=False,
    )
