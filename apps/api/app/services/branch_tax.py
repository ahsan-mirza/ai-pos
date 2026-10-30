"""Branch tax profiles. Calculation still goes through app.services.tax; this module only resolves which profile."""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, SyncRejected
from app.models.branch_tax import BranchTaxProfile, LegalEntity
from app.models.store import Store
from app.models.user import User
from app.schemas.branch_tax import BranchTaxOut, BranchTaxUpdate
from app.services import audit
from app.services.settings_service import cached_settings
from app.services.tax import TaxPolicy, line_tax
from app.tenancy.country_tax import as_dict, describe

_SAUDI = re.compile(r"^3\d{13}3$")


def _store(db: Session, store_id: uuid.UUID) -> Store:
    store = db.get(Store, store_id)
    if store is None:
        raise ApiError(404, "not_found", "Branch was not found.")
    return store


def _profile(db: Session, store_id: uuid.UUID) -> BranchTaxProfile | None:
    return db.scalar(select(BranchTaxProfile).where(BranchTaxProfile.store_id == store_id))


def _ensure(db: Session, store: Store) -> BranchTaxProfile:
    row = _profile(db, store.id)
    if row is not None:
        return row
    row = BranchTaxProfile(store_id=store.id, country=store.country, city=store.city)
    db.add(row)
    db.flush()
    return row


def _check_registration(country: str, number: str | None, *, registered: bool) -> str | None:
    if not registered:
        return number
    if not number:
        label = describe(country).registration_label
        raise ApiError(422, "invalid_tax", f"A tax-registered branch needs its {label}.")
    if country == "SA" and not _SAUDI.match(number):
        raise ApiError(422, "invalid_tax", "A Saudi VAT number is 15 digits that start and end with 3.")
    if country == "AE" and number.isdigit() and len(number) != 15:
        raise ApiError(422, "invalid_tax", "A UAE TRN is 15 digits.")
    return number


def _entity(db: Session, profile: BranchTaxProfile, country: str, legal_name: str | None) -> LegalEntity:
    if profile.legal_entity_id is not None:
        current = db.get(LegalEntity, profile.legal_entity_id)
        if current is not None and current.country == country:
            if legal_name:
                current.legal_name = legal_name
            return current
    shared = db.scalar(select(LegalEntity).where(LegalEntity.country == country))
    if shared is not None:
        return shared
    created = LegalEntity(name=legal_name or "Legal entity", country=country, legal_name=legal_name)
    db.add(created)
    db.flush()
    return created


def _view(store: Store, profile: BranchTaxProfile | None) -> BranchTaxOut:
    country = (profile.country if profile and profile.country else store.country) or None
    meta = describe(country or "AE")
    own = bool(profile and profile.own)
    registered = bool(profile.registered) if profile and own else False
    confirmed = bool(profile.rate_confirmed) if profile else False
    required = own and registered and not confirmed
    return BranchTaxOut(
        store_id=store.id,
        country=country,
        city=(profile.city if profile and profile.city else store.city),
        region=profile.region if profile else None,
        own=own,
        registered=registered if own else False,
        registration_number=profile.registration_number if profile else None,
        secondary_registration_number=profile.secondary_registration_number if profile else None,
        legal_name=profile.legal_name if profile else None,
        legal_name_local=profile.legal_name_local if profile else None,
        prices_include_vat=bool(profile.prices_include_vat) if profile and own else False,
        standard_rate_bps=int(profile.standard_rate_bps) if profile and own else 0,
        tax_authority=(profile.tax_authority if profile and own else meta.tax_authority),
        version=int(profile.version) if profile else 0,
        rate_confirmed=confirmed,
        configuration_required=required,
        legal_entity_id=profile.legal_entity_id if profile else None,
        country_tax=as_dict(describe(country)) if country else as_dict(meta),
    )


def read_profile(db: Session, store_id: uuid.UUID) -> BranchTaxOut:
    store = _store(db, store_id)
    return _view(store, _profile(db, store_id))


