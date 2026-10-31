"""Plugin tests on a disposable SQLite database. They do not touch the AxizPOS development database."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

os.environ["EINVOICING_CREDENTIAL_KEY"] = Fernet.generate_key().decode()

from einvoicing.engine import (  # noqa: E402
    SourceDocument,
    SourceLine,
    TransitionError,
    classify,
    money,
    payload_hash,
    provider_for,
    sign_body,
    transition,
    trn_error,
    webhook_fresh,
)
from einvoicing.main import health  # noqa: E402
from einvoicing.models import Base, Invoice, WebhookEvent  # noqa: E402
from einvoicing.service import (  # noqa: E402
    accept_webhook,
    create_credit_note_from_return,
    create_invoice,
    dashboard,
    list_invoices,
    load_sale,
    manual_retry,
    process_outbox,
    seal_webhook_secret,
    submit_invoice,
    connect_provider,
)

TENANT_A = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
TENANT_B = uuid.UUID("00000000-0000-4000-8000-0000000000b2")
SELLER_TRN = "100000000000003"
BUYER_TRN = "200000000000003"


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE sales (id TEXT PRIMARY KEY, tenant_id TEXT, store_id TEXT, customer_id TEXT, invoice_number TEXT, currency TEXT, subtotal_cents INT, tax_cents INT, total_cents INT, created_at TEXT)"))
        connection.execute(text("CREATE TABLE sale_items (id TEXT PRIMARY KEY, tenant_id TEXT, sale_id TEXT, description TEXT, quantity INT, line_total_cents INT, tax_cents INT, tax_rate_bps INT)"))
        connection.execute(text("CREATE TABLE customers (id TEXT PRIMARY KEY, trn_vat_number TEXT, name TEXT, company_name TEXT)"))
        connection.execute(text("CREATE TABLE stores (id TEXT PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE returns (id TEXT PRIMARY KEY, tenant_id TEXT, original_sale_id TEXT, store_id TEXT, currency TEXT, subtotal_cents INT, tax_refund_cents INT, total_refund_cents INT, credit_note_number TEXT)"))
        connection.execute(text("CREATE TABLE business_settings (legal_name TEXT, trn TEXT)"))
        connection.execute(text("INSERT INTO business_settings (legal_name, trn) VALUES ('Baristo LLC', :trn)"), {"trn": SELLER_TRN})
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


def source(tenant: uuid.UUID = TENANT_A, buyer: str = "Cafe Buyer", trn: str | None = BUYER_TRN, kind: str = "B2B") -> SourceDocument:
    return SourceDocument(
        tenant_id=tenant,
        sale_id=uuid.uuid4(),
        store_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        number="INV-1",
        currency="AED",
        issue_date="2026-10-31",
        seller_name="Baristo LLC",
        seller_trn=SELLER_TRN,
        buyer_name=buyer,
        buyer_trn=trn,
        kind=kind,
        net_cents=10_000,
        tax_cents=500,
        total_cents=10_500,
        lines=(SourceLine("Burger", 2, 10_000, 500, 500),),
    )


def test_health_is_ok() -> None:
    assert health()["status"] == "ok"


def test_classification_keeps_consumers_off_the_einvoice_path() -> None:
    assert classify(None, None, []) == "B2C"
    assert classify(BUYER_TRN, uuid.uuid4(), []) == "B2B"
    customer = uuid.uuid4()
    assert classify(None, customer, [str(customer)]) == "B2G"
    assert classify("123", None, []) == "B2B"


def test_trn_must_be_fifteen_digits() -> None:
    assert trn_error("123") is not None
    assert trn_error(BUYER_TRN) is None


def test_money_keeps_fils_without_a_second_rounding_pass() -> None:
    assert money(10_500) == "105.00"
    assert money(1) == "0.01"


def test_hash_changes_only_when_the_document_changes() -> None:
    left = source()
    from einvoicing.engine import canonical

    assert payload_hash(canonical(left)) == payload_hash(canonical(left))
    other = source()
    assert payload_hash(canonical(left)) != payload_hash(canonical(other))


def test_mock_is_the_only_provider_and_it_is_named_as_a_mock() -> None:
    result = provider_for("mock").test_connection()
    assert result.provider_status == "MOCK_CONNECTED"
    assert "not an accredited ASP" in result.detail
    with pytest.raises(KeyError):
        provider_for("invented-asp")


def test_valid_invoice_is_accepted_by_the_mock_and_a_repeat_does_not_duplicate(db: Session) -> None:
    invoice = create_invoice(db, source())
    submit_invoice(db, invoice)
    assert invoice.status == "ACCEPTED"
    assert invoice.provider_status == "MOCK_ACCEPTED"
    again = create_invoice(db, source())
    assert again.id != invoice.id
    same = create_invoice(
        db,
        SourceDocument(**{**source().__dict__, "sale_id": invoice.source_sale_id, "tenant_id": invoice.tenant_id}),
    )
    assert same.id == invoice.id
    assert db.query(Invoice).count() == 2


def test_rejection_is_stored_and_can_be_retried_only_from_an_allowed_state(db: Session) -> None:
    invoice = create_invoice(db, source(buyer="REJECT"))
    submit_invoice(db, invoice)
    assert invoice.status == "REJECTED"
    assert invoice.provider_status == "MOCK_REJECTED"
    with pytest.raises(TransitionError):
        transition("ACCEPTED", "REJECTED")
    manual_retry(db, invoice.tenant_id, invoice.id)
    assert invoice.status == "REJECTED"
    with pytest.raises(LookupError):
        manual_retry(db, TENANT_B, invoice.id)


def test_tenants_cannot_read_each_others_invoices(db: Session) -> None:
    create_invoice(db, source(TENANT_A))
    create_invoice(db, source(TENANT_B))
    assert len(list_invoices(db, TENANT_A)) == 1
    assert len(list_invoices(db, TENANT_B)) == 1
    assert dashboard(db, TENANT_A)["eligible"] == 1


def test_missing_buyer_trn_fails_validation_and_is_not_submitted(db: Session) -> None:
    invoice = create_invoice(db, source(trn="12"))
    assert invoice.status == "VALIDATION_FAILED"
    submit_invoice(db, invoice)
    assert invoice.provider_reference == ""


def test_line_totals_must_match_the_posted_sale(db: Session) -> None:
    broken = source()
    broken = SourceDocument(**{**broken.__dict__, "tax_cents": 1})
    invoice = create_invoice(db, broken)
    assert invoice.status == "VALIDATION_FAILED"


def test_b2c_sale_is_not_loaded_for_submission(db: Session) -> None:
    sale_id = uuid.uuid4()
    customer_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO sales (id, tenant_id, store_id, customer_id, invoice_number, currency, subtotal_cents, tax_cents, total_cents, created_at) VALUES (:id, :tenant, :store, :customer, 'INV-9', 'AED', 1000, 50, 1050, '2026-10-31')"
        ),
        {"id": str(sale_id), "tenant": str(TENANT_A), "store": str(uuid.uuid4()), "customer": str(customer_id)},
    )
    db.execute(
        text("INSERT INTO customers (id, trn_vat_number, name, company_name) VALUES (:id, NULL, 'Walk in', NULL)"),
        {"id": str(customer_id)},
    )
    db.commit()
    assert load_sale(db, TENANT_A, sale_id) is None


def test_outbox_processes_a_business_sale_once(db: Session) -> None:
    from einvoicing.models import Outbox

    sale_id = uuid.uuid4()
    customer_id = uuid.uuid4()
    store_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO sales (id, tenant_id, store_id, customer_id, invoice_number, currency, subtotal_cents, tax_cents, total_cents, created_at) VALUES (:id, :tenant, :store, :customer, 'INV-2', 'AED', 10000, 500, 10500, '2026-10-31')"
        ),
        {"id": str(sale_id), "tenant": str(TENANT_A), "store": str(store_id), "customer": str(customer_id)},
    )
    db.execute(
        text("INSERT INTO customers (id, trn_vat_number, name, company_name) VALUES (:id, :trn, 'Buyer', 'Buyer LLC')"),
        {"id": str(customer_id), "trn": BUYER_TRN},
    )
    db.execute(
        text(
            "INSERT INTO sale_items (id, tenant_id, sale_id, description, quantity, line_total_cents, tax_cents, tax_rate_bps) VALUES (:id, :tenant, :sale, 'Burger', 2, 10500, 500, 500)"
        ),
        {"id": str(uuid.uuid4()), "tenant": str(TENANT_A), "sale": str(sale_id)},
    )
    db.add(Outbox(tenant_id=TENANT_A, kind="sale", source_id=sale_id, status="PENDING"))
    db.flush()
    assert process_outbox(db) == 1
    assert process_outbox(db) == 0
    rows = list_invoices(db, TENANT_A)
    assert rows[0]["status"] == "ACCEPTED"
    assert rows[0]["provider_status"] == "MOCK_ACCEPTED"


def test_credit_note_uses_the_refund_amounts_and_is_not_duplicated(db: Session) -> None:
    invoice = create_invoice(db, source())
    submit_invoice(db, invoice)
    return_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO returns (id, tenant_id, original_sale_id, store_id, currency, subtotal_cents, tax_refund_cents, total_refund_cents, credit_note_number) VALUES (:id, :tenant, :sale, :store, 'AED', 5000, 250, 5250, 'CN-1')"
        ),
        {"id": str(return_id), "tenant": str(TENANT_A), "sale": str(invoice.source_sale_id), "store": str(uuid.uuid4())},
    )
    db.commit()
    note = create_credit_note_from_return(db, TENANT_A, return_id)
    assert note is not None
    assert note.tax_cents == 250
    assert note.payload["original_invoice"] == "INV-1"
    assert note.provider_status == "MOCK_ACCEPTED"
    again = create_credit_note_from_return(db, TENANT_A, return_id)
    assert again is not None and again.id == note.id


def test_refund_without_an_einvoice_does_not_create_a_credit_note(db: Session) -> None:
    return_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO returns (id, tenant_id, original_sale_id, store_id, currency, subtotal_cents, tax_refund_cents, total_refund_cents, credit_note_number) VALUES (:id, :tenant, :sale, :store, 'AED', 100, 5, 105, 'CN-2')"
        ),
        {"id": str(return_id), "tenant": str(TENANT_A), "sale": str(uuid.uuid4()), "store": str(uuid.uuid4())},
    )
    db.commit()
    assert create_credit_note_from_return(db, TENANT_A, return_id) is None


def test_webhook_rejects_a_bad_signature_a_stale_stamp_and_a_replay(db: Session) -> None:
    seal_webhook_secret(db, TENANT_A, "participant-1", "secret")
    db.commit()
    body = b"{}"
    stamp = datetime.now(UTC).isoformat()
    signature = sign_body("secret", body, stamp)
    ok = accept_webhook(
        db,
        provider_code="mock",
        body=body,
        signature=signature,
        timestamp=stamp,
        event_id="evt-1",
        participant_id="participant-1",
        claimed_tenant=None,
    )
    assert ok["accepted"] is True
    replay = accept_webhook(
        db,
        provider_code="mock",
        body=body,
        signature=signature,
        timestamp=stamp,
        event_id="evt-1",
        participant_id="participant-1",
        claimed_tenant=None,
    )
    assert replay["duplicate"] is True
    bad = accept_webhook(
        db,
        provider_code="mock",
        body=body,
        signature="nope",
        timestamp=stamp,
        event_id="evt-2",
        participant_id="participant-1",
        claimed_tenant=None,
    )
    assert bad["reason"] == "bad_signature"
    stale = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    assert webhook_fresh(stale) is False
    mismatch = accept_webhook(
        db,
        provider_code="mock",
        body=body,
        signature=sign_body("secret", body, stamp),
        timestamp=stamp,
        event_id="evt-3",
        participant_id="participant-1",
        claimed_tenant=str(TENANT_B),
    )
    assert mismatch["reason"] == "tenant_mismatch"
    assert db.query(WebhookEvent).count() == 1


def test_provider_test_does_not_echo_a_secret(db: Session) -> None:
    seal_webhook_secret(db, TENANT_A, "participant-1", "super-secret")
    result = connect_provider(db, TENANT_A, "mock")
    assert "super-secret" not in str(result)
    unsupported = connect_provider(db, TENANT_A, "not-a-real-asp")
    assert unsupported["ok"] is False


def test_timeouts_stop_after_the_attempt_cap(db: Session) -> None:
    invoice = create_invoice(db, source(buyer="TIMEOUT"))
    submit_invoice(db, invoice)
    assert invoice.status == "RETRY_PENDING"
    for _ in range(4):
        manual_retry(db, invoice.tenant_id, invoice.id)
    assert invoice.status == "PROCESSING_ERROR"
