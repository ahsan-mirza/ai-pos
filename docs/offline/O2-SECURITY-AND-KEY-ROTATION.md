# Security and key rotation

## Storage

`terminal.bin` stays sealed with `CryptProtectData` for the current Windows user. The flag is `CRYPTPROTECT_UI_FORBIDDEN`. `CRYPTPROTECT_LOCAL_MACHINE` is not set. Extra entropy remains `ai-pos-terminal-config-v1`.

Version 2 is a JSON object inside that seal: the O1 `TerminalConfig`, the device public key, the device private key, and the entitlement payload, signature, and key id when verification succeeded. A file that is still a bare `TerminalConfig` loads as version 2 in memory and keeps the same register id and device token. Saving writes version 2. A corrupt file is left in place. A DPAPI failure does not generate a new device key.

Save writes `terminal.bin.tmp`, flushes, reads it back, copies the current file to `terminal.bin.bak`, then replaces the active file. A failed replace restores the backup when the active file is missing.

The device private key and the device token are not on `TerminalStatus` and are not sent to the webview as entitlement material. The frontend does not verify the signature.

## Device binding

The register generates an Ed25519 key pair and sends the public key on activation. The signed `device_binding` is the SHA-256 hex of that public key. Another register's copy of the payload fails `DEVICE_BINDING_MISMATCH`.

## Recovery

| Situation | Behaviour |
| --- | --- |
| Missing `terminal.bin` | `NOT_ACTIVATED`. A new activation may create a device key. |
| Corrupt `terminal.bin` | Startup stays `REQUIRES_ONLINE_RECOVERY` and does not mint a device key. An activation key may replace the file. `save` copies the previous bytes to `terminal.bin.bak` before the new file becomes active. |
| DPAPI decryption failure, including another Windows profile | Same recovery state at startup. No device key is generated until someone presents an activation key. |
| Windows reinstall or another computer | The sealed file does not open. A copied entitlement does not activate that computer. Recovery is a new online activation key. |
| Hardware replacement | Same as a new computer. Rebinding requires a new activation key. The entitlement endpoint refuses a different public key. |

## Key rotation

Add a new public key to the desktop trust set under a new `key_id` before issuing with that id. Old entitlements keep verifying while their `key_id` remains trusted. An unknown `key_id` is `UNKNOWN_SIGNING_KEY`. There is no unsigned fallback. Retiring a key means removing it from the trust set; entitlements signed only by that key then fail closed. A compromised seed is retired the same way, and affected registers need a new online activation. No production seed is in this repository.

## Clock

The signature does not depend on the local clock. Tests call `verify` with the clock at zero, thirty days ahead, and before `issued_at`. The machine clock was not changed. Purchased-capability and promotional end times in the capability cache stay separate and still expire on their own timestamps. A verified permanent entitlement ignores the 24-hour subscription lease for ordinary selling. Pharmacy medicine sales stay blocked while offline. The inventory ledger is unchanged.
