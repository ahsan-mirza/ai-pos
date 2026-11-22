# Offline staff management

Status: not implemented.

Offline unlock uses `cached_users` and Argon2 PIN hashes. Failed attempts and lockout columns already exist. A Store Admin cannot create, edit, disable, or reset a cashier on the register.

There is no Staff & Access workspace and no provisioning outbox event. A new account cannot be marked `LOCAL ACTIVE · PENDING SERVER PROVISIONING`.

Privilege limits that must hold when this is built: no Platform Super Admin creation, no self-elevation, no other branch, no other tenant, no seat-limit bypass, and no deletion of audit rows.
