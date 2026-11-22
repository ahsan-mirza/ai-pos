//! Permanent offline entitlement. The register verifies. It never signs.
//!
//! A valid signature does not expire with the clock and does not assign stock to this terminal.

use std::collections::BTreeMap;

use base64::engine::general_purpose::STANDARD;
use base64::Engine;
use ed25519_dalek::{Signature, VerifyingKey, Verifier};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};

pub const VALID: &str = "VALID_PERMANENT_ENTITLEMENT";
pub const MISSING: &str = "MISSING_ENTITLEMENT";
pub const INVALID_SIGNATURE: &str = "INVALID_SIGNATURE";
pub const UNKNOWN_KEY: &str = "UNKNOWN_SIGNING_KEY";
pub const DEVICE_MISMATCH: &str = "DEVICE_BINDING_MISMATCH";
pub const TENANT_MISMATCH: &str = "TENANT_BINDING_MISMATCH";
pub const BRANCH_MISMATCH: &str = "BRANCH_BINDING_MISMATCH";
pub const TERMINAL_MISMATCH: &str = "TERMINAL_BINDING_MISMATCH";
pub const UNSUPPORTED_SCHEMA: &str = "UNSUPPORTED_SCHEMA";
pub const STORAGE_DECRYPTION_FAILED: &str = "STORAGE_DECRYPTION_FAILED";
pub const MALFORMED: &str = "MALFORMED_ENTITLEMENT";

pub const NOT_ACTIVATED: &str = "NOT_ACTIVATED";
pub const ENTITLEMENT_VALID: &str = "ENTITLEMENT_VALID";
pub const BOOTSTRAP_REQUIRED: &str = "BOOTSTRAP_REQUIRED";
pub const BOOTSTRAP_INCOMPLETE: &str = "BOOTSTRAP_INCOMPLETE";
pub const OFFLINE_READY: &str = "OFFLINE_READY";
pub const ONLINE_SYNC_REQUIRED: &str = "ONLINE_SYNC_REQUIRED";
pub const REQUIRES_ONLINE_RECOVERY: &str = "REQUIRES_ONLINE_RECOVERY";
pub const BOOTSTRAP_IN_PROGRESS: &str = "BOOTSTRAP_IN_PROGRESS";
pub const BOOTSTRAP_FAILED: &str = "BOOTSTRAP_FAILED";
pub const BOOTSTRAP_COMPLETE: &str = "BOOTSTRAP_COMPLETE";
pub const PULL_PENDING: &str = "PULL_PENDING";
pub const PULL_FAILED: &str = "PULL_FAILED";

const ISSUER: &str = "axizpos";
const AUDIENCE: &str = "axizpos-register";

#[derive(Clone, Debug, serde::Deserialize, serde::Serialize)]
pub struct SignedEntitlement {
    pub payload: String,
    pub signature: String,
    pub key_id: String,
}

#[derive(Clone, Debug)]
pub struct TrustedKey {
    pub id: String,
    pub public_key: VerifyingKey,
}

#[derive(Clone, Debug)]
pub struct ExpectedBinding {
    pub tenant_id: String,
    pub branch_id: String,
    pub terminal_id: String,
    /// SHA-256 hex of this register's Ed25519 public key.
    pub device_binding: String,
}

#[derive(Clone, Debug)]
pub struct LocalBaseline {
    pub activated: bool,
    pub storage_damaged: bool,
    /// None means the catalogue and staff checks were not run.
    pub sqlite_open: Option<bool>,
    pub queue_readable: bool,
    pub products: i64,
    pub staff: i64,
    pub pending: i64,
    pub capability_snapshot: bool,
    pub server_subscription_blocked: bool,
    /// Empty keeps the O2 product-count check. Other values are the O3 bootstrap states.
    pub bootstrap_status: String,
    pub pull_failed: bool,
}

