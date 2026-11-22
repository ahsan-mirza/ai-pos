//! Signed per-terminal stock allocation. An entitlement is not an allocation.

use base64::engine::general_purpose::STANDARD;
use base64::Engine;
use ed25519_dalek::{Signature, Verifier};
use serde_json::Value;

use crate::db::{Db, QueuedEvent};
use crate::entitlement::{trusted_keys, ExpectedBinding};

pub const PURPOSE: &str = "stock_allocation";

pub fn verify_manifest(payload: &str, signature_b64: &str, key_id: &str, expected: &ExpectedBinding) -> Result<Value, String> {
    let key = trusted_keys()
        .into_iter()
        .find(|item| item.id == key_id)
        .ok_or_else(|| "Unknown allocation signing key.".to_string())?;
    let signature_bytes = STANDARD
        .decode(signature_b64.trim())
        .map_err(|_| "Allocation signature is not valid.".to_string())?;
    let signature = Signature::from_slice(&signature_bytes).map_err(|_| "Allocation signature is not valid.".to_string())?;
    key.public_key
        .verify(payload.as_bytes(), &signature)
        .map_err(|_| "Allocation signature is not valid.".to_string())?;
    let document: Value = serde_json::from_str(payload).map_err(|_| "Allocation manifest is not valid.".to_string())?;
    if document["purpose"].as_str() != Some(PURPOSE) || document["schema_version"].as_i64() != Some(1) {
        return Err("This document is not a stock allocation.".into());
    }
    if document["tenant_id"].as_str() != Some(expected.tenant_id.as_str())
        || document["branch_id"].as_str() != Some(expected.branch_id.as_str())
        || document["terminal_id"].as_str() != Some(expected.terminal_id.as_str())
        || document["device_binding"].as_str() != Some(expected.device_binding.as_str())
    {
        return Err("This allocation belongs to another register.".into());
    }
    let quantity = document["quantity"].as_i64().ok_or("Allocation quantity is not valid.")?;
    if quantity < 1 {
        return Err("Allocation quantity is not valid.".into());
    }
    Ok(document)
}

pub fn install(db: &Db, payload: &str, signature: &str, key_id: &str, expected: &ExpectedBinding) -> Result<(), String> {
    let document = verify_manifest(payload, signature, key_id, expected)?;
    let allocation_id = document["allocation_id"].as_str().ok_or("Allocation identity is missing.")?;
    let product_id = document["product_id"].as_str().ok_or("Allocation product is missing.")?;
    let quantity = document["quantity"].as_i64().ok_or("Allocation quantity is not valid.")?;
    db.save_allocation(allocation_id, product_id, quantity, payload, signature, key_id)
}

/// Remaining quantity for manifests that still verify for this register.
/// A bad signature or a foreign device is omitted, so the product is not sellable offline.
pub fn verified_balances(db: &Db, expected: &ExpectedBinding) -> Result<Vec<(String, String, i64)>, String> {
    let rows: Vec<(String, String, i64, i64, String, String, String)> = db.read(|conn| {
        let mut statement = conn
            .prepare(
                "SELECT allocation_id, product_id, quantity_allocated, quantity_consumed, payload, signature, key_id
                 FROM terminal_allocations WHERE status = 'ACTIVE'",
            )
            .map_err(|err| err.to_string())?;
        let mapped = statement
            .query_map([], |row| {
                Ok((
                    row.get(0)?,
                    row.get(1)?,
                    row.get(2)?,
                    row.get(3)?,
                    row.get(4)?,
                    row.get(5)?,
                    row.get(6)?,
                ))
            })
            .map_err(|err| err.to_string())?;
        mapped.collect::<Result<Vec<_>, _>>().map_err(|err| err.to_string())
    })?;
    let mut balances = Vec::new();
    for (allocation_id, product_id, allocated, consumed, payload, signature, key_id) in rows {
        let Ok(document) = verify_manifest(&payload, &signature, &key_id, expected) else {
            continue;
        };
        if document["allocation_id"].as_str() != Some(allocation_id.as_str())
            || document["product_id"].as_str() != Some(product_id.as_str())
        {
            continue;
        }
        let remaining = allocated - consumed;
        if remaining >= 0 {
            balances.push((product_id, allocation_id, remaining));
        }
    }
    Ok(balances)
}