def save_profile(db: Session, actor: User, store_id: uuid.UUID, data: BranchTaxUpdate) -> BranchTaxOut:
    store = _store(db, store_id)
    profile = _ensure(db, store)
    number = _check_registration(data.country, data.registration_number, registered=data.registered)
    if (
        profile.country
        and profile.country != data.country
        and profile.registration_number
        and not data.confirm_country_change
    ):
        raise ApiError(
            409,
            "country_change_confirmation",
            "Changing the branch country keeps the current registration number. Confirm before saving.",
        )
    meta = describe(data.country)
    before = {
        "country": profile.country,
        "registered": profile.registered,
        "registration_number": profile.registration_number,
        "standard_rate_bps": profile.standard_rate_bps,
        "prices_include_vat": profile.prices_include_vat,
    }
    local = data.legal_name_local if meta.legal_local_language else None
    secondary = data.secondary_registration_number if meta.secondary_registration_label else None
    entity = _entity(db, profile, data.country, data.legal_name)
    profile.legal_entity_id = entity.id
    profile.country = data.country
    profile.city = data.city
    profile.region = data.region
    profile.own = True
    profile.registered = data.registered
    profile.registration_number = number
    profile.secondary_registration_number = secondary
    profile.legal_name = data.legal_name
    profile.legal_name_local = local
    profile.prices_include_vat = data.prices_include_vat
    profile.standard_rate_bps = data.standard_rate_bps
    profile.tax_authority = meta.tax_authority if meta.tax_authority in {"fta", "zatca"} else "fta"
    profile.version = int(profile.version or 0) + 1
    profile.rate_confirmed = True
    entity.legal_name = data.legal_name
    entity.legal_name_local = local
    store.country = data.country
    store.city = data.city
    if data.country == "AE" and data.region:
        store.emirate = data.region
    audit.record(
        db,
        action_type="UPDATE",
        action="settings.branch_tax",
        target_entity="BranchTaxProfile",
        target_entity_id=profile.id,
        user=actor,
        store_id=store.id,
        old_values=before,
        new_values={
            "country": profile.country,
            "registered": profile.registered,
            "registration_number": profile.registration_number,
            "standard_rate_bps": profile.standard_rate_bps,
            "version": profile.version,
        },
    )
    db.commit()
    db.refresh(profile)
    return _view(store, profile)


def assign_country(
    db: Session,
    store: Store,
    country: str,
    *,
    city: str | None,
    region: str | None,
    confirm: bool,
) -> None:
    """Point a branch at a country without copying another country's rate onto it."""
    profile = _ensure(db, store)
    if profile.country == country and city is None and region is None:
        return
    if profile.registration_number and profile.country and profile.country != country and not confirm:
        raise ApiError(
            409,
            "country_change_confirmation",
            "This branch already has a tax registration. Confirm the country change before it is saved.",
        )
    business = cached_settings(db)
    profile.country = country
    if city is not None:
        profile.city = city
        store.city = city
    if region is not None:
        profile.region = region
        if country == "AE":
            store.emirate = region
    store.country = country
    profile.own = True
    same_country = country == (business.country or "")
    if same_country and not profile.registration_number:
        profile.registered = bool(business.vat_registered)
        profile.registration_number = business.trn
        profile.legal_name = business.legal_name
        profile.legal_name_local = business.legal_name_ar
        profile.prices_include_vat = bool(business.prices_include_vat)
        profile.standard_rate_bps = int(business.standard_rate_bps)
        profile.tax_authority = business.tax_authority
        profile.rate_confirmed = True
        profile.legal_entity_id = _entity(db, profile, country, business.legal_name).id
    elif profile.registration_number:
        profile.rate_confirmed = False
    else:
        profile.registered = False
        profile.standard_rate_bps = 0
        profile.prices_include_vat = False
        profile.rate_confirmed = True
        profile.tax_authority = describe(country).tax_authority
    profile.version = int(profile.version or 0) + 1


def policy_for_store(db: Session, store_id: uuid.UUID) -> TaxPolicy | None:
    """The branch profile when it has its own tax. None means keep the business-wide policy.

    A registered branch whose rate was not confirmed cannot sell. Another branch's profile is never used.
    """
    profile = _profile(db, store_id)
    if profile is None or not profile.own:
        return None
    if profile.registered and not profile.rate_confirmed:
        raise SyncRejected(
            "Confirm this branch's tax rate before selling. Another branch's tax settings are not used."
        )
    if not profile.registered:
        return TaxPolicy(enforced=False, prices_include_vat=False, standard_rate_bps=0)
    return TaxPolicy(
        enforced=True,
        prices_include_vat=bool(profile.prices_include_vat),
        standard_rate_bps=int(profile.standard_rate_bps),
    )


