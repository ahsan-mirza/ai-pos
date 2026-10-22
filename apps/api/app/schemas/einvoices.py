import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

EInvoiceStatus = Literal["PENDING", "REPORTED", "CLEARED", "REJECTED"]


class EInvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    authority: str
    source_type: Literal["sale", "return"]
    source_id: uuid.UUID
    number: str
    kind: str
    counter: int
    invoice_hash: str
    previous_hash: str
    qr: str
    status: EInvoiceStatus
    submission_mode: str
    submitted_at: datetime | None
    created_at: datetime
    errors: list[str] = []


class EInvoiceList(BaseModel):
    items: list[EInvoiceOut]
    total: int


class AuthorityOption(BaseModel):
    code: str
    name: str
    country: str
    issues_einvoices: bool


class EInvoiceSummary(BaseModel):
    authority: str
    authority_name: str
    issues_einvoices: bool
    options: list[AuthorityOption]
    #: "simulation" until the business is onboarded with the authority; None before the first invoice.
    environment: str | None
    certificate_subject: str | None
    certificate_expires_at: datetime | None
    last_counter: int
    last_hash: str | None
    counts: dict[str, int]
