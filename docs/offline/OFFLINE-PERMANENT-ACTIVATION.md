# Permanent offline activation

Status: O2 implemented with limitations. See `docs/offline/O2-ACCEPTANCE-REPORT.md`. The notes below describe the gap that O2 closed.

Activation is still the one-time key and device token. When the register sends a device public key and the API has a signing seed, the same call now returns a signed permanent entitlement. The design, trust rules, and test evidence are in the O2 documents. A release build does not yet embed a production verification key, so it rejects signatures until that key is compiled in. No production key was generated.
