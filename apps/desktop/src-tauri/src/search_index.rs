//! Full-text product search for big catalogs (supermarkets carry 10,000-50,000 SKUs). An FTS5 trigram index over the
//! same haystack the API searches (app.models.product.search_haystack): name, model, barcode, SKU, category, brand,
//! season, collection, and model / SKU / barcode without separators. Triggers keep it in step with `products`.

use rusqlite::{params, Connection, OptionalExtension};

/// Trigrams need three characters; shorter search words fall back to LIKE in `Db::search_products`.
pub const MIN_CHARS: usize = 3;

/// Bump when the haystack changes so existing registers rebuild their index on the next start.
const VERSION: i64 = 2;

/// Mirrors `db::compact`: drops spaces, dashes, underscores, dots and slashes.
fn compact_sql(expression: &str) -> String {
    let mut sql = expression.to_string();
    for separator in [" ", "-", "_", ".", "/"] {
        sql = format!("REPLACE({sql}, '{separator}', '')");
    }
    sql
}

fn haystack_sql(row: &str) -> String {
    let model = format!("IFNULL({row}model_number, '')");
    let parts = [
        format!("{row}name"),
        model.clone(),
        format!("{row}barcode"),
        format!("{row}sku"),
        format!("{row}category"),
        format!("IFNULL({row}brand, '')"),
        format!("IFNULL({row}season, '')"),
        format!("IFNULL({row}collection, '')"),
        compact_sql(&model),
        compact_sql(&format!("{row}sku")),
        compact_sql(&format!("{row}barcode")),
    ];
    format!("LOWER({})", parts.join(" || ' ' || "))
}

pub fn migrate(conn: &Connection) -> Result<(), String> {
    let new_row = haystack_sql("NEW.");
    conn.execute_batch(&format!(
        "
        CREATE TABLE IF NOT EXISTS search_index_meta (name TEXT PRIMARY KEY, version INTEGER NOT NULL);
        CREATE VIRTUAL TABLE IF NOT EXISTS products_fts USING fts5(haystack, tokenize = 'trigram');
        DROP TRIGGER IF EXISTS products_fts_insert;
        DROP TRIGGER IF EXISTS products_fts_delete;
        DROP TRIGGER IF EXISTS products_fts_update;
        CREATE TRIGGER products_fts_insert AFTER INSERT ON products BEGIN
            INSERT INTO products_fts (rowid, haystack) VALUES (NEW.rowid, {new_row});
        END;
        CREATE TRIGGER products_fts_delete AFTER DELETE ON products BEGIN
            DELETE FROM products_fts WHERE rowid = OLD.rowid;
        END;
        CREATE TRIGGER products_fts_update AFTER UPDATE ON products BEGIN
            DELETE FROM products_fts WHERE rowid = OLD.rowid;
            INSERT INTO products_fts (rowid, haystack) VALUES (NEW.rowid, {new_row});
        END;
        "
    ))
    .map_err(|err| err.to_string())?;
    let version: Option<i64> = conn
        .query_row(
            "SELECT version FROM search_index_meta WHERE name = 'products'",
            [],
            |row| row.get(0),
        )
        .optional()
        .map_err(|err| err.to_string())?;
    let indexed: i64 = conn
        .query_row("SELECT COUNT(*) FROM products_fts", [], |row| row.get(0))
        .map_err(|err| err.to_string())?;
    let products: i64 = conn
        .query_row("SELECT COUNT(*) FROM products", [], |row| row.get(0))
        .map_err(|err| err.to_string())?;
    if version != Some(VERSION) || indexed != products {
        rebuild(conn)?;
    }
    Ok(())
}

fn rebuild(conn: &Connection) -> Result<(), String> {
    conn.execute_batch(&format!(
        "DELETE FROM products_fts;
         INSERT INTO products_fts (rowid, haystack) SELECT rowid, {} FROM products;",
        haystack_sql("")
    ))
    .map_err(|err| err.to_string())?;
    conn.execute(
        "INSERT INTO search_index_meta (name, version) VALUES ('products', ?1)
         ON CONFLICT(name) DO UPDATE SET version = excluded.version",
        params![VERSION],
    )
    .map_err(|err| err.to_string())?;
    Ok(())
}

fn quoted(text: &str) -> String {
    format!("\"{}\"", text.replace('"', "\"\""))
}

