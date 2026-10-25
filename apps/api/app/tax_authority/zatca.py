"""Saudi ZATCA e-invoicing (Fatoora, phase 2), core pieces:

- UBL 2.1 invoice and credit-note XML,
- the invoice hash (SHA-256 of the canonical XML without the signature, UBL extensions and QR),
- the per-business invoice chain: counter (ICV) and previous invoice hash (PIH),
- an ECDSA secp256k1 signature over the canonical XML,
- the TLV QR code (tags 1-9) printed on the invoice.

Onboarding with ZATCA (CSR, compliance CSID, production CSID) and live clearance/reporting are not wired up yet:
until then credentials are self-signed and submission runs in simulation mode, validating locally and recording
the result. The XAdES signature block is a simplified form; validate output with the ZATCA SDK before going live."""

import base64
import hashlib
import re
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import decrypt_value, encrypt_value
from app.models.einvoice import EInvoice, EInvoiceChain, TaxAuthorityCredential
from app.tax_authority.base import InvoiceDocument, InvoiceKind

AUTHORITY = "zatca"
# PIH of the first invoice in a chain: base64 of the hex SHA-256 of "0", as ZATCA specifies.
INITIAL_PREVIOUS_HASH = base64.b64encode(hashlib.sha256(b"0").hexdigest().encode()).decode()
SUBMISSION_MODE = "simulation"

NS = {
    "": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    "sig": "urn:oasis:names:specification:ubl:schema:xsd:CommonSignatureComponents-2",
    "sac": "urn:oasis:names:specification:ubl:schema:xsd:SignatureAggregateComponents-2",
    "sbc": "urn:oasis:names:specification:ubl:schema:xsd:SignatureBasicComponents-2",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
}
for _prefix, _uri in NS.items():
    ET.register_namespace(_prefix, _uri)

PAYMENT_MEANS = {
    "cash": "10",
    "card": "48",
    "transfer": "30",
    "cheque": "20",
    "on_account": "1",
    "qr": "48",
    "bnpl": "30",
}
VAT_NUMBER = re.compile(r"^3\d{13}3$")


def _q(tag: str) -> str:
    prefix, _, name = tag.rpartition(":")
    return f"{{{NS[prefix]}}}{name}"


def _el(parent: ET.Element, tag: str, text: str | None = None, **attrs: str) -> ET.Element:
    element = ET.SubElement(parent, _q(tag), attrs)
    if text is not None:
        element.text = text
    return element


def amount(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


# --- QR -----------------------------------------------------------------------------------------------------------


def tlv(fields: list[tuple[int, bytes]]) -> bytes:
    """ZATCA TLV: one byte tag, one byte length, then the value."""
    out = bytearray()
    for tag, value in fields:
        if len(value) > 255:
            raise ValueError(f"QR tag {tag} is longer than 255 bytes.")
        out += bytes((tag, len(value))) + value
    return bytes(out)


def qr_payload(
    *,
    seller_name: str,
    vat_number: str,
    timestamp: str,
    total: str,
    vat_total: str,
    invoice_hash: str | None = None,
    signature: str | None = None,
    public_key: bytes | None = None,
    certificate_signature: bytes | None = None,
) -> str:
    """Base64 TLV. Tags 1-5 identify the invoice; 6-9 (phase 2) carry the hash, signature and key."""
    fields = [(1, seller_name), (2, vat_number), (3, timestamp), (4, total), (5, vat_total)]
    encoded: list[tuple[int, bytes]] = [(tag, value.encode()) for tag, value in fields]
    if invoice_hash is not None:
        encoded.append((6, invoice_hash.encode()))
    if signature is not None:
        encoded.append((7, signature.encode()))
    if public_key is not None:
        encoded.append((8, public_key))
    if certificate_signature is not None:
        encoded.append((9, certificate_signature))
    return base64.b64encode(tlv(encoded)).decode()


def read_qr(payload: str) -> dict[int, bytes]:
    raw = base64.b64decode(payload)
    fields: dict[int, bytes] = {}
    index = 0
    while index < len(raw):
        tag, length = raw[index], raw[index + 1]
        fields[tag] = raw[index + 2 : index + 2 + length]
        index += 2 + length
    return fields


# --- Credentials --------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Credentials:
    private_key: ec.EllipticCurvePrivateKey
    certificate: x509.Certificate
    environment: str

    @property
    def public_key_der(self) -> bytes:
        return self.certificate.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )


