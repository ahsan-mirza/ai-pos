# Conflict resolution

Status: not implemented.

The server treats a repeated idempotency key as `duplicate` and rolls a rejected event back with the rest of its batch. It does not return a conflict the register can keep beside an accepted event.

No conflict fixture was run. No sale, return, laundry order, or stock movement was replayed in this phase.
