"""Cancellation rates stay separate from completed sales, and reason codes classify who started it."""

from app.services.cancellation_report import classify, rates


def test_full_and_partial_rates_use_created_orders_as_the_denominator() -> None:
    full, partial = rates(created=10, full=2, partial=1)
    assert full == 20.0
    assert partial == 10.0
    assert rates(0, 1, 1) == (0.0, 0.0)


def test_a_coded_reason_is_customer_or_employee_and_free_text_stays_other() -> None:
    assert classify("[changed_mind] They no longer want it") == ("changed_mind", "customer", "They no longer want it")
    assert classify("[entry_mistake] Wrong SKU") == ("entry_mistake", "employee", "Wrong SKU")
    assert classify("[stock] None left")[0] == "stock"
    code, initiator, note = classify("Cashier typed a note")
    assert (code, initiator, note) == ("other", "employee", "Cashier typed a note")


def test_unknown_codes_do_not_invent_a_category() -> None:
    assert classify("[fraud] looks suspicious")[0] == "other"
