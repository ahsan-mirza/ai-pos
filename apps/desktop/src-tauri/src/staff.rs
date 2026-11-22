//! Local staff administration. Pending people exist on this register only until the server accepts them.
//!
//! The financial sync_queue is not used. PINs are Argon2 verifiers, never stored in clear text.

use rusqlite::params;

use crate::auth::hash_pin;
use crate::db::Db;

pub const PENDING: &str = "LOCAL ACTIVE · PENDING SERVER PROVISIONING";

pub struct NewStaff {
    pub actor_id: String,
    pub actor_role: String,
    pub actor_store_id: String,
    /// `Some` is a cap from a verified entitlement. `None` is a verified plan with no staff cap.
    pub seat_limit: Option<i64>,
    /// False when the entitlement was missing or did not verify. Creation is refused.
    pub seat_trusted: bool,
    pub tenant_id: String,
    pub terminal_id: String,
    pub user_id: String,
    pub username: String,
    pub full_name: String,
    pub store_id: String,
    pub role_name: String,
    pub pin: String,
    pub event_id: String,
}

fn permissions_for(role: &str) -> Result<&'static str, String> {
    match role {
        "Cashier" => Ok("[\"pos:access\"]"),
        "Store Manager" => Ok("[\"pos:access\",\"users:create\",\"users:update\",\"inventory:adjust_stock\"]"),
        "Super Admin" | "Platform Super Admin" => Err("This register cannot grant that role.".into()),
        _ => Err("That role is not available on this register.".into()),
    }
}

fn assert_actor(actor_role: &str, requested: &str, actor_store: &str, staff_store: &str) -> Result<(), String> {
    if actor_store != staff_store {
        return Err("You can only manage staff at your own branch.".into());
    }
    match actor_role {
        "Store Manager" if requested == "Cashier" => Ok(()),
        "Super Admin" if requested == "Cashier" || requested == "Store Manager" => Ok(()),
        "Store Manager" | "Super Admin" => Err("You cannot grant that role.".into()),
        _ => Err("You cannot manage staff.".into()),
    }
}

pub fn create_local(db: &Db, staff: NewStaff) -> Result<String, String> {
    if staff.username.trim().is_empty() || staff.full_name.trim().is_empty() {
        return Err("A staff member needs a name and a username.".into());
    }
    assert_actor(&staff.actor_role, &staff.role_name, &staff.actor_store_id, &staff.store_id)?;
    let permissions = permissions_for(&staff.role_name)?;
    if staff.pin.len() != 4 || !staff.pin.chars().all(|item| item.is_ascii_digit()) {
        return Err("A register PIN is four digits.".into());
    }
    let verifier = hash_pin(&staff.pin)?;
    if verifier.contains(&staff.pin) {
        return Err("The PIN verifier is not safe to store.".into());
    }
    let status_label = PENDING.to_string();
    db.transaction(|tx| {
        if !staff.seat_trusted {
            return Err("Staff seats need a trusted entitlement. Connect this register and try again.".into());
        }
        let active: i64 = tx
            .query_row(
                "SELECT COUNT(*) FROM cached_users WHERE is_active = 1 AND provisioning_status != 'rejected'",
                [],
                |row| row.get(0),
            )
            .map_err(|err| err.to_string())?;
        if staff.seat_limit.is_some_and(|limit| active >= limit) {
            return Err("The staff seat limit is already used.".into());
        }
        let payload = serde_json::json!({
            "user_id": staff.user_id,
            "username": staff.username,
            "full_name": staff.full_name,
            "store_id": staff.store_id,
            "role_name": staff.role_name,
            "pin_verifier": verifier,
        });
        let body = serde_json::to_string(&payload).map_err(|err| err.to_string())?;
        if body.contains(&staff.pin) {
            return Err("The provisioning record must not contain the PIN.".into());
        }
        tx.execute(
            "INSERT INTO cached_users (
                user_id, username, full_name, store_id, role_name, permissions, pin_hash,
                failed_attempts, locked_until, updated_at, max_discount_bps, addon_modules,
                provisioning_status, is_active
             ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, 0, NULL, ?8, 0, '[]', 'pending', 1)",
            params![
                staff.user_id,
                staff.username,
                staff.full_name,
                staff.store_id,
                staff.role_name,
                permissions,
                verifier,
                1_i64
            ],
        )
        .map_err(|err| err.to_string())?;
        tx.execute(
            "INSERT INTO staff_provisioning (
                id, user_id, operation, payload, status, last_error, created_at,
                tenant_id, origin_terminal_id, schema_version, base_version
             ) VALUES (?1, ?2, 'create', ?3, 'pending', NULL, ?4, ?5, ?6, 1, NULL)",
            params![
                staff.event_id,
                staff.user_id,
                body,
                "2026-11-22T00:00:00Z",
                staff.tenant_id,
                staff.terminal_id
            ],
        )
        .map_err(|err| err.to_string())?;
        tx.execute(
            "INSERT INTO staff_audit (actor_id, user_id, operation, status, created_at) VALUES (?1, ?2, 'create', 'pending', ?3)",
            params![staff.actor_id, staff.user_id, "2026-11-22T00:00:00Z"],
        )
        .map_err(|err| err.to_string())?;
        Ok(())
    })?;
    Ok(status_label)
}

