import uuid
from datetime import date

from app.services.timesheet_service import approved_minutes
from wholesale_support import CASHIER_ID, STORE, admin, event, push, seed

DAY = "2026-10-19"


def clock(entry_id: str, out: str | None = None, break_minutes: int = 0) -> dict:
    body = {"id": entry_id, "user_id": CASHIER_ID, "store_id": STORE, "clock_in_at": f"{DAY}T05:00:00Z"}
    if out:
        body.update(clock_out_at=f"{DAY}T{out}:00Z", break_minutes=break_minutes)
    return body


def test_register_clock_in_out_feeds_the_timesheet(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    entry_id = str(uuid.uuid4())
    assert push(client, [event("clock-in-1", "time_entry", clock(entry_id))]).status_code == 200
    open_sheet = client.get("/api/v1/timesheets", headers=headers, params={"from": DAY, "to": DAY}).json()
    assert open_sheet["staff"][0]["open_entries"] == 1

    assert push(client, [event("clock-out-1", "time_entry", clock(entry_id, "15:00", 30))]).status_code == 200
    sheet = client.get("/api/v1/timesheets", headers=headers, params={"from": DAY, "to": DAY}).json()
    person = sheet["staff"][0]
    # 10 hours less a 30 minute break is 570 minutes; everything past 8 hours is overtime.
    assert (person["worked_minutes"], person["overtime_minutes"], person["pending_approval"]) == (570, 90, 1)

    bad = push(client, [event("clock-bad", "time_entry", {**clock(str(uuid.uuid4()), "04:00")})])
    assert bad.status_code == 422

    corrected = client.put(
        f"/api/v1/timesheets/entries/{entry_id}",
        headers=headers,
        json={
            "clock_in_at": f"{DAY}T05:00:00Z",
            "clock_out_at": f"{DAY}T13:00:00Z",
            "break_minutes": 0,
            "note": "Left at 5pm",
        },
    )
    assert corrected.status_code == 200
    # A late retry from the register does not undo the manager's correction.
    assert push(client, [event("clock-out-retry", "time_entry", clock(entry_id, "15:00", 30))]).status_code == 200
    approved = client.post("/api/v1/timesheets/approve", headers=headers, json={"entry_ids": [entry_id]}).json()
    assert approved == {"approved": 1}
    locked = client.put(
        f"/api/v1/timesheets/entries/{entry_id}",
        headers=headers,
        json={"clock_in_at": f"{DAY}T05:00:00Z", "clock_out_at": f"{DAY}T14:00:00Z", "note": "Again"},
    )
    assert locked.status_code == 409
    assert approved_minutes(
        session, user_id=uuid.UUID(CASHIER_ID), start=date(2026, 10, 1), end=date(2026, 10, 31)
    ) == (480, 0)


def test_manager_adds_a_forgotten_shift(client) -> None:
    seed(client)
    headers, _ = admin(client)
    added = client.post(
        "/api/v1/timesheets/entries",
        headers=headers,
        json={
            "user_id": CASHIER_ID,
            "store_id": STORE,
            "clock_in_at": f"{DAY}T06:00:00Z",
            "clock_out_at": f"{DAY}T10:00:00Z",
            "note": "Forgot to clock in",
        },
    )
    assert added.status_code == 201
    entry = client.get("/api/v1/timesheets", headers=headers, params={"from": DAY, "to": DAY}).json()["staff"][0][
        "entries"
    ][0]
    assert (entry["source"], entry["worked_minutes"], entry["edit_note"]) == ("portal", 240, "Forgot to clock in")
    too_long = client.get("/api/v1/timesheets", headers=headers, params={"from": "2026-01-01", "to": DAY})
    assert too_long.status_code == 422
