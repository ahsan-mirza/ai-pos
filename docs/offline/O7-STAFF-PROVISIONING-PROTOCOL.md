# O7 staff provisioning protocol

Staff changes travel in their own outbox. They are not sales events and they are not inserted into `sync_queue`.

## Local event

SQLite `staff_provisioning`:

| Column | Meaning |
| --- | --- |
| `id` | Event id. The same id is sent to the server. |
| `user_id` | Local staff id. |
| `operation` | `create` or `disable`. |
| `payload` | JSON. Create carries `user_id`, `username`, `full_name`, `store_id`, `role_name`, `pin_verifier`. No plaintext PIN. |
| `status` | `pending`, then `accepted` or `rejected`. |
| `last_error` | Safe server text. Empty on acceptance. |
| `created_at` | When the local event was written. |

The original row is updated only to record the server outcome. A later correction is a new event id and a new audit row.

SQLite `staff_audit` records `actor_id`, `user_id`, `operation`, `status`, and `created_at`. It does not store the verifier.

`cached_users.provisioning_status` for a local create is `pending`. The label shown to a manager is `LOCAL ACTIVE · PENDING SERVER PROVISIONING`.

The local table does not yet have separate columns for tenant id, originating terminal id, schema version, base server version, or last-attempt time. Tenant and branch travel inside the payload (`store_id`) and the authenticated server request. That gap is a limitation, not a second queue.

## Server request

`POST /api/v1/users/provision` requires a signed-in user with `users:create`. The body is `StaffProvisionIn`: `event_id`, `operation`, `user_id`, `username`, `full_name`, `email`, `store_id`, `role_name`, `pin_verifier`.

The server hashes the canonical JSON and stores it on `staff_provisioning_events.payload_hash`.

| Situation | Result |
| --- | --- |
| New event, checks pass | `accepted`. The user is inserted or disabled. |
| Same `event_id`, same hash | `duplicate`. No second user. |
| Same `event_id`, different hash | 409 `provisioning_conflict`. The original user is unchanged. |
| Role is Super Admin or Platform Super Admin, or a Store Manager asks for Store Manager | 403 `role_not_allowed`. A rejected event row is stored. |
| Actor is not Store Manager or Super Admin | 403 `role_not_allowed`. |
| Store-scoped actor names another branch | 403 `store_scope`. |
| Username already exists | 409 `conflict`. |
| Verifier is not `$argon2id$…` within 255 characters | 422 `invalid_verifier`. |
| Active users have reached `limit_value("staff")` | 409 `plan_limit`. |
| Disable of a missing user | 404 `not_found`. |
| Disable of the signed-in user | 422 `self_change`. |

Each request is one event. Accepting one event does not roll back another event that was already accepted. A domain refusal rolls the user change back, then commits the rejected event row, then returns the error. Transport failures are not given a server status; the local row stays `pending`.

This build does not emit the separate statuses `retryable` or `awaiting_review`. A domain refusal is `rejected`. A hash collision is `provisioning_conflict`.

Disablement sets `is_active` false and increments `token_version`. It does not delete the user.

## Other registers

`GET /api/v1/users/staff-feed` requires a device credential (`X-Terminal-Token` or `X-Api-Key`). A user bearer token is not enough. The feed lists users that have an accepted provisioning event and an `$argon2id$` verifier. Pending and rejected creates are absent. A disabled accepted user is present with `is_active: false`, so another register can apply the disablement.

The feed is not part of product bootstrap. The response carries `pin_verifier` because that is the credential the other register must store. It is not written to application logs by this route.

`import_accepted` in `staff.rs` refuses anything that does not start with `$argon2`, refuses Super Admin and Platform Super Admin, and inserts the row as `provisioning_status = 'accepted'` with the local permission ceiling for that role. Until that import runs, the other register has no row and cannot unlock the person.