def credentials(db: Session, settings: Settings, *, seller_name: str, vat_number: str) -> Credentials:
    """The business's signing key, created on first use with a self-signed simulation certificate."""
    row = db.scalar(select(TaxAuthorityCredential).where(TaxAuthorityCredential.authority == AUTHORITY))
    if row is None:
        key = ec.generate_private_key(ec.SECP256K1())
        subject = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "SA"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, seller_name[:64] or "Business"),
                x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, vat_number[:10] or "simulation"),
                x509.NameAttribute(NameOID.COMMON_NAME, f"AI POS EGS {vat_number or 'simulation'}"),
            ]
        )
        now = datetime.now(UTC)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=365 * 5))
            .sign(key, hashes.SHA256())
        )
        pem = key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ).decode()
        row = TaxAuthorityCredential(
            authority=AUTHORITY,
            environment=SUBMISSION_MODE,
            private_key_encrypted=encrypt_value(pem, settings),
            certificate_pem=certificate.public_bytes(serialization.Encoding.PEM).decode(),
        )
        db.add(row)
        db.flush()
    key = serialization.load_pem_private_key(decrypt_value(row.private_key_encrypted, settings).encode(), None)
    assert isinstance(key, ec.EllipticCurvePrivateKey)
    certificate = x509.load_pem_x509_certificate(row.certificate_pem.encode())
    return Credentials(private_key=key, certificate=certificate, environment=row.environment)


def verify_signature(certificate_pem: str, canonical: bytes, signature_b64: str) -> bool:
    public_key = x509.load_pem_x509_certificate(certificate_pem.encode()).public_key()
    assert isinstance(public_key, ec.EllipticCurvePublicKey)
    try:
        public_key.verify(base64.b64decode(signature_b64), canonical, ec.ECDSA(hashes.SHA256()))
    except Exception:
        return False
    return True


# --- XML ----------------------------------------------------------------------------------------------------------


def _party(parent: ET.Element, tag: str, name: str, vat: str | None, address: str | None, city: str | None) -> None:
    party = _el(_el(parent, tag), "cac:Party")
    postal = _el(party, "cac:PostalAddress")
    _el(postal, "cbc:StreetName", (address or "-")[:127])
    _el(postal, "cbc:CityName", (city or "-")[:127])
    _el(_el(postal, "cac:Country"), "cbc:IdentificationCode", "SA")
    if vat:
        scheme = _el(party, "cac:PartyTaxScheme")
        _el(scheme, "cbc:CompanyID", vat)
        _el(_el(scheme, "cac:TaxScheme"), "cbc:ID", "VAT")
    _el(_el(party, "cac:PartyLegalEntity"), "cbc:RegistrationName", name[:1000])


def _tax_category(parent: ET.Element, rate_bps: int) -> None:
    category = _el(parent, "cac:TaxCategory" if parent.tag.endswith("TaxSubtotal") else "cac:ClassifiedTaxCategory")
    _el(category, "cbc:ID", "S" if rate_bps > 0 else "Z")
    _el(category, "cbc:Percent", f"{Decimal(rate_bps) / 100:.2f}")
    if rate_bps == 0:
        _el(category, "cbc:TaxExemptionReasonCode", "VATEX-SA-32")
        _el(category, "cbc:TaxExemptionReason", "Export of goods")
    _el(_el(category, "cac:TaxScheme"), "cbc:ID", "VAT")


@dataclass(frozen=True)
class BuiltInvoice:
    root: ET.Element
    canonical: bytes
    invoice_hash: str