/// Public keys compiled into a release build. The O2 test key is not one of them.
///
/// `POS_ENTITLEMENT_PUBLIC_KEYS` is `key-id:base64,key-id:base64` for rotation.
/// The singular `POS_ENTITLEMENT_KEY_ID` and `POS_ENTITLEMENT_PUBLIC_KEY` pair is the same kind of entry.
pub fn production_trusted_keys() -> Vec<TrustedKey> {
    let mut keys = parse_trusted_key_list(option_env!("POS_ENTITLEMENT_PUBLIC_KEYS").unwrap_or(""));
    if let (Some(id), Some(raw)) = (option_env!("POS_ENTITLEMENT_KEY_ID"), option_env!("POS_ENTITLEMENT_PUBLIC_KEY")) {
        if !id.is_empty() && !raw.is_empty() {
            if let Some(key) = parse_public_key(raw) {
                if !keys.iter().any(|item: &TrustedKey| item.id == id) {
                    keys.push(TrustedKey { id: id.to_string(), public_key: key });
                }
            }
        }
    }
    keys
}

/// Parses `key-id:base64` entries. A bad entry is skipped. An empty list fails closed at verification.
pub fn parse_trusted_key_list(raw: &str) -> Vec<TrustedKey> {
    let mut keys: Vec<TrustedKey> = Vec::new();
    for entry in raw.split(',').map(str::trim).filter(|item| !item.is_empty()) {
        let Some((id, material)) = entry.split_once(':') else {
            continue;
        };
        if id.is_empty() {
            continue;
        }
        if let Some(key) = parse_public_key(material) {
            if !keys.iter().any(|item: &TrustedKey| item.id == id) {
                keys.push(TrustedKey { id: id.to_string(), public_key: key });
            }
        }
    }
    keys
}

/// Keys this process will accept. Tests add the dedicated test key. Release builds do not.
pub fn trusted_keys() -> Vec<TrustedKey> {
    let mut keys = production_trusted_keys();
    #[cfg(test)]
    {
        use ed25519_dalek::SigningKey;
        let signing = SigningKey::from_bytes(&[7u8; 32]);
        keys.push(TrustedKey {
            id: "o2-test-1".into(),
            public_key: signing.verifying_key(),
        });
    }
    keys
}

pub fn parse_public_key(raw: &str) -> Option<VerifyingKey> {
    let bytes = STANDARD.decode(raw.trim()).ok()?;
    let array: [u8; 32] = bytes.try_into().ok()?;
    VerifyingKey::from_bytes(&array).ok()
}

pub fn generate_device_key() -> Result<(String, String), String> {
    use ed25519_dalek::SigningKey;
    let signing = SigningKey::generate(&mut rand::rngs::OsRng);
    let public = STANDARD.encode(signing.verifying_key().to_bytes());
    let private = STANDARD.encode(signing.to_bytes());
    Ok((public, private))
}

pub fn code_for(payload: &str, signature: &str, key_id: &str, expected: &ExpectedBinding, now_unix: i64) -> &'static str {
    if payload.is_empty() {
        return MISSING;
    }
    verify(payload, signature, key_id, expected, &trusted_keys(), now_unix)
}

pub fn device_binding(public_key_b64: &str) -> Option<String> {
    let bytes = STANDARD.decode(public_key_b64.trim()).ok()?;
    if bytes.len() != 32 {
        return None;
    }
    Some(hex_sha256(&bytes))
}

fn hex_sha256(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}

