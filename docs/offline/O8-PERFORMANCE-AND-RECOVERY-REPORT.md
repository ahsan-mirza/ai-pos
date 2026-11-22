# O8 performance and recovery

Status: **NOT RUN** as a separate performance study.

No startup, bootstrap, or memory baseline was measured on a native window. No clock was changed. No disk-full or kill-during-write test was added.

The desktop library run includes the existing 50,000-product search test and the allocation restart check: after the process drops the SQLite file handle and opens it again, the remainder is still 10 and the overdraw is still refused. That is a restart check, not a performance target.

Queue recovery remains the O5 contract. A collision stays quarantined. A transport failure can mark a staff event `retryable` without minting a new event id. This run did not time that path.

No performance threshold is proposed.