def build(
    document: InvoiceDocument, *, kind: InvoiceKind, document_uuid: uuid.UUID, counter: int, previous_hash: str
) -> BuiltInvoice:
    """The invoice without signature, UBL extensions or QR, which is exactly what the hash covers."""
    currency = document.currency
    root = ET.Element(_q(":Invoice"))
    _el(root, "cbc:ProfileID", "reporting:1.0")
    _el(root, "cbc:ID", document.number)
    _el(root, "cbc:UUID", str(document_uuid))
    issued = document.issued_at.astimezone(UTC)
    _el(root, "cbc:IssueDate", f"{issued:%Y-%m-%d}")
    _el(root, "cbc:IssueTime", f"{issued:%H:%M:%S}")
    _el(
        root,
        "cbc:InvoiceTypeCode",
        "381" if document.document_type == "credit_note" else "388",
        name="0100000" if kind == "FULL" else "0200000",
    )
    _el(root, "cbc:DocumentCurrencyCode", currency)
    _el(root, "cbc:TaxCurrencyCode", currency)
    if document.reference_number:
        reference = _el(root, "cac:BillingReference")
        _el(_el(reference, "cac:InvoiceDocumentReference"), "cbc:ID", document.reference_number)
    icv = _el(root, "cac:AdditionalDocumentReference")
    _el(icv, "cbc:ID", "ICV")
    _el(icv, "cbc:UUID", str(counter))
    pih = _el(root, "cac:AdditionalDocumentReference")
    _el(pih, "cbc:ID", "PIH")
    _el(_el(pih, "cac:Attachment"), "cbc:EmbeddedDocumentBinaryObject", previous_hash, mimeCode="text/plain")

    seller = document.seller
    _party(root, "cac:AccountingSupplierParty", seller.name, seller.vat_number, seller.address, seller.city)
    buyer = document.buyer
    if buyer is not None:
        _party(root, "cac:AccountingCustomerParty", buyer.name, buyer.vat_number, buyer.address, buyer.city)
    else:
        _el(root, "cac:AccountingCustomerParty")
    if kind == "FULL":
        _el(_el(root, "cac:Delivery"), "cbc:ActualDeliveryDate", f"{issued:%Y-%m-%d}")
    for method in document.payment_means or ("cash",):
        means = _el(root, "cac:PaymentMeans")
        _el(means, "cbc:PaymentMeansCode", PAYMENT_MEANS.get(method, "1"))
        if document.document_type == "credit_note":
            _el(means, "cbc:InstructionNote", (document.reason or "Goods returned")[:1000])

    _el(_el(root, "cac:TaxTotal"), "cbc:TaxAmount", amount(document.tax_cents), currencyID=currency)
    totals = _el(root, "cac:TaxTotal")
    _el(totals, "cbc:TaxAmount", amount(document.tax_cents), currencyID=currency)
    by_rate: dict[int, tuple[int, int]] = {}
    for line in document.lines:
        net, tax = by_rate.get(line.rate_bps, (0, 0))
        by_rate[line.rate_bps] = (net + line.total_cents - line.tax_cents, tax + line.tax_cents)
    for rate_bps, (net, tax) in sorted(by_rate.items()):
        subtotal = _el(totals, "cac:TaxSubtotal")
        _el(subtotal, "cbc:TaxableAmount", amount(net), currencyID=currency)
        _el(subtotal, "cbc:TaxAmount", amount(tax), currencyID=currency)
        _tax_category(subtotal, rate_bps)

    money = _el(root, "cac:LegalMonetaryTotal")
    _el(money, "cbc:LineExtensionAmount", amount(document.subtotal_cents), currencyID=currency)
    _el(money, "cbc:TaxExclusiveAmount", amount(document.subtotal_cents), currencyID=currency)
    _el(money, "cbc:TaxInclusiveAmount", amount(document.total_cents), currencyID=currency)
    _el(money, "cbc:PayableAmount", amount(document.total_cents), currencyID=currency)

    for position, line in enumerate(document.lines, start=1):
        net = line.total_cents - line.tax_cents
        row = _el(root, "cac:InvoiceLine")
        _el(row, "cbc:ID", str(position))
        _el(row, "cbc:InvoicedQuantity", str(line.quantity), unitCode="PCE")
        _el(row, "cbc:LineExtensionAmount", amount(net), currencyID=currency)
        line_tax = _el(row, "cac:TaxTotal")
        _el(line_tax, "cbc:TaxAmount", amount(line.tax_cents), currencyID=currency)
        _el(line_tax, "cbc:RoundingAmount", amount(line.total_cents), currencyID=currency)
        item = _el(row, "cac:Item")
        _el(item, "cbc:Name", line.name[:1000])
        _tax_category(item, line.rate_bps)
        unit = Decimal(net) / Decimal(100 * max(line.quantity, 1))
        _el(_el(row, "cac:Price"), "cbc:PriceAmount", f"{unit:.6f}".rstrip("0").rstrip("."), currencyID=currency)

    canonical = ET.canonicalize(ET.tostring(root, encoding="unicode")).encode()
    invoice_hash = base64.b64encode(hashlib.sha256(canonical).digest()).decode()
    return BuiltInvoice(root=root, canonical=canonical, invoice_hash=invoice_hash)