pub fn disable_local(db: &Db, actor_id: &str, actor_role: &str, user_id: &str, event_id: &str) -> Result<(), String> {
    if actor_role != "Store Manager" && actor_role != "Super Admin" {
        return Err("You cannot manage staff.".into());
    }
    if actor_id == user_id {
        return Err("You cannot disable your own account.".into());
    }
    db.transaction(|tx| {
        let changed = tx
            .execute(
                "UPDATE cached_users SET is_active = 0 WHERE user_id = ?1 AND is_active = 1",
                params![user_id],
            )
            .map_err(|err| err.to_string())?;
        if changed != 1 {
            return Err("That staff member is not active on this register.".into());
        }
        tx.execute(
            "INSERT INTO staff_provisioning (id, user_id, operation, payload, status, last_error, created_at)
             VALUES (?1, ?2, 'disable', ?3, 'pending', NULL, ?4)",
            params![event_id, user_id, format!("{{\"user_id\":\"{user_id}\"}}"), "2026-11-22T00:00:00Z"],
        )
        .map_err(|err| err.to_string())?;
        tx.execute(
            "INSERT INTO staff_audit (actor_id, user_id, operation, status, created_at) VALUES (?1, ?2, 'disable', 'pending', ?3)",
            params![actor_id, user_id, "2026-11-22T00:00:00Z"],
        )
        .map_err(|err| err.to_string())?;
        Ok(())
    })
}

