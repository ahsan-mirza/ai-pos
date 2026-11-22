# O7 rejection and recovery

A refused staff change stays on the register that made it. It is not deleted and it is not shown as a normal server user.

## Create refused

`mark_provisioning(..., "rejected")` sets the local event to `rejected`, sets `cached_users.provisioning_status` to `rejected`, and sets `is_active` to 0. `finish_offline` then refuses the account before the PIN check: "This account was not accepted by the server."

The row and the audit rows remain. The username is not cleared, so a later create does not quietly reuse it on that register while the row is still there. The server does not list the person on `GET /users/staff-feed`.

The server stores its own `staff_provisioning_events` row with `status = rejected` and `safe_message` set to the API error text. That text is not a PIN and not a verifier. Tests assert the fixture PIN digits are absent from those messages and from the feed body.

## Disable refused

Local disablement sets `is_active` to 0 immediately and writes a `disable` event. If that event is later marked `rejected`, `is_active` stays 0. The origin register does not unlock that person again because the server disagreed.

Other registers are unchanged until they pull an accepted update. They keep the last server-accepted row. A rejected disable is not an instruction to re-enable them.

A conflicting replay of an accepted disable (same event id, different body) returns 409 `provisioning_conflict` and leaves `is_active` false.

## What an operator does next

There is no Force Provision and no Ignore Rejection control. The local account stays blocked when the server rejected the create. A new attempt is a new event, made by someone who currently holds `users:create`, and the server authorizes that attempt again. The old event stays in `staff_audit` and `staff_provisioning`.

This phase does not add a separate `awaiting_review` queue. A domain refusal is `rejected`. A same-id payload change is `provisioning_conflict`.