def snapshot_for(db: Session, store_id: uuid.UUID, currency: str) -> dict[str, object]:
    """Values to freeze on the sale. Uses the branch profile when it owns tax, otherwise the business settings."""
    profile = _profile(db, store_id)
    business = cached_settings(db)
    own = profile is not None and profile.own and (not profile.registered or profile.rate_confirmed)
    if own and profile is not None:
        country = profile.country or ""
        meta = describe(country or "AE")
        return {
            "store_id": str(store_id),
            "country": country,
            "legal_entity_id": str(profile.legal_entity_id) if profile.legal_entity_id else None,
            "registered": bool(profile.registered),
            "registration_number": profile.registration_number,
            "registration_label": meta.registration_label,
            "secondary_registration_number": profile.secondary_registration_number,
            "legal_name": profile.legal_name,
            "legal_name_local": profile.legal_name_local,
            "legal_local_language": meta.legal_local_language,
            "standard_rate_bps": int(profile.standard_rate_bps) if profile.registered else 0,
            "prices_include_vat": bool(profile.prices_include_vat) if profile.registered else False,
            "tax_authority": profile.tax_authority,
            "version": int(profile.version),
            "currency": currency,
        }
    return {
        "store_id": str(store_id),
        "country": business.country or "",
        "legal_entity_id": None,
        "registered": bool(business.vat_registered),
        "registration_number": business.trn,
        "registration_label": describe(business.country or "AE").registration_label,
        "secondary_registration_number": None,
        "legal_name": business.legal_name,
        "legal_name_local": business.legal_name_ar,
        "legal_local_language": describe(business.country or "AE").legal_local_language if business.country else "ar",
        "standard_rate_bps": int(business.standard_rate_bps) if business.vat_registered else 0,
        "prices_include_vat": bool(business.prices_include_vat) if business.vat_registered else False,
        "tax_authority": business.tax_authority,
        "version": 0,
        "currency": currency,
    }


def preview(db: Session, store_id: uuid.UUID, amount_cents: int, category: str) -> dict[str, int | str | None]:
    try:
        rules = policy_for_store(db, store_id)
    except SyncRejected as exc:
        raise ApiError(409, "tax_configuration_required", str(exc)) from exc
    if rules is None:
        from app.services.tax import policy

        rules = policy(db)
    if category not in {"STANDARD", "ZERO", "EXEMPT"}:
        raise ApiError(422, "invalid_tax", "Choose a standard, zero-rated, or exempt category.")
    rate = rules.rate_for(category) if rules.enforced else 0
    priced = line_tax(amount_cents, 1, rate, inclusive=rules.prices_include_vat and rules.enforced)
    return {
        "net_cents": priced.net_cents,
        "tax_cents": priced.tax_cents,
        "total_cents": priced.line_total_cents,
        "rate_bps": rate,
        "category": category,
    }


def configuration_required(db: Session, store_id: uuid.UUID) -> bool:
    profile = _profile(db, store_id)
    return bool(profile and profile.own and profile.registered and not profile.rate_confirmed)


def overlay_settings(db: Session, store_id: uuid.UUID, out: object) -> object:
    """Replace the business tax fields a register reads when its branch has its own confirmed profile."""
    profile = _profile(db, store_id)
    if profile is None or not profile.own:
        return out
    if profile.registered and not profile.rate_confirmed:
        return out.model_copy(update={"tax_configuration_required": True})  # type: ignore[attr-defined]
    rules = policy_for_store(db, store_id)
    if rules is None:
        return out
    local = profile.legal_name_local if describe(profile.country or "").legal_local_language == "ar" else None
    return out.model_copy(  # type: ignore[attr-defined]
        update={
            "vat_registered": rules.enforced,
            "prices_include_vat": rules.prices_include_vat,
            "standard_rate_bps": rules.standard_rate_bps,
            "trn": profile.registration_number,
            "legal_name": profile.legal_name or out.legal_name,  # type: ignore[attr-defined]
            "legal_name_ar": local if local is not None else out.legal_name_ar,  # type: ignore[attr-defined]
            "tax_authority": profile.tax_authority,
            "country": profile.country or out.country,  # type: ignore[attr-defined]
            "tax_configuration_required": False,
        }
    )
