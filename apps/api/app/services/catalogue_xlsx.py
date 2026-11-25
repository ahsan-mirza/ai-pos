"""Versioned .xlsx workbook for the product and menu catalogue.

Cells are plain values. The reader rejects macros, formula tags, and any file that is not a zip workbook.
"""

from __future__ import annotations

import io
import re
import zipfile
from xml.sax.saxutils import escape

from app.core.errors import ApiError

FORMAT_VERSION = "1"
TEMPLATE_NAME = "AxizPOS_Product_Menu_Import_Template.xlsx"
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ROWS = 2000

SHEET_GUIDE = "Guide"
SHEET_PRODUCTS = "Products"
SHEET_MENU = "Menu Items"
SHEET_OPTIONS = "Menu Pricing Options"
SHEET_MODIFIERS = "Modifiers"
SHEET_META = "_AxizPOS"

PRODUCT_COLUMNS = (
    "Product ID",
    "Product Name",
    "SKU",
    "Barcode",
    "Product Type",
    "Category",
    "Sub-category",
    "Brand",
    "Unit",
    "Base Price",
    "Cost Price",
    "Currency",
    "Tax Category",
    "Price Includes Tax",
    "Active",
    "Model Number",
    "Open Price",
    "Sold By Weight",
    "PLU",
    "Tare Grams",
    "Minimum Age",
    "Ingredient",
    "Serialized",
    "Season",
    "Collection",
    "Gender",
    "Material",
    "Fit",
    "Care",
)
MENU_COLUMNS = (
    "Product ID",
    "Menu Item Name",
    "SKU",
    "Barcode",
    "Category",
    "Sub-category",
    "Base Price",
    "Currency",
    "Tax Category",
    "Price Includes Tax",
    "Prepared Without Recipe",
    "Active",
    "Open Price",
)
OPTION_COLUMNS = (
    "Option ID",
    "Product ID",
    "Product Name",
    "Option Name",
    "Price",
    "Currency",
    "SKU",
    "Active",
    "Position",
)
MODIFIER_COLUMNS = (
    "Product ID",
    "Product Name",
    "Group ID",
    "Group Name",
    "Min Select",
    "Max Select",
    "Group Active",
    "Option ID",
    "Option Name",
    "Price Adjustment",
    "Default",
    "Option Active",
)

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_FORMULA = re.compile(br"<f[\s/>]")
_ILLEGAL = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")


def money(cents: int | None) -> str:
    if cents is None:
        return ""
    sign = "-" if cents < 0 else ""
    amount = abs(int(cents))
    return f"{sign}{amount // 100}.{amount % 100:02d}"


def yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def _column(index: int) -> str:
    number = index + 1
    letters = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _text(value: object) -> str:
    return _ILLEGAL.sub("", str(value))


def _sheet_xml(rows: list[list[object]]) -> bytes:
    body: list[str] = []
    for row_number, row in enumerate(rows, start=1):
        cells: list[str] = []
        for column, value in enumerate(row):
            if value is None or value == "":
                continue
            ref = f"{_column(column)}{row_number}"
            if isinstance(value, bool):
                shown = yes_no(value)
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(shown)}</t></is></c>')
            elif isinstance(value, int):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                cells.append(
                    f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{escape(_text(value))}</t></is></c>'
                )
        body.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{NS}"><sheetData>{"".join(body)}</sheetData></worksheet>'
    )
    return xml.encode("utf-8")


def write_workbook(sheets: list[tuple[str, list[list[object]]]], *, hidden: set[str] | None = None) -> bytes:
    """Write a macro-free workbook. `hidden` sheet names are not shown in Excel."""
    hidden = hidden or set()
    buffer = io.BytesIO()
    overrides = [
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
    ]
    workbook_sheets: list[str] = []
    relationships: list[str] = [
        '<Relationship Id="rIdStyles" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
    ]
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, (name, rows) in enumerate(sheets, start=1):
            target = f"xl/worksheets/sheet{index}.xml"
            archive.writestr(target, _sheet_xml(rows))
            overrides.append(
                f'<Override PartName="/{target}" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            )
            state = ' state="hidden"' if name in hidden else ""
            workbook_sheets.append(f'<sheet name="{escape(name)}" sheetId="{index}"{state} r:id="rId{index}"/>')
            relationships.append(
                f'<Relationship Id="rId{index}" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                f'Target="worksheets/sheet{index}.xml"/>'
            )
        archive.writestr(
            "[Content_Types].xml",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                + "".join(overrides)
                + "</Types>"
            ).encode(),
        )
        archive.writestr(
            "_rels/.rels",
            (
                b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                b'<Relationship Id="rId1" '
                b'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                b'Target="xl/workbook.xml"/>'
                b"</Relationships>"
            ),
        )
        archive.writestr(
            "xl/workbook.xml",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                f"<sheets>{''.join(workbook_sheets)}</sheets></workbook>"
            ).encode(),
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                + "".join(relationships)
                + "</Relationships>"
            ).encode(),
        )
        archive.writestr(
            "xl/styles.xml",
            (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<styleSheet xmlns="{NS}"><fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
                '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
                '<borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs>'
                '<cellXfs count="1"><xf/></cellXfs></styleSheet>'
            ).encode(),
        )
    return buffer.getvalue()


def assert_plain_xlsx(data: bytes, file_name: str) -> None:
    if not file_name.lower().endswith(".xlsx"):
        raise ApiError(422, "unsupported_file", "Upload an Excel workbook (.xlsx).")
    if len(data) > MAX_FILE_BYTES:
        raise ApiError(422, "file_too_large", "The workbook is larger than 10 MB.")
    if not data.startswith(b"PK"):
        raise ApiError(422, "unsupported_file", "This file is not an Excel workbook.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ApiError(422, "unreadable_file", "The spreadsheet could not be opened. Re-save it as .xlsx.") from exc
    names = [name.replace("\\", "/") for name in archive.namelist()]
    lowered = [name.lower() for name in names]
    if any("vbaproject" in name or name.endswith(".bin") for name in lowered):
        raise ApiError(422, "unsupported_file", "Macros are not allowed. Save the workbook as a plain .xlsx file.")
    if any(name.startswith("xl/externallinks/") for name in lowered):
        raise ApiError(422, "unsupported_file", "Workbooks that link to other files are not allowed.")
    for name in names:
        if not name.startswith("xl/worksheets/") or not name.endswith(".xml"):
            continue
        if _FORMULA.search(archive.read(name)):
            raise ApiError(422, "unsupported_file",
                "Formulas are not allowed. Paste values, then upload the workbook again.")
    archive.close()


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return yes_no(value)
    if isinstance(value, float):
        if value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        return format(value, "f").rstrip("0").rstrip(".")
    if isinstance(value, int):
        return str(value)
    return " ".join(str(value).split())


def read_workbook(data: bytes, file_name: str) -> dict[str, list[list[str]]]:
    assert_plain_xlsx(data, file_name)
    from python_calamine import CalamineWorkbook

    try:
        workbook = CalamineWorkbook.from_filelike(io.BytesIO(data))
    except Exception as exc:
        raise ApiError(422, "unreadable_file", "The spreadsheet could not be opened. Re-save it as .xlsx.") from exc
    sheets: dict[str, list[list[str]]] = {}
    for name in workbook.sheet_names:
        rows = workbook.get_sheet_by_name(name).to_python(skip_empty_area=False)
        sheets[name] = [[_cell(value) for value in row] for row in rows]
        if len(sheets[name]) > MAX_ROWS + 1:
            raise ApiError(422, "too_many_rows", f"{name} has more than {MAX_ROWS} data rows.")
    return sheets