pub fn sell(
    db: &Db,
    allocation_id: &str,
    quantity: i64,
    batch_id: &str,
    events: &[QueuedEvent],
) -> Result<i64, String> {
    db.consume_allocation(allocation_id, quantity, batch_id, events)
}

/// Offline sale commit. Stocked lines draw this register's verified grants.
/// The queue row stores the sequences this commit just assigned. A miss rolls back both.
pub fn commit_queued(db: &Db, expected: &ExpectedBinding, batch_id: &str, events: &[QueuedEvent]) -> Result<(), String> {
    let balances = verified_balances(db, expected)?;
    let mut draws: Vec<(String, String, i64)> = Vec::new();
    for event in events.iter().filter(|event| event.entity_type == "sale") {
        let Some(items) = event.payload.get("items").and_then(|value| value.as_array()) else {
            return Err("The sale has no lines.".into());
        };
        let mut demand: std::collections::BTreeMap<String, i64> = std::collections::BTreeMap::new();
        for item in items {
            let Some(product_id) = item.get("product_id").and_then(|value| value.as_str()) else {
                continue;
            };
            let quantity = item.get("quantity").and_then(|value| value.as_i64()).unwrap_or(0);
            if quantity < 1 {
                return Err("A sale line needs a positive quantity.".into());
            }
            if !stocked(db, product_id)? {
                continue;
            }
            *demand.entry(product_id.to_string()).or_insert(0) += quantity;
        }
        for (product_id, quantity) in demand {
            let mut grants: Vec<&(String, String, i64)> = balances.iter().filter(|row| row.0 == product_id).collect();
            grants.sort_by(|left, right| left.1.cmp(&right.1));
            let available: i64 = grants.iter().map(|row| row.2).sum();
            if grants.is_empty() {
                return Err("ALLOCATION NOT CONFIGURED. Connect to the server and request stock allocation.".into());
            }
            if available < quantity {
                return Err("Available offline allocation is not enough for this sale.".into());
            }
            let mut left = quantity;
            for grant in grants {
                if left == 0 {
                    break;
                }
                let take = left.min(grant.2);
                if take > 0 {
                    draws.push((grant.1.clone(), product_id.clone(), take));
                    left -= take;
                }
            }
            if let Some(claimed) = event.payload.get("allocations").and_then(|value| value.as_array()) {
                if !claimed.is_empty() {
                    for claim in claimed {
                        let claim_product = claim.get("product_id").and_then(|value| value.as_str()).unwrap_or("");
                        if claim_product != product_id {
                            continue;
                        }
                        let claim_id = claim.get("allocation_id").and_then(|value| value.as_str()).unwrap_or("");
                        let claim_qty = claim.get("quantity").and_then(|value| value.as_i64()).unwrap_or(-1);
                        let matches = draws.iter().any(|draw| draw.0 == claim_id && draw.1 == product_id && draw.2 == claim_qty);
                        if !matches {
                            return Err("The sale allocation does not match this register's grant.".into());
                        }
                    }
                }
            }
        }
    }
    db.enqueue_consuming(batch_id, events, &draws)
}

pub fn requires_grant(db: &Db, events: &[QueuedEvent]) -> Result<bool, String> {
    for event in events.iter().filter(|event| event.entity_type == "sale") {
        let Some(items) = event.payload.get("items").and_then(|value| value.as_array()) else {
            continue;
        };
        for item in items {
            let Some(product_id) = item.get("product_id").and_then(|value| value.as_str()) else {
                continue;
            };
            if stocked(db, product_id)? {
                return Ok(true);
            }
        }
    }
    Ok(false)
}