pub fn mark_provisioning(db: &Db, event_id: &str, status: &str, error: Option<&str>) -> Result<(), String> {
    if status == "rejected" {
        db.transaction(|tx| {
            let user_id: String = tx
                .query_row(
                    "SELECT user_id FROM staff_provisioning WHERE id = ?1",
                    params![event_id],
                    |row| row.get(0),
                )
                .map_err(|err| err.to_string())?;
            let operation: String = tx
                .query_row(
                    "SELECT operation FROM staff_provisioning WHERE id = ?1",
                    params![event_id],
                    |row| row.get(0),
                )
                .map_err(|err| err.to_string())?;
            tx.execute(
                "UPDATE staff_provisioning SET status = 'rejected', last_error = ?2 WHERE id = ?1",
                params![event_id, error.unwrap_or("The server rejected this staff change.")],
            )
            .map_err(|err| err.to_string())?;
            if operation == "create" {
                tx.execute(
                    "UPDATE cached_users SET provisioning_status = 'rejected', is_active = 0 WHERE user_id = ?1",
                    params![user_id],
                )
                .map_err(|err| err.to_string())?;
            }
            Ok(())
        })
    } else if status == "accepted" {
        db.transaction(|tx| {
            let user_id: String = tx
                .query_row(
                    "SELECT user_id FROM staff_provisioning WHERE id = ?1",
                    params![event_id],
                    |row| row.get(0),
                )
                .map_err(|err| err.to_string())?;
            tx.execute(
                "UPDATE staff_provisioning SET status = 'accepted', last_error = NULL WHERE id = ?1",
                params![event_id],
            )
            .map_err(|err| err.to_string())?;
            tx.execute(
                "UPDATE cached_users SET provisioning_status = 'accepted' WHERE user_id = ?1 AND provisioning_status = 'pending'",
                params![user_id],
            )
            .map_err(|err| err.to_string())?;
            Ok(())
        })
    } else if status == "conflict" {
        db.transaction(|tx| {
            tx.execute(
                "UPDATE staff_provisioning SET status = 'provisioning_conflict', last_error = ?2 WHERE id = ?1",
                params![event_id, error.unwrap_or("The server already has a different version of this event.")],
            )
            .map_err(|err| err.to_string())?;
            Ok(())
        })
    } else if status == "retryable" {
        db.transaction(|tx| {
            tx.execute(
                "UPDATE staff_provisioning SET status = 'retryable', last_error = ?2 WHERE id = ?1 AND status IN ('pending', 'retryable', 'awaiting_authentication')",
                params![event_id, error.unwrap_or("The server could not be reached. The same event will be sent again.")],
            )
            .map_err(|err| err.to_string())?;
            Ok(())
        })
    } else if status == "awaiting_authentication" || status == "permission_denied" {
        let fallback = if status == "awaiting_authentication" {
            "A signed-in online session is required. This change stays on this register."
        } else {
            "The signed-in user cannot provision staff. This event will not be retried."
        };
        db.transaction(|tx| {
            tx.execute(
                "UPDATE staff_provisioning SET status = ?2, last_error = ?3 WHERE id = ?1",
                params![event_id, status, error.unwrap_or(fallback)],
            )
            .map_err(|err| err.to_string())?;
            Ok(())
        })
    } else {
        Err("Unknown provisioning status.".into())
    }
}

/// Delivery decision for one provisioning response. The local cashier row is not changed here.
pub fn classify_provision_response(status: u16, code: &str, body_status: &str) -> &'static str {
    if (200..300).contains(&status) {
        return match body_status {
            "accepted" => "accepted",
            "duplicate" => "accepted",
            _ => "retryable",
        };
    }
    if status == 401 {
        return "awaiting_authentication";
    }
    if status == 403 {
        return "permission_denied";
    }
    if status == 409 && code == "provisioning_conflict" {
        return "conflict";
    }
    if status == 409 || status == 422 {
        return "rejected";
    }
    "retryable"
}

/// No online access token is available. Pending rows wait. The local cashier stays active.
pub fn hold_for_authentication(db: &Db) -> Result<(), String> {
    db.transaction(|tx| {
        tx.execute(
            "UPDATE staff_provisioning SET status = 'awaiting_authentication', last_error = ?1 WHERE status IN ('pending', 'retryable')",
            params!["A signed-in online session is required. This change stays on this register."],
        )
        .map_err(|err| err.to_string())?;
        Ok(())
    })
}

pub fn edit_local(
    db: &Db,
    actor_id: &str,
    actor_role: &str,
    actor_store_id: &str,
    user_id: &str,
    full_name: &str,
    role_name: &str,
    event_id: &str,
    tenant_id: &str,
    terminal_id: &str,
) -> Result<(), String> {
    let permissions = permissions_for(role_name)?;
    db.transaction(|tx| {
        let (store_id, current_role): (String, String) = tx
            .query_row(
                "SELECT store_id, role_name FROM cached_users WHERE user_id = ?1",
                params![user_id],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .map_err(|_| "That staff member is not on this register.".to_string())?;
        assert_actor(actor_role, role_name, actor_store_id, &store_id)?;
        if actor_id == user_id && role_name != current_role {
            return Err("You cannot change your own role.".into());
        }
        let name = full_name.trim();
        if name.is_empty() {
            return Err("A display name is required.".into());
        }
        tx.execute(
            "UPDATE cached_users SET full_name = ?2, role_name = ?3, permissions = ?4 WHERE user_id = ?1",
            params![user_id, name, role_name, permissions],
        )
        .map_err(|err| err.to_string())?;
        let payload = serde_json::json!({"user_id": user_id, "full_name": name, "role_name": role_name}).to_string();
        tx.execute(
            "INSERT INTO staff_provisioning (
                id, user_id, operation, payload, status, last_error, created_at,
                tenant_id, origin_terminal_id, schema_version, base_version
             ) VALUES (?1, ?2, 'update', ?3, 'pending', NULL, ?4, ?5, ?6, 1, NULL)",
            params![event_id, user_id, payload, "2026-11-22T00:00:00Z", tenant_id, terminal_id],
        )
        .map_err(|err| err.to_string())?;
        tx.execute(
            "INSERT INTO staff_audit (actor_id, user_id, operation, status, created_at) VALUES (?1, ?2, 'update', 'pending', ?3)",
            params![actor_id, user_id, "2026-11-22T00:00:00Z"],
        )
        .map_err(|err| err.to_string())?;
        Ok(())
    })
}