def _attach_signature(built: BuiltInvoice, *, signature: str, certificate: x509.Certificate, qr: str) -> str:
    """Adds the UBL signature extension, the QR reference and the cac:Signature marker, which the hash excludes."""
    root = built.root
    certificate_b64 = base64.b64encode(certificate.public_bytes(serialization.Encoding.DER)).decode()
    extensions = ET.Element(_q("ext:UBLExtensions"))
    extension = _el(extensions, "ext:UBLExtension")
    _el(extension, "ext:ExtensionURI", "urn:oasis:names:specification:ubl:dsig:enveloped:xades")
    signatures = _el(_el(extension, "ext:ExtensionContent"), "sig:UBLDocumentSignatures")
    information = _el(signatures, "sac:SignatureInformation")
    _el(information, "cbc:ID", "urn:oasis:names:specification:ubl:signature:1")
    _el(information, "sbc:ReferencedSignatureID", "urn:oasis:names:specification:ubl:signature:Invoice")
    ds = _el(information, "ds:Signature", Id="signature")
    signed_info = _el(ds, "ds:SignedInfo")
    _el(signed_info, "ds:CanonicalizationMethod", Algorithm="http://www.w3.org/2006/12/xml-c14n11")
    _el(signed_info, "ds:SignatureMethod", Algorithm="http://www.w3.org/2001/04/xmldsig-more#ecdsa-sha256")
    reference = _el(signed_info, "ds:Reference", Id="invoiceSignedData", URI="")
    _el(reference, "ds:DigestMethod", Algorithm="http://www.w3.org/2001/04/xmlenc#sha256")
    _el(reference, "ds:DigestValue", built.invoice_hash)
    _el(ds, "ds:SignatureValue", signature)
    _el(_el(_el(ds, "ds:KeyInfo"), "ds:X509Data"), "ds:X509Certificate", certificate_b64)
    root.insert(0, extensions)

    position = next(
        index
        for index, child in enumerate(root)
        if child.tag == _q("cac:AdditionalDocumentReference") and child.findtext(_q("cbc:ID")) == "PIH"
    )
    qr_reference = ET.Element(_q("cac:AdditionalDocumentReference"))
    _el(qr_reference, "cbc:ID", "QR")
    _el(_el(qr_reference, "cac:Attachment"), "cbc:EmbeddedDocumentBinaryObject", qr, mimeCode="text/plain")
    marker = ET.Element(_q("cac:Signature"))
    _el(marker, "cbc:ID", "urn:oasis:names:specification:ubl:signature:Invoice")
    _el(marker, "cbc:SignatureMethod", "urn:oasis:names:specification:ubl:dsig:enveloped:xades")
    root.insert(position + 1, qr_reference)
    root.insert(position + 2, marker)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


def hashable_xml(xml: str) -> bytes:
    """Strips what the hash excludes from a signed invoice and canonicalises the rest, for verification."""
    root = ET.fromstring(xml)
    for child in list(root):
        excluded = child.tag in (_q("ext:UBLExtensions"), _q("cac:Signature")) or (
            child.tag == _q("cac:AdditionalDocumentReference") and child.findtext(_q("cbc:ID")) == "QR"
        )
        if excluded:
            root.remove(child)
    return ET.canonicalize(ET.tostring(root, encoding="unicode")).encode()