/// One search word as an FTS5 query term: a substring match, or either spelling when the word has separators
/// ("ga05843-us" also finds "GA05843US").
pub fn term(token: &str, compact: &str) -> String {
    if compact != token && compact.chars().count() >= MIN_CHARS {
        format!("({} OR {})", quoted(token), quoted(compact))
    } else {
        quoted(token)
    }
}

#[cfg(test)]
mod tests {
    use std::path::Path;
    use std::time::Instant;

    use serde_json::json;

    use crate::db::{Db, ProductRow};

    fn product(index: usize, name: &str, model: Option<&str>) -> ProductRow {
        serde_json::from_value(json!({
            "id": format!("p-{index}"),
            "store_id": "s-1",
            "sku": format!("GRO-{index:06}"),
            "barcode": format!("6{index:011}"),
            "name": name,
            "model_number": model,
            "brand": if index % 2 == 0 { "Almarai" } else { "Barakat" },
            "category": "Grocery",
            "price_cents": 450,
            "currency": "AED",
            "is_serialized": false,
            "stock_quantity": 10,
        }))
        .expect("product row")
    }

    fn names(db: &Db, query: &str) -> Vec<String> {
        db.search_products(query, 50)
            .expect("search")
            .into_iter()
            .map(|hit| hit.product.name)
            .collect()
    }

    #[test]
    fn matches_like_the_api_haystack_and_follows_catalog_refreshes() {
        let db = Db::open(Path::new(":memory:")).expect("db");
        db.replace_products(&[
            product(1, "Full Cream Milk 1 L", Some("FCM-1L")),
            product(2, "Laban Up 500 ml", None),
            product(3, "Pixel 9", Some("GA05843-US")),
        ])
        .expect("replace");
        assert_eq!(names(&db, "milk"), vec!["Full Cream Milk 1 L"]);
        assert_eq!(names(&db, "MILK barakat"), vec!["Full Cream Milk 1 L"]);
        assert_eq!(names(&db, "ga05843us"), vec!["Pixel 9"]);
        assert_eq!(names(&db, "GA05843-US"), vec!["Pixel 9"]);
        assert_eq!(names(&db, "fcm1l"), vec!["Full Cream Milk 1 L"]);
        assert_eq!(
            names(&db, "up 5"),
            vec!["Laban Up 500 ml"],
            "short words still match through LIKE"
        );
        assert_eq!(
            names(&db, "\"milk"),
            Vec::<String>::new(),
            "quotes are literal, not FTS syntax"
        );
        let hits = db.search_products("600000000002", 5).expect("search");
        assert_eq!(hits[0].match_kind, "exact");

        db.replace_products(&[product(4, "Goat Milk 500 ml", None)])
            .expect("refresh");
        assert_eq!(names(&db, "milk"), vec!["Goat Milk 500 ml"]);
        assert_eq!(names(&db, "laban"), Vec::<String>::new());
    }

    #[test]
    fn fifty_thousand_products_search_fast() {
        let db = Db::open(Path::new(":memory:")).expect("db");
        let words = [
            "Apple", "Banana", "Carrot", "Dates", "Eggs", "Flour", "Garlic", "Honey", "Juice",
            "Milk",
        ];
        let catalog: Vec<ProductRow> = (0..50_000)
            .map(|index| {
                let name = format!(
                    "{} {} {}g",
                    words[index % words.len()],
                    words[(index / 10) % words.len()],
                    index % 900
                );
                product(index, &name, (index % 3 == 0).then_some("FR-100"))
            })
            .collect();
        let loaded = Instant::now();
        db.replace_products(&catalog).expect("replace");
        let load_ms = loaded.elapsed().as_millis();

        let mut slowest = 0;
        for query in [
            "milk",
            "honey dates",
            "almarai juice",
            "600000025000",
            "gro025000",
            "zzqx",
            "fr100",
        ] {
            let started = Instant::now();
            let hits = db.search_products(query, 50).expect("search");
            slowest = slowest.max(started.elapsed().as_millis());
            if query != "zzqx" {
                assert!(!hits.is_empty(), "{query} found nothing");
            }
        }
        eprintln!("50k catalog: load {load_ms} ms, slowest search {slowest} ms");
        assert!(slowest < 250, "slowest search took {slowest} ms");
    }
}
