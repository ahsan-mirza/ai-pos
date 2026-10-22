"""Bank statement files: CSV exports in the shapes UAE banks produce, and SWIFT MT940."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.core.errors import ApiError

MAX_STATEMENT_BYTES = 5 * 1024 * 1024
DATE_FORMATS = (
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y-%m-%d",
    "%d.%m.%Y",
    "%d/%m/%y",
    "%Y/%m/%d",
    "%d %b %Y",
    "%d-%b-%Y",
    "%d-%b-%y",
    "%d %B %Y",
)
DATE_HEADERS = ("value date", "transaction date", "posting date", "txn date", "booking date", "date")
DESCRIPTION_HEADERS = ("description", "narrative", "narration", "details", "particulars", "remarks", "transaction")
REFERENCE_HEADERS = ("reference", "ref", "cheque", "chq")
AMOUNT_HEADERS = ("amount",)
DEBIT_HEADERS = ("debit", "withdrawal", "dr", "money out", "paid out")
CREDIT_HEADERS = ("credit", "deposit", "cr", "money in", "paid in")
BALANCE_HEADERS = ("balance", "running balance")
MT940_61 = re.compile(r"^(\d{6})(\d{4})?(R?[CD])([A-Z])?(\d+,\d{0,2})([NSF][A-Z0-9]{3})?([^/]*)(?://(.*))?")


@dataclass
class ParsedLine:
    booked_on: date
    description: str
    reference: str
    amount_cents: int
    balance_cents: int | None = None


def _decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1256", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ApiError(422, "unreadable_statement", "The statement file could not be read as text.")


def parse_amount(raw: str) -> int | None:
    text = raw.strip().upper().replace("AED", "").replace(" ", "").replace("\u00a0", "")
    if not text:
        return None
    sign = 1
    if text.startswith("(") and text.endswith(")"):
        sign, text = -1, text[1:-1]
    for suffix, factor in (("CR", 1), ("DR", -1)):
        if text.endswith(suffix):
            sign, text = sign * factor, text[: -len(suffix)]
    if text.endswith("-"):
        sign, text = -sign, text[:-1]
    if text.count(",") == 1 and "." not in text and len(text.split(",")[1]) in (1, 2):
        text = text.replace(",", ".")
    text = text.replace(",", "")
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return sign * int((value * 100).quantize(Decimal("1")))


def parse_date(raw: str) -> date | None:
    text = raw.strip().split("T")[0]
    text = text.split(" ")[0] if re.match(r"^\d", text) and ":" in text else text
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _column(header: list[str], names: tuple[str, ...]) -> int | None:
    for name in names:
        for index, cell in enumerate(header):
            if cell == name:
                return index
    for name in names:
        for index, cell in enumerate(header):
            if len(name) > 3 and name in cell:
                return index
    return None


def parse_csv(text: str) -> list[ParsedLine]:
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    start = -1
    for index, row in enumerate(rows[:25]):
        header = [cell.strip().lower() for cell in row]
        when = _column(header, DATE_HEADERS)
        amount = _column(header, AMOUNT_HEADERS)
        debit, credit = _column(header, DEBIT_HEADERS), _column(header, CREDIT_HEADERS)
        if when is not None and (amount is not None or (debit is not None and credit is not None)):
            start = index
            break
    if start < 0:
        raise ApiError(
            422,
            "unknown_statement_layout",
            "Could not find the header row. The CSV needs a date column and either an amount column or "
            "debit and credit columns.",
        )
    description = _column(header, DESCRIPTION_HEADERS)
    reference = _column(header, REFERENCE_HEADERS)
    balance = _column(header, BALANCE_HEADERS)

    def cell(row: list[str], index: int | None) -> str:
        return row[index].strip() if index is not None and index < len(row) else ""

    lines: list[ParsedLine] = []
    for row in rows[start + 1 :]:
        booked = parse_date(cell(row, when))
        if booked is None:
            continue
        if debit is None or credit is None:
            cents = parse_amount(cell(row, amount))
        else:
            paid_in, paid_out = parse_amount(cell(row, credit)), parse_amount(cell(row, debit))
            if paid_in is None and paid_out is None:
                cents = None
            else:
                cents = abs(paid_in or 0) - abs(paid_out or 0)
        if not cents:
            continue
        lines.append(
            ParsedLine(
                booked_on=booked,
                description=cell(row, description)[:255],
                reference=cell(row, reference)[:80],
                amount_cents=cents,
                balance_cents=parse_amount(cell(row, balance)),
            )
        )
    return lines


def _mt940_fields(text: str) -> list[tuple[str, str]]:
    fields: list[tuple[str, str]] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        match = re.match(r"^:(\d{2}[A-Z]?):(.*)$", line)
        if match:
            fields.append((match.group(1), match.group(2)))
        elif fields and line and line != "-" and not line.startswith(("{", "}")):
            tag, value = fields[-1]
            fields[-1] = (tag, f"{value}\n{line}")
    return fields


def parse_mt940(text: str) -> list[ParsedLine]:
    lines: list[ParsedLine] = []
    for tag, value in _mt940_fields(text):
        if tag == "61":
            match = MT940_61.match(value.split("\n")[0])
            if match is None:
                continue
            booked = datetime.strptime(match.group(1), "%y%m%d").date()
            cents = parse_amount(match.group(5)) or 0
            if match.group(3).endswith("D"):
                cents = -cents
            if match.group(3).startswith("R"):
                cents = -cents
            extra = value.split("\n", 1)[1].strip() if "\n" in value else ""
            reference = (match.group(7) or "").strip()
            if reference.upper() == "NONREF":
                reference = ""
            lines.append(
                ParsedLine(
                    booked_on=booked,
                    description=extra[:255],
                    reference=(reference or (match.group(8) or "").strip())[:80],
                    amount_cents=cents,
                )
            )
        elif tag == "86" and lines:
            detail = " ".join(part.strip() for part in value.split("\n") if part.strip())
            last = lines[-1]
            last.description = (f"{last.description} {detail}".strip() if last.description else detail)[:255]
        elif tag in ("62F", "62M") and lines:
            match = re.match(r"^([CD])\d{6}[A-Z]{3}(\d+,\d{0,2})", value)
            if match:
                balance = parse_amount(match.group(2)) or 0
                lines[-1].balance_cents = balance if match.group(1) == "C" else -balance
    return lines


def parse(content: bytes, file_name: str) -> tuple[str, list[ParsedLine]]:
    if len(content) > MAX_STATEMENT_BYTES:
        raise ApiError(413, "file_too_large", "Statement files are limited to 5 MB.")
    text = _decode(content)
    lowered = file_name.lower()
    if lowered.endswith((".sta", ".mt940", ".940")) or (":61:" in text and ":20:" in text):
        file_format, lines = "MT940", parse_mt940(text)
    else:
        file_format, lines = "CSV", parse_csv(text)
    if not lines:
        raise ApiError(422, "empty_statement", "The statement has no transactions we could read.")
    return file_format, lines


def line_hashes(lines: list[ParsedLine]) -> list[str]:
    """Stable per-line fingerprints: re-importing the same (or an overlapping) statement skips lines already in."""
    seen: Counter[str] = Counter()
    hashes = []
    for line in lines:
        base = f"{line.booked_on}|{line.amount_cents}|{line.description}|{line.reference}|{line.balance_cents}"
        seen[base] += 1
        hashes.append(hashlib.sha256(f"{base}|{seen[base]}".encode()).hexdigest())
    return hashes