# --- Validation and submission ------------------------------------------------------------------------------------


def validate(document: InvoiceDocument, kind: InvoiceKind) -> list[str]:
    """The checks ZATCA rejects most often, run locally so problems surface before going live."""
    errors: list[str] = []
    if not document.seller.vat_number or not VAT_NUMBER.match(document.seller.vat_number):
        errors.append("Seller VAT number must be 15 digits starting and ending with 3.")
    if kind == "FULL":
        if document.buyer is None or not document.buyer.vat_number:
            errors.append("A standard tax invoice needs the buyer's VAT number.")
        elif not VAT_NUMBER.match(document.buyer.vat_number):
            errors.append("Buyer VAT number must be 15 digits starting and ending with 3.")
    if document.document_type == "credit_note" and not document.reference_number:
        errors.append("A credit note must reference the original invoice.")
    if sum(line.tax_cents for line in document.lines) != document.tax_cents:
        errors.append("Line VAT does not add up to the invoice VAT total.")
    return errors


def _chain_head(db: Session) -> EInvoiceChain:
    statement = select(EInvoiceChain).where(EInvoiceChain.authority == AUTHORITY)
    if db.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    head = db.scalar(statement)
    if head is None:
        head = EInvoiceChain(authority=AUTHORITY, last_counter=0, last_hash=INITIAL_PREVIOUS_HASH)
        db.add(head)
        db.flush()
    return head


class ZatcaAdapter:
    code = AUTHORITY
    name = "ZATCA (Saudi Arabia)"
    country = "SA"
    issues_einvoices = True

    def invoice_kind(self, total_cents: int, buyer_vat_number: str | None) -> InvoiceKind:
        """Standard (B2B) tax invoice when the buyer is VAT-registered, simplified (B2C) otherwise."""
        return "FULL" if buyer_vat_number else "SIMPLIFIED"

    def issue(self, db: Session, settings: Settings, document: InvoiceDocument) -> EInvoice:
        buyer_vat = document.buyer.vat_number if document.buyer is not None else None
        kind = self.invoice_kind(document.total_cents, buyer_vat)
        head = _chain_head(db)
        counter = head.last_counter + 1
        document_uuid = uuid.uuid4()
        built = build(document, kind=kind, document_uuid=document_uuid, counter=counter, previous_hash=head.last_hash)
        seller_vat = document.seller.vat_number or ""
        keys = credentials(db, settings, seller_name=document.seller.name, vat_number=seller_vat)
        signature = base64.b64encode(keys.private_key.sign(built.canonical, ec.ECDSA(hashes.SHA256()))).decode()
        issued = document.issued_at.astimezone(UTC)
        qr = qr_payload(
            seller_name=document.seller.name,
            vat_number=seller_vat,
            timestamp=f"{issued:%Y-%m-%dT%H:%M:%SZ}",
            total=amount(document.total_cents),
            vat_total=amount(document.tax_cents),
            invoice_hash=built.invoice_hash,
            signature=signature,
            public_key=keys.public_key_der,
            certificate_signature=keys.certificate.signature if kind == "SIMPLIFIED" else None,
        )
        xml = _attach_signature(built, signature=signature, certificate=keys.certificate, qr=qr)
        errors = validate(document, kind)
        record = EInvoice(
            authority=AUTHORITY,
            source_type="sale" if document.document_type == "invoice" else "return",
            source_id=document.source_id,
            number=document.number,
            kind="STANDARD" if kind == "FULL" else "SIMPLIFIED",
            document_uuid=document_uuid,
            counter=counter,
            invoice_hash=built.invoice_hash,
            previous_hash=head.last_hash,
            qr=qr,
            xml=xml,
            status="REJECTED" if errors else ("CLEARED" if kind == "FULL" else "REPORTED"),
            submission_mode=keys.environment,
            submitted_at=datetime.now(UTC),
            response={
                "mode": keys.environment,
                "errors": errors,
                "note": "Validated locally; not sent to ZATCA until onboarding is complete.",
            },
        )
        db.add(record)
        head.last_counter = counter
        head.last_hash = built.invoice_hash
        db.flush()
        return record