fn stocked(db: &Db, product_id: &str) -> Result<bool, String> {
    let row = db.read(|conn| {
        conn.query_row(
            "SELECT is_service, is_open_price, has_recipe, is_serialized FROM products WHERE id = ?1",
            rusqlite::params![product_id],
            |row| Ok((row.get::<_, i64>(0)?, row.get::<_, i64>(1)?, row.get::<_, i64>(2)?, row.get::<_, i64>(3)?)),
        )
        .map(Some)
        .or_else(|err| match err {
            rusqlite::Error::QueryReturnedNoRows => Ok(None),
            other => Err(other.to_string()),
        })
    })?;
    let Some((is_service, is_open_price, has_recipe, is_serialized)) = row else {
        return Err("This product is not on this register.".into());
    };
    Ok(is_service == 0 && is_open_price == 0 && has_recipe == 0 && is_serialized == 0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use ed25519_dalek::Signer;

    fn binding() -> ExpectedBinding {
        ExpectedBinding {
            tenant_id: "tenant-1".into(),
            branch_id: "branch-1".into(),
            terminal_id: "till-a".into(),
            device_binding: "ab".repeat(32),
        }
    }

    fn signed(payload: &str) -> (String, String) {
        let key = ed25519_dalek::SigningKey::from_bytes(&[7u8; 32]);
        let signature = STANDARD.encode(key.sign(payload.as_bytes()).to_bytes());
        (signature, "o2-test-1".into())
    }

    fn manifest(terminal: &str, quantity: i64) -> String {
        format!(
            r#"{{"allocation_id":"alloc-1","allocation_version":1,"branch_id":"branch-1","device_binding":"{binding}","issuer":"axizpos","manifest_id":"manifest-1","policy_version":1,"product_id":"product-1","purpose":"stock_allocation","quantity":{quantity},"schema_version":1,"tenant_id":"tenant-1","terminal_id":"{terminal}","unit":"each"}}"#,
            binding = "ab".repeat(32),
        )
    }

    #[test]
    fn a_tampered_or_foreign_manifest_is_rejected() {
        let payload = manifest("till-a", 40);
        let (signature, key_id) = signed(&payload);
        assert!(verify_manifest(&payload, &signature, &key_id, &binding()).is_ok());
        let mut tampered = payload.clone();
        tampered = tampered.replace("40", "41");
        assert!(verify_manifest(&tampered, &signature, &key_id, &binding()).is_err());
        let other = binding();
        let foreign = ExpectedBinding { terminal_id: "till-b".into(), ..other };
        assert!(verify_manifest(&payload, &signature, &key_id, &foreign).is_err());
        let entitlement = r#"{"audience":"axizpos-register","purpose":"entitlement","schema_version":1}"#;
        let (entitlement_signature, _) = signed(entitlement);
        assert!(verify_manifest(entitlement, &entitlement_signature, &key_id, &binding()).is_err());
    }

    #[test]
    fn a_sale_and_its_allocation_commit_together_and_cannot_overdraw() {
        let path = std::env::temp_dir().join(format!("axiz-o6-{}.db", std::process::id()));
        let _ = std::fs::remove_file(&path);
        let db = Db::open(&path).unwrap();
        let payload = manifest("till-a", 40);
        let (signature, key_id) = signed(&payload);
        install(&db, &payload, &signature, &key_id, &binding()).unwrap();
        let event = QueuedEvent {
            id: "event-1".into(),
            idempotency_key: "sale-1".into(),
            entity_type: "sale".into(),
            operation: "upsert".into(),
            payload: serde_json::json!({"total_cents": 100, "allocations": [{"allocation_id": "alloc-1", "quantity": 30}]}),
            occurred_at: "2026-11-22T00:00:00Z".into(),
        };
        assert_eq!(sell(&db, "alloc-1", 30, "batch-1", &[event]).unwrap(), 1);
        assert_eq!(db.allocation_remaining("alloc-1").unwrap(), Some(10));
        assert_eq!(db.pending_count().unwrap(), 1);
        let over = QueuedEvent {
            id: "event-2".into(),
            idempotency_key: "sale-2".into(),
            entity_type: "sale".into(),
            operation: "upsert".into(),
            payload: serde_json::json!({"total_cents": 50}),
            occurred_at: "2026-11-22T00:01:00Z".into(),
        };
        assert!(sell(&db, "alloc-1", 11, "batch-2", &[over]).is_err());
        assert_eq!(db.allocation_remaining("alloc-1").unwrap(), Some(10));
        assert_eq!(db.pending_count().unwrap(), 1);
        drop(db);
        let db = Db::open(&path).unwrap();
        assert_eq!(db.allocation_remaining("alloc-1").unwrap(), Some(10));
        let stored: String = db
            .read(|conn| {
                conn.query_row(
                    "SELECT payload FROM sync_queue WHERE idempotency_key = 'sale-1'",
                    [],
                    |row| row.get(0),
                )
                .map_err(|err| err.to_string())
            })
            .unwrap();
        assert!(stored.contains("\"total_cents\":100"));
        let balances = verified_balances(&db, &binding()).unwrap();
        assert_eq!(balances, vec![("product-1".into(), "alloc-1".into(), 10)]);
        db.read(|conn| {
            conn.execute(
                "UPDATE terminal_allocations SET payload = replace(payload, 'product-1', 'product-2') WHERE allocation_id = 'alloc-1'",
                [],
            )
            .map_err(|err| err.to_string())?;
            Ok(())
        })
        .unwrap();
        assert!(verified_balances(&db, &binding()).unwrap().is_empty());
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn an_offline_sale_writes_the_grant_sequence_and_an_overdraw_writes_nothing() {
        let path = std::env::temp_dir().join(format!("axiz-o82-{}.db", std::process::id()));
        let _ = std::fs::remove_file(&path);
        let db = Db::open(&path).unwrap();
        db.read(|conn| {
            conn.execute(
                "INSERT INTO products (id, store_id, sku, barcode, name, category, price_cents, currency, is_serialized, stock_quantity)
                 VALUES ('product-1', 'branch-1', 'SKU-1', 'BAR-1', 'Rice', 'Grocery', 100, 'USD', 0, 100)",
                [],
            )
            .map_err(|err| err.to_string())?;
            Ok(())
        })
        .unwrap();
        let payload = manifest("till-a", 40);
        let (signature, key_id) = signed(&payload);
        install(&db, &payload, &signature, &key_id, &binding()).unwrap();
        let event = QueuedEvent {
            id: "event-live".into(),
            idempotency_key: "sale-live".into(),
            entity_type: "sale".into(),
            operation: "upsert".into(),
            payload: serde_json::json!({
                "items": [{"product_id": "product-1", "quantity": 30}],
                "total_cents": 100
            }),
            occurred_at: "2026-11-22T00:00:00Z".into(),
        };
        commit_queued(&db, &binding(), "batch-live", &[event]).unwrap();
        assert_eq!(db.allocation_remaining("alloc-1").unwrap(), Some(10));
        let stored: String = db
            .read(|conn| {
                conn.query_row("SELECT payload FROM sync_queue WHERE idempotency_key = 'sale-live'", [], |row| row.get(0))
                    .map_err(|err| err.to_string())
            })
            .unwrap();
        assert!(stored.contains("\"sequence\":1"));
        assert!(stored.contains("\"quantity\":30"));
        let over = QueuedEvent {
            id: "event-over".into(),
            idempotency_key: "sale-over".into(),
            entity_type: "sale".into(),
            operation: "upsert".into(),
            payload: serde_json::json!({"items": [{"product_id": "product-1", "quantity": 11}]}),
            occurred_at: "2026-11-22T00:02:00Z".into(),
        };
        assert!(commit_queued(&db, &binding(), "batch-over", &[over]).is_err());
        assert_eq!(db.allocation_remaining("alloc-1").unwrap(), Some(10));
        assert_eq!(db.pending_count().unwrap(), 1);
        let _ = std::fs::remove_file(&path);
    }
}