/// `now_unix` is accepted so tests can move the clock. The signature does not use it.
pub fn verify(
    payload: &str,
    signature_b64: &str,
    key_id: &str,
    expected: &ExpectedBinding,
    trusted: &[TrustedKey],
    _now_unix: i64,
) -> &'static str {
    if payload.is_empty() || signature_b64.is_empty() || key_id.is_empty() {
        return MISSING;
    }
    let Some(key) = trusted.iter().find(|item| item.id == key_id) else {
        return UNKNOWN_KEY;
    };
    let Ok(signature_bytes) = STANDARD.decode(signature_b64.trim()) else {
        return INVALID_SIGNATURE;
    };
    let Ok(signature_array) = <[u8; 64]>::try_from(signature_bytes.as_slice()) else {
        return INVALID_SIGNATURE;
    };
    let signature = Signature::from_bytes(&signature_array);
    if key.public_key.verify(payload.as_bytes(), &signature).is_err() {
        return INVALID_SIGNATURE;
    }
    let Ok(parsed) = serde_json::from_str::<Value>(payload) else {
        return MALFORMED;
    };
    if canonical_json(&parsed) != payload {
        return MALFORMED;
    }
    let Some(document) = parsed.as_object() else {
        return MALFORMED;
    };
    let Some(schema) = document.get("schema_version").and_then(Value::as_i64) else {
        return MALFORMED;
    };
    if schema != 1 {
        return UNSUPPORTED_SCHEMA;
    }
    if document.get("permanent") != Some(&Value::Bool(true)) {
        return MALFORMED;
    }
    if document.get("issuer").and_then(Value::as_str) != Some(ISSUER)
        || document.get("audience").and_then(Value::as_str) != Some(AUDIENCE)
    {
        return MALFORMED;
    }
    for field in ["entitlement_id", "tenant_id", "branch_id", "terminal_id", "device_binding", "plan_id", "issued_at", "key_id"]
    {
        match document.get(field).and_then(Value::as_str) {
            Some(value) if !value.is_empty() => {}
            _ => return MALFORMED,
        }
    }
    if document.get("key_id").and_then(Value::as_str) != Some(key_id) {
        return MALFORMED;
    }
    if document.get("device_binding").and_then(Value::as_str) != Some(expected.device_binding.as_str()) {
        return DEVICE_MISMATCH;
    }
    if document.get("tenant_id").and_then(Value::as_str) != Some(expected.tenant_id.as_str()) {
        return TENANT_MISMATCH;
    }
    if document.get("branch_id").and_then(Value::as_str) != Some(expected.branch_id.as_str()) {
        return BRANCH_MISMATCH;
    }
    if document.get("terminal_id").and_then(Value::as_str) != Some(expected.terminal_id.as_str()) {
        return TERMINAL_MISMATCH;
    }
    VALID
}

/// First match wins. `OFFLINE_READY` is the single-terminal baseline, not multi-terminal stock safety.
pub fn readiness(code: &str, facts: &LocalBaseline) -> &'static str {
    if facts.storage_damaged {
        return REQUIRES_ONLINE_RECOVERY;
    }
    if !facts.activated {
        return NOT_ACTIVATED;
    }
    if code == MISSING || code.is_empty() {
        return "ENTITLEMENT_MISSING";
    }
    if code != VALID {
        return "ENTITLEMENT_INVALID";
    }
    let Some(open) = facts.sqlite_open else {
        return ENTITLEMENT_VALID;
    };
    if !open || !facts.queue_readable {
        return BOOTSTRAP_REQUIRED;
    }
    match facts.bootstrap_status.as_str() {
        "in_progress" => return BOOTSTRAP_IN_PROGRESS,
        "failed" => return BOOTSTRAP_FAILED,
        "pull_failed" => return PULL_FAILED,
        "pull_pending" => return PULL_PENDING,
        _ => {}
    }
    if facts.pull_failed {
        return PULL_FAILED;
    }
    if facts.bootstrap_status == "incomplete" || facts.products <= 0 || facts.staff <= 0 || !facts.capability_snapshot {
        return BOOTSTRAP_INCOMPLETE;
    }
    if facts.server_subscription_blocked || facts.pending > 0 {
        return ONLINE_SYNC_REQUIRED;
    }
    if facts.bootstrap_status == "complete" {
        return OFFLINE_READY;
    }
    // Empty status is the O2 path: catalogue and staff counts already passed.
    OFFLINE_READY
}

