"""Turns an uploaded purchase file into a header row plus data rows of plain strings.

CSV is sniffed for its delimiter and encoding, spreadsheets are read with calamine (first non-empty sheet), and
PDF invoices are read table-first with pdfplumber, falling back to column-aligned text lines. The header row is
the first row near the top that looks like labels rather than data, so title blocks above the table are skipped."""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from app.core.errors import ApiError

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ROWS = 5000
HEADER_SCAN_ROWS = 25
SOURCES = {".csv": "CSV", ".txt": "CSV", ".xlsx": "EXCEL", ".xlsm": "EXCEL", ".xls": "EXCEL", ".pdf": "PDF_INVOICE"}

# Lower-cased, alphanumeric-only header spellings for each system field.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "name": ("productname", "name", "product", "item", "itemname", "description", "itemdescription", "title"),
    "code": ("sku", "barcode", "skubarcode", "code", "itemcode", "productcode", "ean", "upc", "partnumber", "partno"),
    "quantity": ("quantity", "qty", "units", "pcs", "count", "qtyordered", "qtyreceived", "orderqty"),
    "cost": (
        "purchasecost",
        "cost",
        "unitcost",
        "costprice",
        "purchaseprice",
        "buyprice",
        "rate",
        "unitprice",
        "price",
        "purchasecostaed",
        "costaed",
    ),
    "price": ("sellingprice", "retailprice", "saleprice", "sellprice", "mrp", "rrp", "sellingpriceaed", "retail"),
    "model_number": ("modelnumber", "model", "modelno", "mpn"),
    "category": ("category", "department", "group", "productcategory"),
    "sub_category": ("subcategory", "subcat", "subgroup"),
    "serials": ("imei", "imeis", "serial", "serials", "serialnumber", "serialnumbers", "imeiserial", "imeiserials"),
    "expiry_date": ("expiry", "expirydate", "expdate", "bestbefore", "expires"),
}


@dataclass
class ParsedFile:
    source: str
    headers: list[str]
    rows: list[list[str]]
    warnings: list[str] = field(default_factory=list)


def source_for(file_name: str) -> str:
    suffix = Path(file_name).suffix.lower()
    if suffix not in SOURCES:
        raise ApiError(422, "unsupported_file", "Upload an Excel (.xlsx), CSV or PDF purchase invoice.")
    return SOURCES[suffix]


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        if value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        return f"{value:.6f}".rstrip("0").rstrip(".")
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == time(0) else value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return " ".join(str(value).split())


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ApiError(422, "unreadable_file", "The CSV file is not in a readable text encoding.")


def _read_csv(data: bytes) -> list[list[str]]:
    text = _decode(data)
    sample = text[:20_000]
    try:
        dialect: type[csv.Dialect] | csv.Dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return [[_cell(value) for value in row] for row in csv.reader(io.StringIO(text), dialect)]


def _read_excel(data: bytes) -> list[list[str]]:
    from python_calamine import CalamineWorkbook

    try:
        workbook = CalamineWorkbook.from_filelike(io.BytesIO(data))
    except Exception as exc:  # calamine raises its own error types for every malformed-file case
        raise ApiError(422, "unreadable_file", "The spreadsheet could not be opened. Re-save it as .xlsx.") from exc
    for name in workbook.sheet_names:
        rows = workbook.get_sheet_by_name(name).to_python(skip_empty_area=True)
        cleaned = [[_cell(value) for value in row] for row in rows]
        if any(any(cell for cell in row) for row in cleaned):
            return cleaned
    return []


_COLUMN_GAP = re.compile(r"\s{2,}|\t")


def _read_pdf(data: bytes, warnings: list[str]) -> list[list[str]]:
    import pdfplumber

    tables: list[list[list[str]]] = []
    text_lines: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages[:50]:
                for table in page.extract_tables():
                    rows = [[_cell(value) for value in row] for row in table if row]
                    if rows:
                        tables.append(rows)
                text_lines.extend((page.extract_text(layout=True) or "").splitlines())
    except Exception as exc:  # pdfminer raises a wide set of parser errors for damaged files
        raise ApiError(422, "unreadable_file", "The PDF could not be read. Export the invoice again.") from exc
    if tables:
        width = max(len(rows[0]) for rows in tables)
        merged: list[list[str]] = []
        for rows in tables:
            if max(len(row) for row in rows) == width:
                merged.extend(rows)
        return merged
    warnings.append("No ruled table was found in the PDF, so columns were split on spacing. Check the preview.")
    rows = [[part.strip() for part in _COLUMN_GAP.split(line.strip())] for line in text_lines if line.strip()]
    return [row for row in rows if len(row) >= 3]


