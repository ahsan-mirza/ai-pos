"""Marketplace copy stored on the existing billing add-on. Prices stay on the add-on row."""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import capabilities as capability_catalog
from app.schemas.billing import AddonBenefit, AddonFaq, AddonListing, MarketplaceItem, MarketplaceOut
from app.tenancy.models import (
    BillingAddon,
    BillingInvoice,
    BillingInvoiceLine,
    BillingTransfer,
    Subscription,
    SubscriptionItem,
    Tenant,
)

_TAG = re.compile(r"<[^>]*>")
_ICON = re.compile(r"^[a-z0-9-]{1,32}$")
_PUBLICATION = {"published", "draft", "archived"}


def _plain(value: object, limit: int) -> str:
    text = _TAG.sub("", str(value or "")).replace("\x00", "").strip()
    return text[:limit]


def _url(value: object) -> str:
    text = _plain(value, 500)
    if text.startswith("https://") or text.startswith("http://"):
        return text
    return ""


def _pairs(value: object, limit: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not isinstance(value, list):
        return rows
    for item in value[:limit]:
        if not isinstance(item, dict):
            continue
        title = _plain(item.get("title"), 120)
        description = _plain(item.get("description"), 500)
        if title or description:
            rows.append({"title": title, "description": description})
    return rows


def normalize_listing(raw: object, *, customized: bool | None = None) -> dict:
    """Drops markup and keeps only the fields the marketplace renders."""
    source = raw if isinstance(raw, dict) else {}
    publication = str(source.get("publication") or "published")
    if publication not in _PUBLICATION:
        publication = "published"
    icon = _plain(source.get("icon"), 32).lower()
    if not _ICON.fullmatch(icon):
        icon = "puzzle"
    tags = []
    if isinstance(source.get("tags"), list):
        for tag in source["tags"][:20]:
            cleaned = _plain(tag, 40)
            if cleaned and cleaned not in tags:
                tags.append(cleaned)
    requirements = []
    if isinstance(source.get("requirements"), list):
        for item in source["requirements"][:20]:
            cleaned = _plain(item, 200)
            if cleaned:
                requirements.append(cleaned)
    faqs = []
    if isinstance(source.get("faqs"), list):
        for item in source["faqs"][:20]:
            if not isinstance(item, dict):
                continue
            question = _plain(item.get("question"), 200)
            answer = _plain(item.get("answer"), 800)
            if question or answer:
                faqs.append({"question": question, "answer": answer})
    listing = {
        "short_description": _plain(source.get("short_description"), 240),
        "overview": _plain(source.get("overview"), 4000),
        "category": _plain(source.get("category"), 40) or "operations",
        "tags": tags,
        "benefits": _pairs(source.get("benefits"), 12),
        "features": _pairs(source.get("features"), 20),
        "steps": _pairs(source.get("steps"), 8),
        "requirements": requirements,
        "faqs": faqs,
        "documentation_url": _url(source.get("documentation_url")),
        "video_url": _url(source.get("video_url")),
        "support": _plain(source.get("support"), 240),
        "icon": icon,
        "image_url": _url(source.get("image_url")),
        "featured": bool(source.get("featured")),
        "publication": publication,
        "customized": bool(source.get("customized")) if customized is None else customized,
    }
    return listing


def listing_out(raw: object) -> AddonListing:
    data = normalize_listing(raw)
    return AddonListing(
        short_description=data["short_description"],
        overview=data["overview"],
        category=data["category"],
        tags=list(data["tags"]),
        benefits=[AddonBenefit(**row) for row in data["benefits"]],
        features=[AddonBenefit(**row) for row in data["features"]],
        steps=[AddonBenefit(**row) for row in data["steps"]],
        requirements=list(data["requirements"]),
        faqs=[AddonFaq(**row) for row in data["faqs"]],
        documentation_url=data["documentation_url"],
        video_url=data["video_url"],
        support=data["support"],
        icon=data["icon"],
        image_url=data["image_url"],
        featured=data["featured"],
        publication=data["publication"],
    )


def listing_blank(raw: object) -> bool:
    if not isinstance(raw, dict):
        return True
    if raw.get("customized") is True:
        return False
    return not any(raw.get(key) for key in ("short_description", "overview", "benefits", "features"))


def _benefit(title: str, description: str) -> dict[str, str]:
    return {"title": title, "description": description}


# Seed copy for an empty listing. A console save sets customized and is left alone.
_DEFAULTS: dict[str, dict] = {
    "hardware_lease": {
        "short_description": "Rent register hardware instead of buying it outright.",
        "overview": (
            "Register hardware rented to the store. "
            "The one-time amount is a refundable deposit when the catalogue says so."
        ),
        "category": "hardware",
        "icon": "monitor",
        "tags": ["hardware", "lease", "deposit"],
        "benefits": [
            _benefit("Lower upfront cost", "Pay monthly rent for the register hardware."),
            _benefit("Refundable deposit", "The one-time amount follows the refundable flag on this add-on."),
        ],
        "steps": [
            _benefit("Choose the hardware", "The hardware catalogue lists what can be leased."),
            _benefit("Pay the invoice", "The deposit and the rent are lines on the package invoice."),
        ],
    },
    "extra_register": {
        "short_description": "Add a register beyond the ones included in the package.",
        "overview": "An additional POS register. It does not add a new sidebar section.",
        "category": "hardware",
        "icon": "monitor",
        "tags": ["register", "till"],
        "benefits": [_benefit("Another till", "Sell from an extra register once the package allowance is used.")],
    },
    "equipment_protection": {
        "short_description": "Cover leased hardware.",
        "overview": "A monthly cover for leased hardware. It does not add a sidebar section.",
        "category": "hardware",
        "icon": "shield",
        "tags": ["hardware", "cover"],
        "benefits": [_benefit("Cover for leased kit", "Charged with the hardware lease.")],
    },
    "wholesale_pricing": {
        "short_description": "Retail and wholesale prices, tiers, and volume breaks.",
        "category": "selling",
        "icon": "layers",
        "tags": ["wholesale", "price tiers"],
        "benefits": [
            _benefit("Two price modes", "Switch between retail and wholesale at the register."),
            _benefit("Volume breaks", "Apply the tier already stored on the price list."),
        ],
    },
    "serial_tracking": {
        "short_description": "Track individual units by IMEI or serial number.",
        "category": "inventory",
        "icon": "hash",
        "tags": ["imei", "serial", "warranty"],
        "benefits": [
            _benefit("Unit history", "Keep the serial or IMEI with the unit."),
            _benefit("Sales and returns", "Identify the specific unit that was sold or returned."),
        ],
    },
    "b2b_credit": {
        "short_description": "On-account sales, credit limits, statements, and collections.",
        "category": "selling",
        "icon": "landmark",
        "tags": ["credit", "statements"],
        "benefits": [
            _benefit("Account sales", "Sell on account up to the customer's limit."),
            _benefit("Statements", "Collect against the balance the account already stores."),
        ],
    },
    "cheques": {
        "short_description": "Record cheques and post-dated cheques through clearing.",
        "category": "finance",
        "icon": "landmark",
        "tags": ["cheques", "pdc"],
        "benefits": [_benefit("Clearing", "Track a cheque from receipt through clearing.")],
    },
    "sales_orders": {
        "short_description": "Wholesale orders, partial deliveries, proof of delivery, and invoicing.",
        "category": "selling",
        "icon": "truck",
        "tags": ["orders", "delivery"],
        "benefits": [
            _benefit("Partial delivery", "Deliver and invoice part of an order."),
            _benefit("Proof of delivery", "Keep the delivery record with the order."),
        ],
    },
    "card_terminals": {
        "short_description": "Send the card amount to a supported terminal and confirm the payment.",
        "category": "payments",
        "icon": "credit-card",
        "tags": ["card", "terminal"],
        "benefits": [_benefit("Till and terminal", "The sale amount is sent to the configured terminal.")],
    },
    "uae_einvoicing": {
        "short_description": "Prepare structured invoices for a UAE accredited service provider.",
        "overview": (
            "For in-scope business and government sales. AxizPOS is not an accredited service provider. "
            "A provider account has to be connected before anything is submitted. "
            "This listing is not a statement that the integration is production-ready."
        ),
        "category": "compliance",
        "icon": "receipt",
        "tags": ["uae", "e-invoice", "vat"],
        "benefits": [
            _benefit("Structured invoice", "A snapshot of the posted sale for in-scope documents."),
            _benefit("Provider status", "Submission state stays with the e-invoicing plugin."),
            _benefit("Credit notes", "A refund of an e-invoice can raise a credit note."),
        ],
        "requirements": [
            "An accredited service provider account, held by the business or an approved partner.",
            "Buyer details required by the e-invoicing plugin for in-scope sales.",
        ],
        "steps": [
            _benefit("Purchase", "The add-on turns on after the existing invoice is paid."),
            _benefit("Connect a provider", "Provider credentials stay on the server."),
        ],
    },
}


def default_listing(code: str, description: str) -> dict:
    seed = dict(_DEFAULTS.get(code, {}))
    seed.setdefault("short_description", _plain(description, 240))
    seed.setdefault("category", "operations")
    seed.setdefault("icon", "puzzle")
    seed["customized"] = False
    seed["publication"] = "published"
    return normalize_listing(seed, customized=False)


def fill_listings(db: Session) -> None:
    """Writes seed copy onto rows the console has not edited."""
    for row in db.scalars(select(BillingAddon)):
        if listing_blank(row.listing):
            row.listing = default_listing(row.code, row.description or "")
    db.flush()


def _compatible_labels(code: str, module_keys: list[str]) -> list[str]:
    if not module_keys:
        return [capability_catalog.PROFILE_LABELS[profile] for profile in capability_catalog.PROFILES]
    labels = []
    for profile in capability_catalog.PROFILES:
        allowed = capability_catalog.catalogue(profile)
        if code in {item.value for item in allowed.optional} or code in {item.value for item in allowed.base}:
            labels.append(capability_catalog.PROFILE_LABELS[profile])
    return labels


def _search_text(row: BillingAddon, listing: AddonListing) -> str:
    parts = [row.name, row.description, listing.short_description, listing.overview, listing.category]
    parts.extend(listing.tags)
    parts.extend(item.title for item in listing.benefits)
    parts.extend(item.title for item in listing.features)
    parts.extend(item.description for item in listing.benefits)
    return " ".join(part for part in parts if part)


def marketplace_for(db: Session, settings: object, tenant: Tenant) -> MarketplaceOut:
    """Authoritative card state for one store. The portal does not decide activation itself."""
    from app.console import billing as billing_mod

    billing_mod.ensure_catalog(db)
    billing_mod.ensure_module_addons(db)
    fill_listings(db)
    profile = billing_mod._business_profile(settings, tenant)  # noqa: SLF001
    catalogue = capability_catalog.catalogue(profile)
    preset = {item.value for item in catalogue.base}
    optional = {item.value for item in catalogue.optional}
    subscription = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant.id))
    owned: dict[str, int] = {}
    status = ""
    if subscription is not None:
        status = subscription.status
        for item in db.scalars(select(SubscriptionItem).where(SubscriptionItem.subscription_id == subscription.id)):
            if item.quantity > 0:
                owned[item.addon_code] = item.quantity
    pending: dict[str, tuple[uuid.UUID, str]] = {}
    invoices = list(
        db.scalars(
            select(BillingInvoice).where(BillingInvoice.tenant_id == tenant.id, BillingInvoice.status == "pending")
        )
    )
    for invoice in invoices:
        review = db.scalar(
            select(BillingTransfer.id).where(
                BillingTransfer.invoice_id == invoice.id,
                BillingTransfer.status == "pending_review",
            )
        )
        kind = "pending_activation" if review is not None else "pending_payment"
        for line in db.scalars(select(BillingInvoiceLine).where(BillingInvoiceLine.invoice_id == invoice.id)):
            pending.setdefault(line.code, (invoice.id, kind))
    items: list[MarketplaceItem] = []
    recurring = 0
    for row in db.scalars(select(BillingAddon).order_by(BillingAddon.sort_order, BillingAddon.code)):
        listing = listing_out(row.listing)
        code = row.code
        module = bool(row.module_keys)
        compatible = (not module) or code in preset or code in optional
        state = "available"
        reason = ""
        invoice_id = None
        if module and code in preset:
            state = "included"
            reason = "Included in your plan"
        elif code in owned and status == "canceled":
            state = "expired"
            reason = "The subscription is canceled. History is kept."
        elif code in owned:
            state = "activated"
        elif code in pending:
            invoice_id, state = pending[code]
            reason = "Payment verification in progress" if state == "pending_activation" else "Awaiting payment"
        elif not compatible:
            state = "unavailable"
            reason = "Not available for this business type."
        elif not row.active:
            continue
        elif module and int(row.monthly_fils or 0) <= 0 and int(row.one_time_fils or 0) <= 0:
            state = "unpriced"
            reason = "Price is set in the console."
        if state == "activated":
            recurring += int(row.monthly_fils or 0) * owned.get(code, 1)
        if state in {"available", "unpriced"} and not row.active:
            continue
        items.append(
            MarketplaceItem(
                addon=billing_mod.addon_out(row),
                state=state,  # type: ignore[arg-type]
                reason=reason,
                invoice_id=invoice_id,
                compatible_labels=_compatible_labels(code, list(row.module_keys or [])),
                search_text=_search_text(row, listing),
            )
        )
    return MarketplaceOut(
        available=sum(1 for item in items if item.state == "available"),
        activated=sum(1 for item in items if item.state == "activated"),
        pending=sum(1 for item in items if item.state in {"pending_payment", "pending_activation"}),
        recurring_fils=recurring,
        items=items,
    )
