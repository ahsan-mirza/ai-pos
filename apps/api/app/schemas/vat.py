from datetime import date
from uuid import UUID

from app.schemas.payloads import ApiModel


class VatEmirateRow(ApiModel):
    emirate: str | None
    label: str
    amount_cents: int
    vat_cents: int
    adjustment_cents: int


class VatBox(ApiModel):
    key: str
    label: str
    amount_cents: int
    vat_cents: int


class VatReport(ApiModel):
    period_from: date
    period_to: date
    store_id: UUID | None
    currency: str
    trn: str | None
    legal_name: str | None
    vat_registered: bool
    emirates: list[VatEmirateRow]
    boxes: list[VatBox]
    output_vat_cents: int
    input_vat_cents: int
    net_vat_cents: int
    input_vat_estimated: bool
    invoices: int
    full_invoices: int
    simplified_invoices: int
    credit_notes: int
