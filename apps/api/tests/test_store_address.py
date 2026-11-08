"""A branch address keeps spaces, punctuation and other languages."""

import pytest
from pydantic import ValidationError

from app.schemas.address import clean_address
from app.schemas.inventory import StoreUpdate
from app.schemas.signup import SignupStore
from wholesale_support import admin, seed

SAMPLES = [
    "Shop 12, Building A, Main Street",
    "Office #204, Al Nahda 2, Dubai",
    "House No. 25-B, Street 10, DHA Phase 6, Lahore",
    "Unit 4/5, Block-C, Industrial Area",
    "Flat 12, Sheikh Zayed Road, Dubai, UAE",
    "شارع الشيخ زايد، دبي",
    "O'Brien's Shop",
    "Suite (12) Tower",
    "Marks & Spencer, Mall",
    "Shop  12,  Main  Street",
    "Étage 3, Rue de l'Université",
    "Building 15, Floor 2, Apt. 304",
]


def test_valid_addresses_keep_every_character() -> None:
    for sample in SAMPLES:
        pasted = f"  {sample}  "
        assert clean_address(pasted, required=True) == sample
        assert StoreUpdate(address=pasted).address == sample


def test_blank_overlong_and_non_strings_are_rejected() -> None:
    with pytest.raises(ValidationError, match="Enter the store address"):
        StoreUpdate(address="   ")
    with pytest.raises(ValidationError, match="Enter the store address"):
        SignupStore(store_name="Al Noor", slug="alnoor", address="", currency="AED", country="AE", trn=None)
    with pytest.raises(ValidationError, match="Enter the store address"):
        SignupStore(store_name="Al Noor", slug="alnoor", address="   ", currency="AED", country="AE", trn=None)
    with pytest.raises(ValidationError, match="255"):
        StoreUpdate(address="a" * 256)
    with pytest.raises(ValidationError):
        StoreUpdate(address=12)  # type: ignore[arg-type]
    assert clean_address("", required=False) is None
    assert StoreUpdate(address="").address is None
    assert clean_address("Shop  12", required=True) == "Shop  12"


def test_store_address_round_trip_and_receipt(client) -> None:
    seed(client)
    headers, _ = admin(client)
    listed = client.get("/api/v1/stores", headers=headers)
    assert listed.status_code == 200, listed.text
    store_id = listed.json()[0]["id"]
    for sample in SAMPLES:
        saved = client.patch(f"/api/v1/stores/{store_id}", headers=headers, json={"address": f"  {sample}  "})
        assert saved.status_code == 200, saved.text
        assert saved.json()["address"] == sample
        loaded = client.get(f"/api/v1/stores/{store_id}", headers=headers)
        assert loaded.status_code == 200, loaded.text
        assert loaded.json()["address"] == sample

    spaces = client.patch(f"/api/v1/stores/{store_id}", headers=headers, json={"address": "   "})
    assert spaces.status_code == 422
    assert "Enter the store address" in spaces.text
    huge = client.patch(f"/api/v1/stores/{store_id}", headers=headers, json={"address": "a" * 256})
    assert huge.status_code == 422
    assert "255" in huge.text
    number = client.patch(f"/api/v1/stores/{store_id}", headers=headers, json={"address": 12})
    assert number.status_code == 422
    assert client.get(f"/api/v1/stores/{store_id}", headers=headers).json()["address"] == SAMPLES[-1]

    receipt = client.get(f"/api/v1/settings/receipt?store_id={store_id}", headers=headers)
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()["store"]["address"] == SAMPLES[-1]

    cleared = client.patch(f"/api/v1/stores/{store_id}", headers=headers, json={"address": ""})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["address"] is None
    restored = client.patch(f"/api/v1/stores/{store_id}", headers=headers, json={"address": SAMPLES[0]})
    assert restored.status_code == 200, restored.text
    assert restored.json()["address"] == SAMPLES[0]
