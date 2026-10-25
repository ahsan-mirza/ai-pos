import base64
import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BusinessSettings, EInvoice, TaxAuthorityCredential
from app.tax_authority import ADAPTERS
from app.tax_authority.zatca import INITIAL_PREVIOUS_HASH, hashable_xml, qr_payload, read_qr, verify_signature
from test_returns import (
    CABLE_ID,
    admin_id,
    admin_token,
    approval,
    bearer,
    push,
    receipt,
    record_sale,
    return_payload,
    seed_catalog,
)

SAUDI_VAT = "300000000000003"


def use_zatca(client, token: str, trn: str = SAUDI_VAT) -> None:
    body = {
        "vat_registered": True,
        "trn": trn,
        "legal_name": "Riyadh Mobiles",
        "legal_name_ar": None,
        "prices_include_vat": False,
        "standard_rate_bps": 500,
        "tax_authority": "zatca",
    }
    response = client.put("/api/v1/settings/tax", headers=bearer(token), json=body)
    assert response.status_code == 200, response.text
    assert response.json()["tax_authority"] == "zatca"


def einvoices(session: Session) -> list[EInvoice]:
    return list(session.scalars(select(EInvoice).order_by(EInvoice.counter)))


def test_qr_matches_zatcas_published_example() -> None:
    payload = qr_payload(
        seller_name="Bobs Records",
        vat_number="310122393500003",
        timestamp="2022-04-25T15:30:00Z",
        total="1000.00",
        vat_total="150.00",
    )
    assert payload == "AQxCb2JzIFJlY29yZHMCDzMxMDEyMjM5MzUwMDAwMwMUMjAyMi0wNC0yNVQxNTozMDowMFoEBzEwMDAuMDAFBjE1MC4wMA=="
    assert read_qr(payload)[1] == b"Bobs Records"


def test_fta_rules_are_unchanged() -> None:
    fta = ADAPTERS["fta"]
    assert fta.invoice_kind(1_000_000, None) == "SIMPLIFIED"
    assert fta.invoice_kind(1_000_001, None) == "FULL"
    assert fta.invoice_kind(100, "100000000000003") == "FULL"
    assert ADAPTERS["zatca"].invoice_kind(5_000_000, None) == "SIMPLIFIED"


def test_fta_businesses_issue_no_einvoices(client, session: Session) -> None:
    seed_catalog(client)
    record_sale(client, product_id=CABLE_ID, price=1500)
    assert einvoices(session) == []
    summary = client.get("/api/v1/einvoices/summary", headers=bearer(admin_token(client))).json()
    assert summary["authority"] == "fta" and summary["issues_einvoices"] is False


def test_zatca_sales_are_signed_chained_and_reported(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    use_zatca(client, token)
    record_sale(client, product_id=CABLE_ID, price=1500)
    record_sale(client, product_id=CABLE_ID, price=1500, quantity=2)

    first, second = einvoices(session)
    assert (first.counter, second.counter) == (1, 2)
    assert first.previous_hash == INITIAL_PREVIOUS_HASH
    assert second.previous_hash == first.invoice_hash
    assert (first.kind, first.status, first.submission_mode) == ("SIMPLIFIED", "REPORTED", "simulation")

    canonical = hashable_xml(first.xml)
    assert base64.b64encode(hashlib.sha256(canonical).digest()).decode() == first.invoice_hash
    tags = read_qr(first.qr)
    assert tags[1] == b"Riyadh Mobiles" and tags[2] == SAUDI_VAT.encode()
    assert tags[4] == b"15.75" and tags[5] == b"0.75"
    assert tags[6].decode() == first.invoice_hash
    assert 9 in tags, "simplified invoices carry the certificate signature"
    summary = client.get("/api/v1/einvoices/summary", headers=bearer(token)).json()
    assert summary["environment"] == "simulation" and summary["last_counter"] == 2
    credential = session.scalar(select(TaxAuthorityCredential).where(TaxAuthorityCredential.authority == "zatca"))
    assert verify_signature(credential.certificate_pem, canonical, tags[7].decode())
    assert not verify_signature(credential.certificate_pem, canonical + b" ", tags[7].decode())
    assert '<cbc:InvoiceTypeCode name="0200000">388</cbc:InvoiceTypeCode>' in first.xml


def test_local_validation_rejects_bad_vat_numbers_without_blocking_the_sale(client, session: Session) -> None:
    seed_catalog(client)
    use_zatca(client, admin_token(client), trn="312345678900003")
    record_sale(client, product_id=CABLE_ID, price=1500)
    [record] = einvoices(session)
    assert record.status == "REPORTED"

    # A UAE-style TRN left over from before the switch: the sale still syncs, the e-invoice is flagged.
    session.scalar(select(BusinessSettings)).trn = "100000000000003"
    session.commit()
    record_sale(client, product_id=CABLE_ID, price=1500)
    rejected = einvoices(session)[-1]
    assert rejected.status == "REJECTED"
    assert "Seller VAT number" in rejected.response["errors"][0]


def test_credit_notes_reference_the_invoice_and_join_the_chain(client, session: Session) -> None:
    seed_catalog(client)
    use_zatca(client, admin_token(client))
    sale = record_sale(client, product_id=CABLE_ID, price=1500)
    body = receipt(client, sale["client_sale_id"])
    response = push(client, "sale_return", return_payload(body, override=approval(admin_id(client))))
    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["status"] == "applied", response.text

    invoice, credit = einvoices(session)
    assert credit.source_type == "return" and credit.counter == 2
    assert credit.previous_hash == invoice.invoice_hash
    assert ">381</cbc:InvoiceTypeCode>" in credit.xml
    assert f"<cbc:ID>{invoice.number}</cbc:ID>" in credit.xml


def test_invoice_pdf_prints_the_qr_and_endpoints_serve_the_xml(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    use_zatca(client, token)
    sale = record_sale(client, product_id=CABLE_ID, price=1500)
    pdf = client.get(f"/api/v1/sales/{sale['id']}/invoice.pdf", headers=bearer(token))
    assert pdf.status_code == 200, pdf.text
    assert b"/Subtype /Image" in pdf.content

    listing = client.get("/api/v1/einvoices", headers=bearer(token)).json()
    assert listing["total"] == 1 and listing["items"][0]["status"] == "REPORTED"
    xml = client.get(f"/api/v1/einvoices/{listing['items'][0]['id']}/xml", headers=bearer(token))
    assert xml.status_code == 200 and xml.headers["content-type"].startswith("application/xml")
    assert "ICV" in xml.text and "PIH" in xml.text and "ds:SignatureValue" in xml.text


def test_saudi_vat_numbers_are_checked_when_switching(client) -> None:
    token = admin_token(client)
    body = {
        "vat_registered": True,
        "trn": "100000000000003",
        "legal_name": None,
        "legal_name_ar": None,
        "prices_include_vat": False,
        "standard_rate_bps": 1500,
        "tax_authority": "zatca",
    }
    assert client.put("/api/v1/settings/tax", headers=bearer(token), json=body).status_code == 422
