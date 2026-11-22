# O8.2 production entitlement key readiness

Status: **AWAITING APPROVAL**.

No authorized production public key was supplied. This run did not generate one, did not place the test key in the release list, and did not disable signature verification.

## What the build accepts

`production_trusted_keys()` reads two compile-time sources:

- `POS_ENTITLEMENT_PUBLIC_KEYS`, a comma-separated `key-id:base64` list
- `POS_ENTITLEMENT_KEY_ID` and `POS_ENTITLEMENT_PUBLIC_KEY`, one extra pair

Both values are public keys. A bad list entry is skipped. An empty list fails closed when a document is verified. An unknown key id fails closed. An invalid signature fails closed. The private signing key is not compiled into the desktop crate.

The O2 test key is added only inside `trusted_keys()` under `cfg(test)`. `the_test_signing_key_is_not_a_release_key` passed in this run. `a_rotation_list_keeps_named_public_keys_and_drops_a_bad_entry` passed. Those tests use isolated test material. They are not a production trust decision.

Rotation is the list plus the singular pair. A key id already present is not added twice. Removing a key from the next release build stops that id from verifying. This run did not ship a release build with a production key.

Release logs were not inspected against a production build, because no authorized key was available to put in one.