pub fn reset_pin_local(
    db: &Db,
    actor_id: &str,
    actor_role: &str,
    user_id: &str,
    pin: &str,
    event_id: &str,
    tenant_id: &str,
    terminal_id: &str,
) -> Result<(), String> {
    if actor_role != "Store Manager" && actor_role != "Super Admin" {
        return Err("You cannot manage staff.".into());
    }
    if pin.len() != 4 || !pin.chars().all(|item| item.is_ascii_digit()) {
        return Err("A register PIN is four digits.".into());
    }
    let verifier = hash_pin(pin)?;
    if verifier.contains(pin) {
        return Err("The PIN verifier is not safe to store.".into());
    }
    db.transaction(|tx| {
        let changed = tx
            .execute(
                "UPDATE cached_users SET pin_hash = ?2, failed_attempts = 0, locked_until = NULL WHERE user_id = ?1",
                params![user_id, verifier],
            )
            .map_err(|err| err.to_string())?;
        if changed != 1 {
            return Err("That staff member is not on this register.".into());
        }
        let payload = serde_json::json!({"user_id": user_id, "pin_verifier": verifier});
        let body = serde_json::to_string(&payload).map_err(|err| err.to_string())?;
        if body.contains(pin) {
            return Err("The provisioning record must not contain the PIN.".into());
        }
        tx.execute(
            "INSERT INTO staff_provisioning (
                id, user_id, operation, payload, status, last_error, created_at,
                tenant_id, origin_terminal_id, schema_version, base_version
             ) VALUES (?1, ?2, 'pin_reset', ?3, 'pending', NULL, ?4, ?5, ?6, 1, NULL)",
            params![event_id, user_id, body, "2026-11-22T00:00:00Z", tenant_id, terminal_id],
        )
        .map_err(|err| err.to_string())?;
        tx.execute(
            "INSERT INTO staff_audit (actor_id, user_id, operation, status, created_at) VALUES (?1, ?2, 'pin_reset', 'pending', ?3)",
            params![actor_id, user_id, "2026-11-22T00:00:00Z"],
        )
        .map_err(|err| err.to_string())?;
        Ok(())
    })
}

pub struct OutboxEvent {
    pub id: String,
    pub operation: String,
    pub payload: String,
    pub origin_terminal_id: String,
    pub base_version: String,
}

pub fn pending_outbox(db: &Db) -> Result<Vec<OutboxEvent>, String> {
    db.read(|conn| {
        let mut statement = conn
            .prepare(
                "SELECT id, operation, payload, COALESCE(origin_terminal_id, ''), COALESCE(base_version, '')
                 FROM staff_provisioning WHERE status IN ('pending', 'retryable', 'awaiting_authentication') ORDER BY created_at",
            )
            .map_err(|err| err.to_string())?;
        let rows = statement
            .query_map([], |row| {
                Ok(OutboxEvent {
                    id: row.get(0)?,
                    operation: row.get(1)?,
                    payload: row.get(2)?,
                    origin_terminal_id: row.get(3)?,
                    base_version: row.get(4)?,
                })
            })
            .map_err(|err| err.to_string())?;
        rows.collect::<Result<Vec<_>, _>>().map_err(|err| err.to_string())
    })
}