/// Stock allocation is a later phase. This stays false so O2 cannot turn on a second stock model.
pub fn single_terminal_offline_stock_enabled() -> bool {
    false
}

pub fn describe_bootstrap(status: &str) -> &'static str {
    match status {
        "complete" => BOOTSTRAP_COMPLETE,
        "in_progress" => BOOTSTRAP_IN_PROGRESS,
        "failed" => BOOTSTRAP_FAILED,
        "pull_failed" => PULL_FAILED,
        "pull_pending" => PULL_PENDING,
        _ => BOOTSTRAP_INCOMPLETE,
    }
}

pub fn verification_message(code: &str) -> &'static str {
    match code {
        VALID => "Permanent entitlement verified. A remote change applies only after this register syncs.",
        MISSING => "Activate this register before selling.",
        INVALID_SIGNATURE => "The entitlement signature does not match. Activate again with a new key.",
        UNKNOWN_KEY => "This register does not trust the key that signed the entitlement.",
        DEVICE_MISMATCH => "This entitlement belongs to a different device.",
        TENANT_MISMATCH => "This entitlement belongs to a different store account.",
        BRANCH_MISMATCH => "This entitlement belongs to a different branch.",
        TERMINAL_MISMATCH => "This entitlement belongs to a different register.",
        UNSUPPORTED_SCHEMA => "This register does not understand this entitlement version.",
        STORAGE_DECRYPTION_FAILED => "Windows could not read this register's protected file. Activate again with a new key.",
        MALFORMED => "The entitlement file is damaged. Activate again with a new key.",
        _ => "This register cannot use the stored entitlement.",
    }
}

fn canonical_json(value: &Value) -> String {
    match value {
        Value::Null => "null".to_string(),
        Value::Bool(true) => "true".to_string(),
        Value::Bool(false) => "false".to_string(),
        Value::Number(number) => number.to_string(),
        Value::String(text) => serde_json::to_string(text).unwrap_or_else(|_| "\"\"".to_string()),
        Value::Array(items) => {
            let parts: Vec<String> = items.iter().map(canonical_json).collect();
            format!("[{}]", parts.join(","))
        }
        Value::Object(map) => canonical_object(map),
    }
}

fn canonical_object(map: &Map<String, Value>) -> String {
    let mut keys: Vec<&String> = map.keys().collect();
    keys.sort();
    let parts: Vec<String> = keys
        .into_iter()
        .map(|key| {
            let encoded = serde_json::to_string(key).unwrap_or_else(|_| "\"\"".to_string());
            format!("{encoded}:{}", canonical_json(&map[key]))
        })
        .collect();
    format!("{{{}}}", parts.join(","))
}

#[cfg(test)]
pub(crate) fn sign_for_test(seed: &[u8; 32], document: &BTreeMap<&str, Value>) -> (String, String, VerifyingKey) {
    use ed25519_dalek::Signer;
    use ed25519_dalek::SigningKey;
    let signing = SigningKey::from_bytes(seed);
    let map = Map::from_iter(document.iter().map(|(key, value)| ((*key).to_string(), value.clone())));
    let payload = canonical_object(&map);
    let signature = STANDARD.encode(signing.sign(payload.as_bytes()).to_bytes());
    (payload, signature, signing.verifying_key())
}

#[cfg(test)]
mod tests {
    use super::*;
    use ed25519_dalek::SigningKey;

    const SEED: [u8; 32] = [7u8; 32];