def _looks_numeric(value: str) -> bool:
    return re.fullmatch(r"[-+]?[\d.,\s]+%?|[A-Z]{3}\s?[\d.,]+", value.strip()) is not None


def _header_index(rows: list[list[str]]) -> int:
    widest = max((sum(1 for cell in row if cell) for row in rows[:HEADER_SCAN_ROWS]), default=0)
    for index, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        filled = [cell for cell in row if cell]
        if len(filled) < max(2, (widest + 1) // 2):
            continue
        if sum(1 for cell in filled if not _looks_numeric(cell)) >= len(filled) * 0.6:
            return index
    return 0


def _unique_headers(raw: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    headers: list[str] = []
    for position, value in enumerate(raw, start=1):
        label = value.strip() or f"Column {position}"
        count = seen.get(label.lower(), 0)
        seen[label.lower()] = count + 1
        headers.append(label if count == 0 else f"{label} ({count + 1})")
    return headers


def parse(file_name: str, data: bytes) -> ParsedFile:
    if not data:
        raise ApiError(422, "empty_file", "The uploaded file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise ApiError(413, "file_too_large", "Purchase files are limited to 10 MB.")
    source = source_for(file_name)
    warnings: list[str] = []
    if source == "CSV":
        rows = _read_csv(data)
    elif source == "EXCEL":
        rows = _read_excel(data)
    else:
        rows = _read_pdf(data, warnings)
    rows = [row for row in rows if any(cell for cell in row)]
    if len(rows) < 2:
        raise ApiError(422, "no_rows", "No product rows were found. The file needs a header row and at least one line.")
    start = _header_index(rows)
    header_row = rows[start]
    width = max(len(row) for row in rows[start:])
    headers = _unique_headers(header_row + [""] * (width - len(header_row)))
    header_key = [cell.strip().lower() for cell in header_row]
    body: list[list[str]] = []
    for row in rows[start + 1 :]:
        if [cell.strip().lower() for cell in row[: len(header_key)]] == header_key:
            continue  # header repeated on every page of a PDF invoice
        body.append(row + [""] * (width - len(row)))
    if not body:
        raise ApiError(422, "no_rows", "The file has a header row but no product lines under it.")
    if len(body) > MAX_ROWS:
        raise ApiError(422, "too_many_rows", f"Imports are limited to {MAX_ROWS} rows per file. Split the file.")
    if start:
        warnings.append(f"Skipped {start} line(s) above the header row.")
    return ParsedFile(source=source, headers=headers, rows=body, warnings=warnings)


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def suggest_mapping(headers: list[str]) -> dict[str, str]:
    """Best header for each field: exact synonym first, then a header containing a synonym."""
    keys = {header: _key(header) for header in headers}
    taken: set[str] = set()
    mapping: dict[str, str] = {}
    for exact in (True, False):
        for field_name, words in SYNONYMS.items():
            if field_name in mapping:
                continue
            for word in words:
                match = next(
                    (
                        header
                        for header, key in keys.items()
                        if header not in taken and (key == word if exact else len(word) > 3 and word in key)
                    ),
                    None,
                )
                if match is not None:
                    mapping[field_name] = match
                    taken.add(match)
                    break
    return mapping


# --- Value parsing -------------------------------------------------------------------------------


def parse_money(raw: str) -> int | None:
    """'AED 1,234.50', '1.234,50', '58' -> cents. Returns None for blanks, raises ValueError for junk."""
    text = re.sub(r"[^\d,.\-]", "", raw or "")
    if not text:
        return None
    if "," in text and "." in text:
        decimal_mark = "," if text.rfind(",") > text.rfind(".") else "."
        thousands = "." if decimal_mark == "," else ","
        text = text.replace(thousands, "").replace(decimal_mark, ".")
    elif "," in text:
        head, _, tail = text.rpartition(",")
        text = (
            f"{head.replace(',', '')}.{tail}" if text.count(",") == 1 and len(tail) in (1, 2) else text.replace(",", "")
        )
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(raw) from exc
    if amount < 0:
        raise ValueError(raw)
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def parse_quantity(raw: str) -> int | None:
    text = re.sub(r"[^\d.,\-]", "", raw or "").replace(",", "")
    if not text:
        return None
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(raw) from exc
    if amount < 0 or amount != amount.to_integral_value():
        raise ValueError(raw)
    return int(amount)


def parse_date(raw: str) -> date | None:
    text = (raw or "").strip()
    if not text:
        return None
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%m/%Y", "%Y-%m-%d %H:%M:%S", "%d %b %Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    raise ValueError(raw)


def parse_serials(raw: str) -> list[str]:
    return [part for part in re.split(r"[\s,;|/]+", raw or "") if part]