/// Another terminal may store a staff member only after the server accepted the verifier.
pub fn import_accepted(
    db: &Db,
    user_id: &str,
    username: &str,
    verifier: &str,
    store_id: &str,
    role_name: &str,
    active: bool,
) -> Result<(), String> {
    if !verifier.starts_with("$argon2") {
        return Err("Staff credentials must arrive as an Argon2 verifier.".into());
    }
    let permissions = permissions_for(role_name)?;
    let is_active = i64::from(active);
    db.transaction(|tx| {
        tx.execute(
            "INSERT INTO cached_users (
                user_id, username, full_name, store_id, role_name, permissions, pin_hash,
                failed_attempts, locked_until, updated_at, max_discount_bps, addon_modules,
                provisioning_status, is_active
             ) VALUES (?1, ?2, ?2, ?3, ?4, ?5, ?6, 0, NULL, 1, 0, '[]', 'accepted', ?7)",
            params![user_id, username, store_id, role_name, permissions, verifier, is_active],
        )
        .map_err(|err| err.to_string())?;
        Ok(())
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::auth::hash_pin;

    fn open() -> (Db, std::path::PathBuf) {
        let path = std::env::temp_dir().join(format!("axiz-o7-{}-{}.db", std::process::id(), rand_suffix()));
        let _ = std::fs::remove_file(&path);
        (Db::open(&path).unwrap(), path)
    }

    fn rand_suffix() -> u32 {
        use std::time::{SystemTime, UNIX_EPOCH};
        SystemTime::now().duration_since(UNIX_EPOCH).unwrap().subsec_nanos()
    }

    fn sample(role: &str, pin: &str, seats: Option<i64>) -> NewStaff {
        NewStaff {
            actor_id: "manager".into(),
            actor_role: "Store Manager".into(),
            actor_store_id: "branch-a".into(),
            seat_limit: seats,
            seat_trusted: seats.is_some(),
            tenant_id: "tenant-a".into(),
            terminal_id: "till-a".into(),
            user_id: "cashier-local".into(),
            username: "new.cashier".into(),
            full_name: "New Cashier".into(),
            store_id: "branch-a".into(),
            role_name: role.into(),
            pin: pin.into(),
            event_id: "event-create-1".into(),
        }
    }

    #[test]
    fn a_local_cashier_is_pending_and_the_pin_is_not_stored() {
        let (db, path) = open();
        let label = create_local(&db, sample("Cashier", "1357", Some(2))).unwrap();
        assert_eq!(label, PENDING);
        let stored: String = db
            .read(|conn| {
                conn.query_row("SELECT pin_hash FROM cached_users WHERE user_id = 'cashier-local'", [], |row| row.get(0))
                    .map_err(|err| err.to_string())
            })
            .unwrap();
        assert!(stored.starts_with("$argon2"));
        assert!(!stored.contains("1357"));
        let payload: String = db
            .read(|conn| {
                conn.query_row("SELECT payload FROM staff_provisioning WHERE id = 'event-create-1'", [], |row| row.get(0))
                    .map_err(|err| err.to_string())
            })
            .unwrap();
        assert!(!payload.contains("1357"));
        assert!(payload.contains("pin_verifier"));
        let status: String = db
            .read(|conn| {
                conn.query_row(
                    "SELECT provisioning_status FROM cached_users WHERE user_id = 'cashier-local'",
                    [],
                    |row| row.get(0),
                )
                .map_err(|err| err.to_string())
            })
            .unwrap();
        assert_eq!(status, "pending");
        let mut blank = sample("Cashier", "1357", Some(2));
        blank.username = " ".into();
        blank.user_id = "cashier-blank".into();
        blank.event_id = "event-blank".into();
        assert!(create_local(&db, blank).unwrap_err().contains("name and a username"));
        assert!(create_local(&db, sample("Super Admin", "1357", Some(2))).is_err());
        assert!(create_local(&db, sample("Cashier", "1357", Some(1))).is_err());
        assert!(create_local(&db, sample("Cashier", "1357", None)).is_err());
        drop(db);
        let db = Db::open(&path).unwrap();
        assert_eq!(
            db.cached_user("new.cashier").unwrap().unwrap().provisioning_status,
            "pending"
        );
        let _ = std::fs::remove_file(&path);
        let _ = hash_pin("0000");
    }

    #[test]
    fn disablement_survives_a_rejected_provisioning_event() {
        let (db, path) = open();
        create_local(&db, sample("Cashier", "2468", Some(5))).unwrap();
        disable_local(&db, "manager", "Store Manager", "cashier-local", "event-disable-1").unwrap();
        assert_eq!(db.cached_user("new.cashier").unwrap().unwrap().is_active, 0);
        mark_provisioning(&db, "event-disable-1", "rejected", Some("The manager no longer has this permission.")).unwrap();
        assert_eq!(db.cached_user("new.cashier").unwrap().unwrap().is_active, 0);
        let audits: i64 = db
            .read(|conn| {
                conn.query_row("SELECT COUNT(*) FROM staff_audit", [], |row| row.get(0))
                    .map_err(|err| err.to_string())
            })
            .unwrap();
        assert!(audits >= 2);
        drop(db);
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn another_terminal_receives_the_verifier_only_after_acceptance() {
        let (origin, origin_path) = open();
        create_local(&origin, sample("Cashier", "1357", Some(5))).unwrap();
        let verifier: String = origin
            .read(|conn| {
                conn.query_row("SELECT pin_hash FROM cached_users WHERE user_id = 'cashier-local'", [], |row| row.get(0))
                    .map_err(|err| err.to_string())
            })
            .unwrap();
        let (other, other_path) = open();
        assert!(other.cached_user("new.cashier").unwrap().is_none());
        import_accepted(&other, "cashier-local", "new.cashier", &verifier, "branch-a", "Cashier", true).unwrap();
        assert!(import_accepted(&other, "x", "x", "not-a-verifier", "branch-a", "Cashier", true).is_err());
        assert!(import_accepted(&other, "y", "y", &verifier, "branch-a", "Platform Super Admin", true).is_err());
        let row = other.cached_user("new.cashier").unwrap().unwrap();
        assert_eq!(row.provisioning_status, "accepted");
        assert!(row.pin_hash.starts_with("$argon2"));
        assert!(crate::auth::tests_verify_pin("1357", &row.pin_hash));
        assert!(!crate::auth::tests_verify_pin("9999", &row.pin_hash));
        drop(origin);
        drop(other);
        let _ = std::fs::remove_file(&origin_path);
        let _ = std::fs::remove_file(&other_path);
    }

    #[test]
    fn a_missing_token_or_401_keeps_the_cashier_and_the_original_event() {
        let (db, path) = open();
        create_local(&db, sample("Cashier", "1357", Some(5))).unwrap();
        assert_eq!(classify_provision_response(401, "", ""), "awaiting_authentication");
        assert_eq!(classify_provision_response(403, "forbidden", ""), "permission_denied");
        assert_eq!(classify_provision_response(200, "", "duplicate"), "accepted");
        assert_eq!(classify_provision_response(200, "", "accepted"), "accepted");
        assert_eq!(classify_provision_response(409, "provisioning_conflict", ""), "conflict");
        assert_eq!(classify_provision_response(422, "invalid_verifier", ""), "rejected");
        assert_eq!(classify_provision_response(503, "", ""), "retryable");
        hold_for_authentication(&db).unwrap();
        let waiting = pending_outbox(&db).unwrap();
        assert_eq!(waiting.len(), 1);
        assert_eq!(waiting[0].id, "event-create-1");
        let person = db.cached_user("new.cashier").unwrap().unwrap();
        assert_eq!(person.is_active, 1);
        assert_eq!(person.provisioning_status, "pending");
        mark_provisioning(&db, "event-create-1", "permission_denied", Some("You cannot manage staff.")).unwrap();
        assert!(pending_outbox(&db).unwrap().is_empty());
        let still = db.cached_user("new.cashier").unwrap().unwrap();
        assert_eq!(still.is_active, 1);
        assert_eq!(still.provisioning_status, "pending");
        mark_provisioning(&db, "event-create-1", "retryable", Some("The server could not be reached.")).unwrap();
        let status: String = db
            .read(|conn| {
                conn.query_row("SELECT status FROM staff_provisioning WHERE id = 'event-create-1'", [], |row| row.get(0))
                    .map_err(|err| err.to_string())
            })
            .unwrap();
        assert_eq!(status, "permission_denied");
        drop(db);
        let _ = std::fs::remove_file(&path);
    }
}