    fn document(binding: &str) -> BTreeMap<&'static str, Value> {
        let mut map = BTreeMap::new();
        map.insert("schema_version", Value::from(1));
        map.insert("entitlement_id", Value::from("ent-1"));
        map.insert("issuer", Value::from(ISSUER));
        map.insert("audience", Value::from(AUDIENCE));
        map.insert("tenant_id", Value::from("tenant-a"));
        map.insert("branch_id", Value::from("branch-a"));
        map.insert("terminal_id", Value::from("till-a"));
        map.insert("device_binding", Value::from(binding));
        map.insert("plan_id", Value::from("local"));
        map.insert("issued_at", Value::from("2020-01-01T00:00:00Z"));
        map.insert("permanent", Value::Bool(true));
        map.insert("key_id", Value::from("o2-test-1"));
        map.insert("capabilities", Value::Array(vec![]));
        map
    }

    fn expected(binding: &str) -> ExpectedBinding {
        ExpectedBinding {
            tenant_id: "tenant-a".into(),
            branch_id: "branch-a".into(),
            terminal_id: "till-a".into(),
            device_binding: binding.into(),
        }
    }

    fn trusted(public_key: VerifyingKey) -> Vec<TrustedKey> {
        vec![TrustedKey {
            id: "o2-test-1".into(),
            public_key,
        }]
    }

    #[test]
    fn valid_signature_survives_a_moved_clock() {
        let binding = "abc";
        let (payload, signature, public_key) = sign_for_test(&SEED, &document(binding));
        let keys = trusted(public_key);
        let days = 60 * 60 * 24;
        assert_eq!(verify(&payload, &signature, "o2-test-1", &expected(binding), &keys, 0), VALID);
        assert_eq!(
            verify(&payload, &signature, "o2-test-1", &expected(binding), &keys, 10 * days),
            VALID
        );
        assert_eq!(
            verify(&payload, &signature, "o2-test-1", &expected(binding), &keys, -10 * days),
            VALID
        );
    }

    #[test]
    fn tamper_wrong_key_and_bindings_fail_closed() {
        let binding = "abc";
        let (payload, signature, public_key) = sign_for_test(&SEED, &document(binding));
        let keys = trusted(public_key);
        let mut tampered = payload.clone();
        tampered.push(' ');
        assert_eq!(
            verify(&tampered, &signature, "o2-test-1", &expected(binding), &keys, 0),
            INVALID_SIGNATURE
        );
        assert_eq!(
            verify(&payload, &signature, "other-key", &expected(binding), &keys, 0),
            UNKNOWN_KEY
        );
        let other = SigningKey::from_bytes(&[9u8; 32]).verifying_key();
        let wrong_keys = trusted(other);
        assert_eq!(
            verify(&payload, &signature, "o2-test-1", &expected(binding), &wrong_keys, 0),
            INVALID_SIGNATURE
        );
        let mut bad_signature = signature.clone();
        bad_signature.pop();
        assert_eq!(
            verify(&payload, &bad_signature, "o2-test-1", &expected(binding), &keys, 0),
            INVALID_SIGNATURE
        );
        let mut other_device = expected(binding);
        other_device.device_binding = "nope".into();
        assert_eq!(verify(&payload, &signature, "o2-test-1", &other_device, &keys, 0), DEVICE_MISMATCH);
        let mut other_tenant = expected(binding);
        other_tenant.tenant_id = "tenant-b".into();
        assert_eq!(verify(&payload, &signature, "o2-test-1", &other_tenant, &keys, 0), TENANT_MISMATCH);
        let mut other_branch = expected(binding);
        other_branch.branch_id = "branch-b".into();
        assert_eq!(verify(&payload, &signature, "o2-test-1", &other_branch, &keys, 0), BRANCH_MISMATCH);
        let mut other_till = expected(binding);
        other_till.terminal_id = "till-b".into();
        assert_eq!(
            verify(&payload, &signature, "o2-test-1", &other_till, &keys, 0),
            TERMINAL_MISMATCH
        );
    }

    #[test]
    fn malformed_and_unsupported_schema_are_distinct() {
        let binding = "abc";
        let keys = trusted(SigningKey::from_bytes(&SEED).verifying_key());
        assert_eq!(verify("{}", "aaaa", "o2-test-1", &expected(binding), &keys, 0), INVALID_SIGNATURE);
        let mut newer = document(binding);
        newer.insert("schema_version", Value::from(2));
        let (payload, signature, public_key) = sign_for_test(&SEED, &newer);
        assert_eq!(
            verify(&payload, &signature, "o2-test-1", &expected(binding), &trusted(public_key), 0),
            UNSUPPORTED_SCHEMA
        );
        let mut broken = document(binding);
        broken.insert("permanent", Value::Bool(false));
        let (payload, signature, public_key) = sign_for_test(&SEED, &broken);
        assert_eq!(
            verify(&payload, &signature, "o2-test-1", &expected(binding), &trusted(public_key), 0),
            MALFORMED
        );
        assert!(production_trusted_keys().iter().all(|item| item.id != "o2-test-1"));
    }

    #[test]
    fn an_expiry_field_does_not_cancel_a_permanent_entitlement() {
        let binding = "abc";
        let mut map = document(binding);
        map.insert("expires_at", Value::from("2020-01-02T00:00:00Z"));
        let (payload, signature, public_key) = sign_for_test(&SEED, &map);
        assert_eq!(
            verify(&payload, &signature, "o2-test-1", &expected(binding), &trusted(public_key), 9_999_999_999),
            VALID
        );
    }

    fn baseline() -> LocalBaseline {
        LocalBaseline {
            activated: true,
            storage_damaged: false,
            sqlite_open: Some(true),
            queue_readable: true,
            products: 2,
            staff: 1,
            pending: 0,
            capability_snapshot: true,
            server_subscription_blocked: false,
            bootstrap_status: String::new(),
            pull_failed: false,
        }
    }

    #[test]
    fn the_test_signing_key_is_not_a_release_key() {
        assert!(production_trusted_keys().iter().all(|key| key.id != "o2-test-1"));
    }

    #[test]
    fn a_rotation_list_keeps_named_public_keys_and_drops_a_bad_entry() {
        use ed25519_dalek::SigningKey;
        let signing = SigningKey::from_bytes(&[9u8; 32]);
        let public = super::STANDARD.encode(signing.verifying_key().to_bytes());
        let parsed = parse_trusted_key_list(&format!("rotation-a:{public},not-a-key,"));
        assert_eq!(parsed.len(), 1);
        assert_eq!(parsed[0].id, "rotation-a");
    }

    #[test]
    fn readiness_order_is_explicit() {
        let mut damaged = baseline();
        damaged.storage_damaged = true;
        assert_eq!(readiness(VALID, &damaged), REQUIRES_ONLINE_RECOVERY);
        let mut cold = baseline();
        cold.activated = false;
        cold.storage_damaged = false;
        assert_eq!(readiness(MISSING, &cold), NOT_ACTIVATED);
        assert_eq!(readiness(MISSING, &baseline()), "ENTITLEMENT_MISSING");
        assert_eq!(readiness(INVALID_SIGNATURE, &baseline()), "ENTITLEMENT_INVALID");
        let mut unassessed = baseline();
        unassessed.sqlite_open = None;
        assert_eq!(readiness(VALID, &unassessed), ENTITLEMENT_VALID);
        let mut closed = baseline();
        closed.sqlite_open = Some(false);
        assert_eq!(readiness(VALID, &closed), BOOTSTRAP_REQUIRED);
        let mut empty = baseline();
        empty.products = 0;
        assert_eq!(readiness(VALID, &empty), BOOTSTRAP_INCOMPLETE);
        let mut queued = baseline();
        queued.pending = 3;
        assert_eq!(readiness(VALID, &queued), ONLINE_SYNC_REQUIRED);
        assert_eq!(readiness(VALID, &baseline()), OFFLINE_READY);
        let mut downloading = baseline();
        downloading.bootstrap_status = "in_progress".into();
        assert_eq!(readiness(VALID, &downloading), BOOTSTRAP_IN_PROGRESS);
        let mut broken = baseline();
        broken.bootstrap_status = "failed".into();
        assert_eq!(readiness(VALID, &broken), BOOTSTRAP_FAILED);
    }
}
