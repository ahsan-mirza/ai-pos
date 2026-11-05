"""Model context is compact JSON. TOON helpers stay available and are not sent to the model."""

import json

from app.services.llm_context import (
    decode_toon_context,
    encode_llm_context_to_toon,
    estimate_context_tokens,
    prepare_llm_context,
    validate_toon_document,
)


def test_round_trip_keeps_values() -> None:
    data = {
        "conversation": {
            "tenant_context": "authorized_current_tenant",
            "human_handling": False,
            "pending_customer_messages": ["Hello", "هل لديكم بدلات قطنية؟"],
            "language": "ar",
        },
        "matched_products": [
            {"product_id": "p1", "name": "Cotton Suit, Beige Frost", "price": "6400.00 AED", "confidence": 0.98},
            {"product_id": "p2", "name": "بدلة قطن", "price": "10.00 AED", "confidence": 0.91},
        ],
        "flags": {"ready": True, "missing": None, "count": 0},
        "notes": [],
        "nested": {"price": {"currency": "PKR", "retail_price": 6400, "source": "retail_pricing_resolver"}},
    }
    text = encode_llm_context_to_toon(data)
    assert "matched_products[2]{product_id,name,price,confidence}:" in text
    assert decode_toon_context(text) == data
    assert validate_toon_document(text) is True


def test_restricted_fields_are_omitted() -> None:
    text = encode_llm_context_to_toon(
        {"name": "Cable", "price": "15.00", "purchase_cost": 400, "salary": 1000, "margin": 20}
    )
    assert "purchase_cost" not in text
    assert "salary" not in text
    assert "margin" not in text
    assert decode_toon_context(text) == {"name": "Cable", "price": "15.00"}


def test_special_characters_arabic_and_empty_values() -> None:
    data = {
        "name": 'Quote "frost" \\ path',
        "arabic": "قطن",
        "mark": "café — 100%",
        "items": [],
        "blank": "",
        "ok": True,
        "no": False,
        "none": None,
        "whole": 2,
        "part": 1.5,
    }
    assert decode_toon_context(encode_llm_context_to_toon(data)) == data


def test_malformed_and_truncated_documents_are_rejected() -> None:
    text = encode_llm_context_to_toon({"matched_products": [{"name": "Alpha"}, {"name": "Beta"}]})
    row = text.index("\n")
    assert validate_toon_document("matched_products[2]{name}:\n  only-one") is False
    assert validate_toon_document(text[: row + 3]) is False
    assert validate_toon_document("") is False


def test_catalogue_context_sent_to_the_model_is_json() -> None:
    rows = [
        {
            "product_id": f"p{index}",
            "name": f"Cotton Suit {index}",
            "sku": f"CS-{index}",
            "category": "Suits",
            "brand": "House",
            "confidence": 0.9,
        }
        for index in range(1, 6)
    ]
    document = prepare_llm_context({"matched_products": rows})
    assert document.format == "json"
    assert document.fallback is False
    assert document.valid is True
    assert document.text == document.json_text
    assert document.text.startswith('{"matched_products":')
    assert "product_id" in document.text
    assert document.toon_text is None

    tiny = prepare_llm_context({"a": 1, "b": 2})
    assert tiny.format == "json"
    assert tiny.text == json.dumps({"a": 1, "b": 2}, separators=(",", ":"))


def test_larger_catalogues_stay_json() -> None:
    for size in (5, 50, 100):
        rows = [{"product_id": f"p{index}", "name": f"Item {index}", "sku": f"S-{index}"} for index in range(size)]
        document = prepare_llm_context({"matched_products": rows})
        assert document.format == "json"
        assert document.text == document.json_text
        assert json.loads(document.text)["matched_products"][0]["name"] == "Item 0"
    assert estimate_context_tokens("Cotton Suit") > 0
