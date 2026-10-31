"""Invoice register, outbox worker, and credit notes. Tenant id is always the trusted argument."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from einvoicing.engine import (
    MAX_ATTEMPTS,
    MockAsp,
    SourceDocument,
    SourceLine,
    TransitionError,
    canonical,
    classify,
    money,
    payload_hash,
    provider_for,
    sign_body,
    transition,
    validate_snapshot,
    webhook_fresh,
)
from einvoicing.models import (
    AuditLog,
    CreditNote,
    EInvoicingSetting,
    Invoice,
    InvoiceLine,
    Outbox,
    ProviderAccount,
    Submission,
    SubmissionAttempt,
    WebhookEvent,
    utcnow,
)


def _audit(db: Session, tenant_id: uuid.UUID, action: str, subject: str, detail: str = "") -> None:
    db.add(AuditLog(tenant_id=tenant_id, action=action, subject_id=subject[:64], detail=detail[:500]))


def settings_row(db: Session, tenant_id: uuid.UUID) -> EInvoicingSetting:
    row = db.get(EInvoicingSetting, tenant_id)
    if row is None:
        row = EInvoicingSetting(tenant_id=tenant_id, government_customer_ids=[])
        db.add(row)
        db.flush()
    return row


def public_settings(row: EInvoicingSetting) -> dict:
    return {
        "revenue_band": row.revenue_band,
        "voluntary": row.voluntary,
        "b2b_enabled": row.b2b_enabled,
        "b2g_enabled": row.b2g_enabled,
        "government_customer_ids": list(row.government_customer_ids or []),
        "environment": row.environment,
    }


def update_settings(db: Session, tenant_id: uuid.UUID, payload: dict) -> dict:
    row = settings_row(db, tenant_id)
    band = str(payload.get("revenue_band") or "unknown")
    if band not in {"unknown", "at_least_50m", "below_50m", "government"}:
        raise ValueError("Unknown revenue band.")
    environment = str(payload.get("environment") or "sandbox")
    if environment not in {"sandbox", "production"}:
        raise ValueError("Environment must be sandbox or production.")
    row.revenue_band = band
    row.voluntary = bool(payload.get("voluntary"))
    row.b2b_enabled = bool(payload.get("b2b_enabled", True))
    row.b2g_enabled = bool(payload.get("b2g_enabled", True))
    row.environment = environment
    row.government_customer_ids = [str(item) for item in payload.get("government_customer_ids") or []]
    row.updated_at = utcnow()
    _audit(db, tenant_id, "settings_updated", str(tenant_id))
    db.flush()
    return public_settings(row)


def connect_provider(db: Session, tenant_id: uuid.UUID, provider_code: str) -> dict:
    try:
        adapter = provider_for(provider_code)
    except KeyError:
        _audit(db, tenant_id, "provider_rejected", provider_code, "Unsupported provider.")
        return {"ok": False, "provider_status": "UNSUPPORTED", "detail": "No accredited adapter is configured for this code."}
    result = adapter.test_connection()
    account = db.scalar(
        select(ProviderAccount).where(ProviderAccount.tenant_id == tenant_id, ProviderAccount.provider_code == provider_code)
    )
    if account is None:
        account = ProviderAccount(tenant_id=tenant_id, provider_code=provider_code, environment="sandbox")
        db.add(account)
    account.connection_status = "connected" if result.outcome == "ok" else "failed"
    account.updated_at = utcnow()
    db.flush()
    return {"ok": result.outcome == "ok", "provider_status": result.provider_status, "detail": result.detail}


def _lines(db: Session, invoice: Invoice, source: SourceDocument) -> None:
    for index, line in enumerate(source.lines, start=1):
        db.add(
            InvoiceLine(
                tenant_id=invoice.tenant_id,
                invoice_id=invoice.id,
                line_no=index,
                description=line.description[:200],
                quantity=line.quantity,
                net_cents=line.net_cents,
                tax_cents=line.tax_cents,
                tax_rate_bps=line.tax_rate_bps,
            )
        )


def create_invoice(db: Session, source: SourceDocument) -> Invoice:
    existing = db.scalar(
        select(Invoice).where(Invoice.tenant_id == source.tenant_id, Invoice.source_sale_id == source.sale_id)
    )
    if existing is not None:
        return existing
    document = canonical(source)
    digest = payload_hash(document)
    problem = validate_snapshot(source)
    status = "VALIDATION_FAILED" if problem else "QUEUED"
    invoice = Invoice(
        tenant_id=source.tenant_id,
        store_id=source.store_id,
        source_sale_id=source.sale_id,
        customer_id=source.customer_id,
        document_number=source.number,
        document_kind=source.kind,
        profile_version=document["profile"],
        issue_date=source.issue_date,
        currency=source.currency,
        status=status,
        payload=document,
        payload_hash=digest,
        error_detail=(problem or "")[:500],
    )
    db.add(invoice)
    db.flush()
    _lines(db, invoice, source)
    if status == "QUEUED":
        db.add(
            Submission(
                tenant_id=source.tenant_id,
                invoice_id=invoice.id,
                idempotency_key=f"sale:{source.sale_id}",
                status="QUEUED",
            )
        )
    _audit(db, source.tenant_id, "invoice_created", str(invoice.id), status)
    db.flush()
    return invoice


def _apply_result(db: Session, invoice: Invoice, submission: Submission, attempt_no: int) -> None:
    adapter = MockAsp()
    result = adapter.submit(invoice.payload)
    invoice.provider_code = adapter.code
    invoice.provider_status = result.provider_status
    if result.outcome == "accepted":
        invoice.status = transition(invoice.status, "SUBMISSION_IN_PROGRESS")
        invoice.status = transition(invoice.status, "SUBMITTED")
        invoice.status = transition(invoice.status, "ACCEPTED")
        invoice.provider_reference = result.reference
        invoice.error_detail = ""
        submission.status = "ACCEPTED"
    elif result.outcome == "rejected":
        invoice.status = transition(invoice.status, "SUBMISSION_IN_PROGRESS")
        invoice.status = transition(invoice.status, "SUBMITTED")
        invoice.status = transition(invoice.status, "REJECTED")
        invoice.error_detail = result.detail
        submission.status = "REJECTED"
    else:
        invoice.error_detail = result.detail
        if attempt_no >= MAX_ATTEMPTS:
            invoice.status = transition(invoice.status, "SUBMISSION_IN_PROGRESS")
            invoice.status = transition(invoice.status, "PROCESSING_ERROR")
            submission.status = "DEAD"
        else:
            invoice.status = transition(invoice.status, "SUBMISSION_IN_PROGRESS")
            invoice.status = transition(invoice.status, "RETRY_PENDING")
            submission.status = "RETRY_PENDING"
    db.add(
        SubmissionAttempt(
            tenant_id=invoice.tenant_id,
            submission_id=submission.id,
            attempt_no=attempt_no,
            outcome=result.outcome,
            provider_status=result.provider_status,
            detail=result.detail,
        )
    )
    invoice.updated_at = utcnow()


def submit_invoice(db: Session, invoice: Invoice) -> Invoice:
    if invoice.status == "ACCEPTED":
        return invoice
    if invoice.status == "VALIDATION_FAILED":
        return invoice
    if invoice.status not in {"QUEUED", "RETRY_PENDING", "REJECTED"}:
        raise TransitionError(f"{invoice.status} is not waiting for submission")
    if invoice.status == "REJECTED":
        invoice.status = transition(invoice.status, "RETRY_PENDING")
    submission = db.scalar(select(Submission).where(Submission.invoice_id == invoice.id, Submission.tenant_id == invoice.tenant_id))
    if submission is None:
        submission = Submission(
            tenant_id=invoice.tenant_id,
            invoice_id=invoice.id,
            idempotency_key=f"sale:{invoice.source_sale_id}",
            status="QUEUED",
        )
        db.add(submission)
        db.flush()
    attempt_no = int(
        db.scalar(select(func.count()).select_from(SubmissionAttempt).where(SubmissionAttempt.submission_id == submission.id)) or 0
    ) + 1
    if invoice.status == "RETRY_PENDING":
        _apply_from_retry(db, invoice, submission, attempt_no)
    elif invoice.status == "QUEUED":
        _apply_result(db, invoice, submission, attempt_no)
    else:
        raise TransitionError(invoice.status)
    db.flush()
    return invoice


def _apply_from_retry(db: Session, invoice: Invoice, submission: Submission, attempt_no: int) -> None:
    """RETRY_PENDING is allowed to enter SUBMISSION_IN_PROGRESS directly."""
    adapter = MockAsp()
    result = adapter.submit(invoice.payload)
    invoice.provider_code = adapter.code
    invoice.provider_status = result.provider_status
    invoice.status = transition(invoice.status, "SUBMISSION_IN_PROGRESS")
    if result.outcome == "accepted":
        invoice.status = transition(invoice.status, "SUBMITTED")
        invoice.status = transition(invoice.status, "ACCEPTED")
        invoice.provider_reference = result.reference
        invoice.error_detail = ""
        submission.status = "ACCEPTED"
    elif result.outcome == "rejected":
        invoice.status = transition(invoice.status, "SUBMITTED")
        invoice.status = transition(invoice.status, "REJECTED")
        invoice.error_detail = result.detail
        submission.status = "REJECTED"
    elif attempt_no >= MAX_ATTEMPTS:
        invoice.status = transition(invoice.status, "PROCESSING_ERROR")
        invoice.error_detail = result.detail
        submission.status = "DEAD"
    else:
        invoice.status = transition(invoice.status, "RETRY_PENDING")
        invoice.error_detail = result.detail
        submission.status = "RETRY_PENDING"
    db.add(
        SubmissionAttempt(
            tenant_id=invoice.tenant_id,
            submission_id=submission.id,
            attempt_no=attempt_no,
            outcome=result.outcome,
            provider_status=result.provider_status,
            detail=result.detail,
        )
    )
    invoice.updated_at = utcnow()


def load_sale(db: Session, tenant_id: uuid.UUID, sale_id: uuid.UUID) -> SourceDocument | None:
    header = db.execute(
        text(
            """
            SELECT s.id, s.tenant_id, s.store_id, s.customer_id, s.invoice_number, s.currency,
                   s.subtotal_cents, s.tax_cents, s.total_cents, s.created_at,
                       c.trn_vat_number, c.name, c.company_name
            FROM sales s
            LEFT JOIN customers c ON c.id = s.customer_id
            WHERE s.id = :sale_id AND s.tenant_id = :tenant_id
            """
        ),
        {"sale_id": str(sale_id), "tenant_id": str(tenant_id)},
    ).mappings().first()
    if header is None:
        return None
    seller = db.execute(
        text("SELECT legal_name, trn FROM business_settings LIMIT 1")
    ).mappings().first()
    items = db.execute(
        text(
            """
            SELECT description, quantity, line_total_cents, tax_cents, tax_rate_bps
            FROM sale_items WHERE sale_id = :sale_id AND tenant_id = :tenant_id ORDER BY id
            """
        ),
        {"sale_id": str(sale_id), "tenant_id": str(tenant_id)},
    ).mappings().all()
    def as_uuid(value: object) -> uuid.UUID | None:
        if value is None or isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))

    settings = settings_row(db, tenant_id)
    customer_id = as_uuid(header["customer_id"])
    kind = classify(header["trn_vat_number"], customer_id, list(settings.government_customer_ids or []))
    if kind == "B2C" or (kind == "B2B" and not settings.b2b_enabled) or (kind == "B2G" and not settings.b2g_enabled):
        return None
    created = header["created_at"]
    issue = created.date().isoformat() if hasattr(created, "date") else str(created)[:10]
    lines = tuple(
        SourceLine(
            description=row["description"] or "Item",
            quantity=int(row["quantity"] or 1),
            net_cents=int(row["line_total_cents"]) - int(row["tax_cents"]),
            tax_cents=int(row["tax_cents"]),
            tax_rate_bps=int(row["tax_rate_bps"] or 0),
        )
        for row in items
    )
    return SourceDocument(
        tenant_id=tenant_id,
        sale_id=sale_id,
        store_id=as_uuid(header["store_id"]),
        customer_id=customer_id,
        number=header["invoice_number"] or "",
        currency=header["currency"] or "AED",
        issue_date=issue,
        seller_name=(seller["legal_name"] if seller else "") or "",
        seller_trn=(seller["trn"] if seller else None),
        buyer_name=(header["company_name"] or header["name"] or ""),
        buyer_trn=header["trn_vat_number"],
        kind=kind,
        net_cents=int(header["subtotal_cents"]),
        tax_cents=int(header["tax_cents"]),
        total_cents=int(header["total_cents"]),
        lines=lines,
    )


def process_outbox(db: Session, *, limit: int = 20) -> int:
    rows = db.scalars(select(Outbox).where(Outbox.status == "PENDING").order_by(Outbox.created_at).limit(limit)).all()
    done = 0
    for row in rows:
        row.attempts += 1
        row.updated_at = utcnow()
        try:
            if row.kind == "sale":
                source = load_sale(db, row.tenant_id, row.source_id)
                if source is None:
                    row.status = "SKIPPED"
                    _audit(db, row.tenant_id, "sale_skipped", str(row.source_id), "Outside e-invoice scope.")
                else:
                    invoice = create_invoice(db, source)
                    if invoice.status == "QUEUED":
                        submit_invoice(db, invoice)
            elif row.kind == "return":
                create_credit_note_from_return(db, row.tenant_id, row.source_id)
            else:
                row.status = "SKIPPED"
                row.last_error = "Unknown outbox kind."
            if row.status == "PENDING":
                row.status = "DONE"
            done += 1
        except Exception as exc:
            row.last_error = str(exc)[:500]
            row.status = "DEAD" if row.attempts >= MAX_ATTEMPTS else "PENDING"
            _audit(db, row.tenant_id, "outbox_error", str(row.id), row.last_error)
    db.flush()
    return done


def create_credit_note_from_return(db: Session, tenant_id: uuid.UUID, return_id: uuid.UUID) -> CreditNote | None:
    existing = db.scalar(select(CreditNote).where(CreditNote.tenant_id == tenant_id, CreditNote.source_return_id == return_id))
    if existing is not None:
        return existing
    record = db.execute(
        text(
            """
            SELECT id, original_sale_id, store_id, currency, subtotal_cents, tax_refund_cents, total_refund_cents, credit_note_number
            FROM returns WHERE id = :return_id AND tenant_id = :tenant_id
            """
        ),
        {"return_id": str(return_id), "tenant_id": str(tenant_id)},
    ).mappings().first()
    if record is None:
        return None
    original_sale = record["original_sale_id"]
    if not isinstance(original_sale, uuid.UUID):
        original_sale = uuid.UUID(str(original_sale))
    invoice = db.scalar(select(Invoice).where(Invoice.tenant_id == tenant_id, Invoice.source_sale_id == original_sale))
    if invoice is None:
        _audit(db, tenant_id, "credit_skipped", str(return_id), "No issued e-invoice for this sale.")
        return None
    document = {
        "profile": invoice.profile_version,
        "document_type": "381",
        "number": record["credit_note_number"] or "",
        "currency": record["currency"],
        "original_invoice": invoice.document_number,
        "original_invoice_id": str(invoice.id),
        "net": money(int(record["subtotal_cents"])),
        "tax": money(int(record["tax_refund_cents"])),
        "total": money(int(record["total_refund_cents"])),
        "source_return_id": str(return_id),
    }
    note = CreditNote(
        tenant_id=tenant_id,
        store_id=uuid.UUID(str(record["store_id"])) if record["store_id"] else None,
        invoice_id=invoice.id,
        source_return_id=return_id,
        document_number=record["credit_note_number"] or "",
        status="QUEUED",
        currency=record["currency"] or "AED",
        net_cents=int(record["subtotal_cents"]),
        tax_cents=int(record["tax_refund_cents"]),
        total_cents=int(record["total_refund_cents"]),
        payload=document,
        payload_hash=payload_hash(document),
    )
    db.add(note)
    db.flush()
    result = MockAsp().submit(document)
    note.provider_status = result.provider_status
    note.provider_reference = result.reference
    note.status = "ACCEPTED" if result.outcome == "accepted" else "REJECTED"
    note.error_detail = "" if result.outcome == "accepted" else result.detail
    note.updated_at = utcnow()
    _audit(db, tenant_id, "credit_note_created", str(note.id), note.status)
    db.flush()
    return note


def manual_retry(db: Session, tenant_id: uuid.UUID, invoice_id: uuid.UUID) -> Invoice:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None or invoice.tenant_id != tenant_id:
        raise LookupError("Invoice was not found.")
    if invoice.status not in {"REJECTED", "RETRY_PENDING", "PROCESSING_ERROR"}:
        raise TransitionError("This invoice is not eligible for a retry.")
    if invoice.status == "PROCESSING_ERROR":
        invoice.status = transition(invoice.status, "RETRY_PENDING")
    return submit_invoice(db, invoice)


def invoice_public(invoice: Invoice) -> dict:
    return {
        "id": str(invoice.id),
        "source_sale_id": str(invoice.source_sale_id),
        "document_number": invoice.document_number,
        "document_kind": invoice.document_kind,
        "issue_date": invoice.issue_date,
        "currency": invoice.currency,
        "status": invoice.status,
        "provider_code": invoice.provider_code,
        "provider_status": invoice.provider_status,
        "provider_reference": invoice.provider_reference,
        "payload_hash": invoice.payload_hash,
        "error_detail": invoice.error_detail,
        "profile_version": invoice.profile_version,
    }


def list_invoices(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    status: str | None = None,
    store_id: uuid.UUID | None = None,
    number: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> list[dict]:
    query = select(Invoice).where(Invoice.tenant_id == tenant_id)
    if status:
        query = query.where(Invoice.status == status)
    if store_id is not None:
        query = query.where(Invoice.store_id == store_id)
    if number:
        query = query.where(Invoice.document_number == number)
    rows = db.scalars(query.order_by(Invoice.created_at.desc()).offset(offset).limit(min(limit, 100))).all()
    return [invoice_public(row) for row in rows]


def dashboard(db: Session, tenant_id: uuid.UUID) -> dict:
    def count(status: str | None = None) -> int:
        query = select(func.count()).select_from(Invoice).where(Invoice.tenant_id == tenant_id)
        if status:
            query = query.where(Invoice.status == status)
        return int(db.scalar(query) or 0)

    credits = int(db.scalar(select(func.count()).select_from(CreditNote).where(CreditNote.tenant_id == tenant_id)) or 0)
    account = db.scalar(select(ProviderAccount).where(ProviderAccount.tenant_id == tenant_id))
    return {
        "eligible": count(),
        "queued": count("QUEUED") + count("RETRY_PENDING") + count("SUBMISSION_IN_PROGRESS"),
        "accepted": count("ACCEPTED"),
        "rejected": count("REJECTED"),
        "validation_failed": count("VALIDATION_FAILED"),
        "credit_notes": credits,
        "provider_connected": bool(account and account.connection_status == "connected"),
        "provider_code": account.provider_code if account else "",
        "mock_only": True,
    }


def accept_webhook(
    db: Session,
    *,
    provider_code: str,
    body: bytes,
    signature: str,
    timestamp: str,
    event_id: str,
    participant_id: str,
    claimed_tenant: str | None,
) -> dict:
    if not webhook_fresh(timestamp):
        return {"accepted": False, "reason": "stale"}
    account = db.scalar(
        select(ProviderAccount).where(
            ProviderAccount.provider_code == provider_code,
            ProviderAccount.participant_id == participant_id,
        )
    )
    if account is None or not account.webhook_secret_ciphertext:
        return {"accepted": False, "reason": "unknown_account"}
    if claimed_tenant and claimed_tenant != str(account.tenant_id):
        _audit(db, account.tenant_id, "webhook_rejected", event_id, "Tenant claim did not match the provider account.")
        return {"accepted": False, "reason": "tenant_mismatch"}
    from einvoicing.crypto import open_secret

    expected = sign_body(open_secret(account.webhook_secret_ciphertext), body, timestamp)
    if not hmac_equal(expected, signature):
        _audit(db, account.tenant_id, "webhook_rejected", event_id, "Signature did not match.")
        return {"accepted": False, "reason": "bad_signature"}
    prior = db.scalar(
        select(WebhookEvent).where(
            WebhookEvent.tenant_id == account.tenant_id,
            WebhookEvent.provider_code == provider_code,
            WebhookEvent.event_id == event_id,
        )
    )
    if prior is not None:
        return {"accepted": True, "duplicate": True}
    db.add(WebhookEvent(tenant_id=account.tenant_id, provider_code=provider_code, event_id=event_id, outcome="stored"))
    _audit(db, account.tenant_id, "webhook_stored", event_id)
    db.flush()
    return {"accepted": True, "duplicate": False}


def hmac_equal(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left, right)


def seal_webhook_secret(db: Session, tenant_id: uuid.UUID, participant_id: str, secret: str) -> None:
    account = db.scalar(select(ProviderAccount).where(ProviderAccount.tenant_id == tenant_id, ProviderAccount.provider_code == "mock"))
    if account is None:
        account = ProviderAccount(tenant_id=tenant_id, provider_code="mock", environment="sandbox")
        db.add(account)
    from einvoicing.crypto import seal

    account.participant_id = participant_id
    account.webhook_secret_ciphertext = seal(secret)
    db.flush()


def issue_date_now() -> str:
    return datetime.now(UTC).date().isoformat()
