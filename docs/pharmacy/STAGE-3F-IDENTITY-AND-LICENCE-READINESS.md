# Stage 3F — Identity and licence readiness

Stage 3F.1 did not connect an identity or licence source, and it did not mark any account verified.

## What exists

Pharmacist authorization is a row on `pharmacist_authorizations` for a `users.id`. Governance officers are rows on `pharmacy_governance_officers`, also keyed by user id. Appointment, confirmation, approval, rejection, and revocation store those user ids and timestamps. Audit rows store the acting user id.

Two different user ids are two different accounts. They do not prove two different natural persons. A shared password, a shared PIN, or one person holding two accounts would still satisfy the account checks.

The permission comment on pharmacist appointment states that a governed officer record appoints pharmacists and that this is not a licence check. No pharmacist licence number, issuer, expiry, or verification result is stored on the authorization.

Veterinary products stay off with the message that a later licence is required. That is a catalogue block, not a connected licence registry.

## What does not exist

- Verified natural-person identity.
- A licence verification source.
- Licence expiry or revocation fed from a regulator.
- A provider integration.
- Fabricated licence numbers or fake "verified" flags. None were added.

## Boundary, if a source is later approved

Keep the current account workflow. Add a separate verification record only after a named source is approved. Suggested shape, not implemented:

| Field | Rule |
|---|---|
| User id | The account being checked. Not proof of a person by itself. |
| Source | The approved registry or manual process. Required. |
| Licence reference | The value returned by that source. Do not invent one. |
| Checked at | Timestamp of the check. |
| Expires at | From the source. An expired check cannot authorize release. |
| Revoked at | From the source or from an explicit local revocation. |
| Evidence | A reference the auditor can re-read. Not a copy of a secret token. |

Release and governance would consult that record in addition to the existing two-account rules. Until the record exists, release continues to require the current account-level pharmacist authorization and nothing more.

## Audit

Any later check should append an audit row with the user id, the source name, the result, and the time. It must not log licence images, identity-document numbers, or provider credentials.

## Business approval

This document does not approve an identity provider, a regulator API, or a manual licence process. Those remain external dependencies. Account separation must not be described as natural-person separation in a commercial or regulatory claim.
