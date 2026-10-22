use std::collections::HashMap;
use std::sync::Mutex;

use serde_json::Value;

use crate::auth::{self, CashierProfile, Session};
use crate::db::{Db, QueuedEvent};
use crate::sync::DesktopConfig;

/// Approvals stay valid for the rest of a busy wholesale cart, then must be re-entered.
const APPROVAL_TTL_SECS: i64 = 30 * 60;
const POS_PRICE_OVERRIDE: &str = "pos:price_override";
const POS_BELOW_FLOOR_OVERRIDE: &str = "pos:below_floor_override";
const POS_DISCOUNT: &str = "pos:discount";
const POS_CREDIT_SALE: &str = "pos:credit_sale";
const CUSTOMERS_MANAGE: &str = "customers:manage";

/// (approver id, permission) -> verified at.
pub type CheckoutApprovals = Mutex<HashMap<(String, String), i64>>;

fn allowed_permission(permission: &str) -> bool {
    matches!(permission, POS_PRICE_OVERRIDE | POS_BELOW_FLOOR_OVERRIDE | POS_DISCOUNT | CUSTOMERS_MANAGE)
}

fn action_label(permission: &str) -> &'static str {
    match permission {
        POS_PRICE_OVERRIDE => "price overrides",
        POS_BELOW_FLOOR_OVERRIDE => "prices below the margin floor",
        POS_DISCOUNT => "discounts",
        _ => "credit limit overrides",
    }
}

/// Verifies a manager PIN for a checkout override without switching the register's session.
pub fn approve(
    db: &Db,
    config: &DesktopConfig,
    approvals: &CheckoutApprovals,
    session: &Session,
    username: &str,
    pin: &str,
    permission: &str,
) -> Result<CashierProfile, String> {
    if !allowed_permission(permission) {
        return Err("Unknown approval type.".into());
    }
    let approver = auth::pin_login(db, config, username, pin)?.user;
    if !approver.permissions.iter().any(|item| item == permission) {
        return Err(format!("{} cannot approve {}.", approver.full_name, action_label(permission)));
    }
    if let (Some(store), Some(own)) = (&session.user.store_id, &approver.store_id) {
        if store != own {
            return Err(format!("{} is not assigned to this store.", approver.full_name));
        }
    }
    approvals
        .lock()
        .map_err(|err| err.to_string())?
        .insert((approver.id.clone(), permission.to_string()), auth::now_secs());
    Ok(approver)
}

fn fresh(approvals: &HashMap<(String, String), i64>, session: &Session, approver: &str, permission: &str) -> bool {
    if approver == session.user.id && session.user.permissions.iter().any(|item| item == permission) {
        return true;
    }
    approvals
        .get(&(approver.to_string(), permission.to_string()))
        .is_some_and(|verified| auth::now_secs() - verified <= APPROVAL_TTL_SECS)
}

/// Every override named in a queued sale must come from a manager verified on this register.
pub fn check_sale(approvals: &CheckoutApprovals, session: &Session, events: &[QueuedEvent]) -> Result<(), String> {
    let guard = approvals.lock().map_err(|err| err.to_string())?;
    for event in events.iter().filter(|event| event.entity_type == "sale") {
        let payload = &event.payload;
        let items = payload.get("items").and_then(Value::as_array).cloned().unwrap_or_default();
        for item in &items {
            for (field, permission, label) in [
                ("price_override", POS_PRICE_OVERRIDE, "Price override"),
                ("below_floor_override", POS_BELOW_FLOOR_OVERRIDE, "Below-floor price"),
                ("discount_override", POS_DISCOUNT, "Discount"),
            ] {
                let Some(approver) = item
                    .get(field)
                    .and_then(|value| value.get("approved_by_id"))
                    .and_then(Value::as_str)
                else {
                    continue;
                };
                if !fresh(&guard, session, approver, permission) {
                    return Err(format!("{label} approval expired. Ask the manager to enter their PIN again."));
                }
            }
        }
        let on_account = payload
            .get("tenders")
            .and_then(Value::as_array)
            .is_some_and(|tenders| {
                tenders
                    .iter()
                    .any(|tender| tender.get("method").and_then(Value::as_str) == Some("on_account"))
            });
        if on_account && !session.user.permissions.iter().any(|item| item == POS_CREDIT_SALE) {
            return Err(format!("{} cannot sell on account.", session.user.full_name));
        }
        if let Some(approver) = payload
            .get("credit_override")
            .and_then(|value| value.get("approved_by_id"))
            .and_then(Value::as_str)
        {
            if !fresh(&guard, session, approver, CUSTOMERS_MANAGE) {
                return Err("Credit limit approval expired. Ask the manager to enter their PIN again.".into());
            }
        }
    }
    Ok(())
}
