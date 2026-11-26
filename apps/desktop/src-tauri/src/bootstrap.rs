//! Local catalogue generations.
//!
//! Checkout reads `products` only after `Db::activate_bootstrap` commits.
//! `sync_queue` is not part of that transaction. A short download leaves the previous products in place.

#[cfg(test)]
mod tests {
    use crate::db::{Db, QueuedEvent};

    fn product(id: &str, name: &str, stock: i64) -> String {
        format!(
            r#"{{"id":"{id}","store_id":"branch-a","sku":"sku-{id}","barcode":"bc-{id}","name":"{name}","category":"General","price_cents":100,"currency":"AED","is_serialized":false,"stock_quantity":{stock},"stock_authoritative":true}}"#
        )
    }

    fn open(name: &str) -> (Db, std::path::PathBuf) {
        let path = std::env::temp_dir().join(format!("axiz-o3-{}-{name}.db", std::process::id()));
        let _ = std::fs::remove_file(&path);
        let db = Db::open(&path).expect("database");
        (db, path)
    }

    #[test]
    fn a_floor_row_for_another_branch_is_not_stored() {
        let (db, path) = open("floor");
        db.stage_products(1, &[("p1".into(), product("p1", "Milk", 4))]).unwrap();
        db.activate_bootstrap(1, 1, "cursor-1", None).unwrap();
        let own = r#"{"id":"t1","kind":"table","store_id":"branch-a","label":"5"}"#;
        let other = r#"{"id":"t9","kind":"table","store_id":"branch-b","label":"Marina 5"}"#;
        db.apply_catalogue_pull(
            "branch-a",
            &[
                (1, "floor".into(), "upsert".into(), "t1".into(), Some(own.into())),
                (2, "floor".into(), "omit".into(), "".into(), None),
                (3, "floor".into(), "upsert".into(), "t9".into(), Some(other.into())),
                (4, "menu".into(), "upsert".into(), "g1".into(), Some(r#"{"id":"g1","kind":"group","name":"Milk"}"#.into())),
            ],
            "cursor-floor",
        )
        .unwrap();
        assert_eq!(db.register_config("floor", "t1").unwrap().as_deref(), Some(own));
        assert_eq!(db.register_config("floor", "t9").unwrap(), None);
        assert!(db.register_config("menu", "g1").unwrap().unwrap().contains("Milk"));
        assert_eq!(db.bootstrap_last_seq().unwrap(), 4);
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn a_short_download_does_not_replace_products_or_the_queue() {
        let (db, path) = open("short");
        db.stage_products(1, &[("p1".into(), product("p1", "Milk", 4))]).unwrap();
        db.activate_bootstrap(1, 1, "cursor-1", None).unwrap();
        db.enqueue(
            "batch-1",
            &[QueuedEvent {
                id: "event-1".into(),
                idempotency_key: "sale-key-1".into(),
                entity_type: "sale".into(),
                operation: "create".into(),
                payload: serde_json::json!({"total_cents": 100}),
                occurred_at: "2020-01-01T00:00:00Z".into(),
            }],
        )
        .unwrap();
        db.stage_products(2, &[("p1".into(), product("p1", "Milk", 4))]).unwrap();
        assert!(db.activate_bootstrap(2, 2, "cursor-2", None).is_err());
        assert_eq!(db.list_products().unwrap().len(), 1);
        assert_eq!(db.list_products().unwrap()[0].name, "Milk");
        assert_eq!(db.pending_count().unwrap(), 1);
        assert_eq!(db.bootstrap_label(), "complete");
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn duplicate_pages_and_pulls_do_not_move_the_cursor_past_a_gap() {
        let (db, path) = open("pull");
        let row = ("p1".into(), product("p1", "Milk", 4));
        db.stage_products(1, &[row.clone()]).unwrap();
        db.stage_products(1, &[row]).unwrap();
        assert!(db
            .stage_products(1, &[("p1".into(), product("p1", "Other", 4))])
            .is_err());
        db.activate_bootstrap(1, 1, "cursor-1", None).unwrap();
        let changed = product("p1", "Milk 2", 99).replace("true", "false");
        db.apply_product_pull(&[(1, "upsert".into(), "p1".into(), Some(changed))], "cursor-a")
            .unwrap();
        assert_eq!(db.bootstrap_last_seq().unwrap(), 1);
        assert_eq!(db.list_products().unwrap()[0].stock_quantity, 4);
        assert_eq!(db.list_products().unwrap()[0].name, "Milk 2");
        db.apply_product_pull(&[(1, "upsert".into(), "p1".into(), Some(product("p1", "Ignored", 1)))], "cursor-b")
            .unwrap();
        assert_eq!(db.list_products().unwrap()[0].name, "Milk 2");
        assert!(db
            .apply_product_pull(&[(3, "delete".into(), "p1".into(), None)], "cursor-gap")
            .is_err());
        assert_eq!(db.bootstrap_last_seq().unwrap(), 1);
        assert!(db.list_products().unwrap()[0].is_active);
        db.apply_product_pull(&[(2, "delete".into(), "p1".into(), None)], "cursor-c").unwrap();
        assert!(!db.list_products().unwrap()[0].is_active);
        assert_eq!(db.list_products().unwrap().len(), 1);
        assert_eq!(db.pending_count().unwrap(), 0);
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn a_queued_sale_keeps_its_price_after_restart_and_a_later_catalogue_price() {
        let (db, path) = open("sale");
        db.stage_products(1, &[("p1".into(), product("p1", "Milk", 4))]).unwrap();
        db.activate_bootstrap(1, 1, "cursor-1", None).unwrap();
        let sale = serde_json::json!({
            "total_cents": 100,
            "tax_cents": 5,
            "items": [{"unit_price_cents": 100, "tax_cents": 5, "line_total_cents": 100}]
        });
        let event = QueuedEvent {
            id: "event-1".into(),
            idempotency_key: "sale-1".into(),
            entity_type: "sale".into(),
            operation: "upsert".into(),
            payload: sale,
            occurred_at: "2026-11-21T00:00:00Z".into(),
        };
        db.enqueue("batch-1", &[event.clone()]).unwrap();
        assert!(db.enqueue("batch-2", &[event]).is_err());
        assert_eq!(db.pending_count().unwrap(), 1);
        let later = product("p1", "Milk", 4).replace("\"price_cents\":100", "\"price_cents\":900");
        db.apply_product_pull(&[(1, "upsert".into(), "p1".into(), Some(later))], "cursor-2")
            .unwrap();
        drop(db);
        let db = Db::open(&path).unwrap();
        let (batch_id, events) = db.next_pending_batch().unwrap().unwrap();
        assert_eq!(batch_id, "batch-1");
        assert_eq!(events[0].idempotency_key, "sale-1");
        assert_eq!(events[0].payload["total_cents"], 100);
        assert_eq!(events[0].payload["tax_cents"], 5);
        assert_eq!(events[0].payload["items"][0]["unit_price_cents"], 100);
        assert_eq!(db.list_products().unwrap()[0].price_cents, 900);
        assert_eq!(db.pending_count().unwrap(), 1);
        let _ = std::fs::remove_file(&path);
    }

    fn cashier() -> crate::auth::Session {
        crate::auth::Session {
            user: crate::auth::CashierProfile {
                id: "cashier".into(),
                username: "cashier".into(),
                full_name: "Cashier".into(),
                store_id: Some("branch-a".into()),
                role_name: "Cashier".into(),
                permissions: Vec::new(),
                max_discount_bps: None,
                addon_modules: Vec::new(),
                addon_synced_at: 0,
                avatar_url: None,
            },
            mode: "offline",
            unlocked_at: 0,
        }
    }

    fn return_event(id: &str, key: &str) -> QueuedEvent {
        QueuedEvent {
            id: id.into(),
            idempotency_key: key.into(),
            entity_type: "sale_return".into(),
            operation: "upsert".into(),
            payload: serde_json::json!({
                "id": "return-1",
                "original_sale_id": "sale-1",
                "cashier_id": "cashier",
                "store_id": "branch-a",
                "total_refund_cents": 100
            }),
            occurred_at: "2026-11-21T00:00:00Z".into(),
        }
    }

    #[test]
    fn a_return_and_its_queue_row_commit_together() {
        let (db, path) = open("return");
        let approvals = std::sync::Mutex::new(std::collections::HashMap::new());
        let session = cashier();
        let wrong = QueuedEvent {
            payload: serde_json::json!({"id": "return-x", "cashier_id": "other", "original_sale_id": "sale-1"}),
            ..return_event("event-x", "return-x")
        };
        assert!(crate::returns::enqueue(&db, &approvals, &session, "batch-x", &[wrong]).is_err());
        assert_eq!(db.pending_count().unwrap(), 0);
        crate::returns::enqueue(&db, &approvals, &session, "batch-r", &[return_event("event-r", "return-1")]).unwrap();
        assert!(crate::returns::enqueue(&db, &approvals, &session, "batch-r2", &[return_event("event-r2", "return-2")]).is_err());
        assert_eq!(db.pending_count().unwrap(), 1);
        let mirrored: i64 = db
            .read(|conn| {
                conn.query_row("SELECT COUNT(*) FROM local_returns WHERE id = 'return-1'", [], |row| row.get(0))
                    .map_err(|err| err.to_string())
            })
            .unwrap();
        assert_eq!(mirrored, 1);
        drop(db);
        let db = Db::open(&path).unwrap();
        let (_batch, events) = db.next_pending_batch().unwrap().unwrap();
        assert_eq!(events[0].idempotency_key, "return-1");
        assert_eq!(events[0].payload["total_refund_cents"], 100);
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn checkout_settings_activate_with_the_catalogue_and_do_not_rewrite_a_queued_sale() {
        let (db, path) = open("tax");
        let frozen = r#"{"currency":"AED","vat_registered":true,"prices_include_vat":false,"standard_rate_bps":500,"tax_authority":"fta"}"#;
        db.stage_products(1, &[("p1".into(), product("p1", "Milk", 4))]).unwrap();
        db.activate_bootstrap(1, 1, "cursor-1", Some(frozen)).unwrap();
        assert_eq!(crate::settings::cached_currency(&db).unwrap().as_deref(), Some("AED"));
        let sale = serde_json::json!({"total_cents": 105, "tax_cents": 5, "currency": "AED"});
        db.enqueue(
            "batch-tax",
            &[QueuedEvent {
                id: "event-tax".into(),
                idempotency_key: "sale-tax".into(),
                entity_type: "sale".into(),
                operation: "upsert".into(),
                payload: sale,
                occurred_at: "2026-11-22T00:00:00Z".into(),
            }],
        )
        .unwrap();
        let changed = r#"{"currency":"USD","vat_registered":true,"prices_include_vat":false,"standard_rate_bps":1000,"tax_authority":"fta"}"#;
        db.apply_product_pull(&[(1, "settings".into(), "checkout".into(), Some(changed.into()))], "cursor-2")
            .unwrap();
        assert_eq!(crate::settings::cached_currency(&db).unwrap().as_deref(), Some("USD"));
        let (_batch, events) = db.next_pending_batch().unwrap().unwrap();
        assert_eq!(events[0].idempotency_key, "sale-tax");
        assert_eq!(events[0].payload["tax_cents"], 5);
        assert_eq!(events[0].payload["currency"], "AED");
        db.stage_products(2, &[("p1".into(), product("p1", "Milk", 4))]).unwrap();
        let replacement = r#"{"currency":"EUR","vat_registered":false,"prices_include_vat":false,"standard_rate_bps":0,"tax_authority":"fta"}"#;
        assert!(db.activate_bootstrap(2, 2, "cursor-3", Some(replacement)).is_err());
        assert_eq!(crate::settings::cached_currency(&db).unwrap().as_deref(), Some("USD"));
        assert_eq!(db.pending_count().unwrap(), 1);
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn a_product_edit_keeps_the_photo_and_the_stock_already_on_the_register() {
        let (db, path) = open("merge");
        let staged = r#"{"id":"p1","store_id":"branch-a","sku":"DAL-1","barcode":"628","name":"Daal","category":"Mains","price_cents":1500,"currency":"AED","is_serialized":false,"stock_quantity":9,"stock_authoritative":true,"image_url":"https://cdn.example/daal.webp"}"#;
        db.stage_products(1, &[("p1".into(), staged.into())]).unwrap();
        db.activate_bootstrap(1, 1, "cursor-1", None).unwrap();
        let edit = r#"{"id":"p1","sku":null,"barcode":null,"name":"Daal Channa","category":"Mains","price_cents":1800,"currency":"AED","is_serialized":false,"is_active":true,"stock_quantity":0,"stock_authoritative":false}"#;
        db.apply_catalogue_pull(
            "branch-a",
            &[(1, "products".into(), "upsert".into(), "p1".into(), Some(edit.into()))],
            "cursor-2",
        )
        .unwrap();
        let rows = db.list_products().unwrap();
        let row = rows.iter().find(|item| item.id == "p1").expect("product");
        assert_eq!(row.name, "Daal Channa");
        assert_eq!(row.price_cents, 1800);
        assert_eq!(row.stock_quantity, 9);
        assert_eq!(row.sku, "DAL-1");
        assert_eq!(row.image_url.as_deref(), Some("https://cdn.example/daal.webp"));
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn a_conflict_stays_out_of_the_pending_queue_and_keeps_its_payload() {
        let (db, path) = open("conflict");
        db.enqueue(
            "batch-1",
            &[QueuedEvent {
                id: "event-1".into(),
                idempotency_key: "sale-1".into(),
                entity_type: "sale".into(),
                operation: "upsert".into(),
                payload: serde_json::json!({"total_cents": 100, "tax_cents": 5}),
                occurred_at: "2026-11-21T00:00:00Z".into(),
            }],
        )
        .unwrap();
        db.mark_batch("batch-1", "conflict", Some("Idempotency key was already used with a different payload."))
            .unwrap();
        assert!(db.next_pending_batch().unwrap().is_none());
        assert_eq!(crate::sync_center::conflict_count(&db).unwrap(), 1);
        drop(db);
        let db = Db::open(&path).unwrap();
        assert_eq!(crate::sync_center::conflict_count(&db).unwrap(), 1);
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
        let _ = std::fs::remove_file(&path);
    }
}
