# O6 signed allocation manifest

The manifest uses the same Ed25519 seed as permanent entitlements and a different purpose, so an entitlement document is not an allocation.

## Payload

Canonical JSON, sorted keys, no extra whitespace. The signature is over those UTF-8 bytes.

Fields: `schema_version` 1, `purpose` `stock_allocation`, `manifest_id`, `allocation_id`, `allocation_version`, `issuer` `axizpos`, `tenant_id`, `branch_id`, `terminal_id`, `device_binding`, `product_id`, `serial_number_id`, `batch_item_id`, `unit`, `quantity`, `policy_version`, `issued_at`, `key_id`.

A release acknowledgement uses `purpose` `stock_allocation_release` and names the released quantity and sequence.

## Verification

The API holds the signing seed. The register holds public keys only, through the O2 trusted-key list. Unknown keys fail. A changed payload fails. A different tenant, branch, terminal, or device binding fails. Schema other than 1 fails. A document whose purpose is not `stock_allocation` fails.

The test key is accepted only in test builds. Release builds still require `POS_ENTITLEMENT_KEY_ID` and `POS_ENTITLEMENT_PUBLIC_KEY`. Allocation grants are not enabled for a production release until that public key is configured. This limitation is unchanged from O2.

`terminal.bin` is not replaced.
