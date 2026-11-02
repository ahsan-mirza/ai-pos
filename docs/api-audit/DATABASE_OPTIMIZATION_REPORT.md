# Database optimization report

Measured on the local development PostgreSQL database on 2026-11-02. No index was added. The signed-in tenant has 2 products, and the tenant-scoped plan is already an index scan of a few tenths of a millisecond. A new composite index would not change a 2-row result in a way this measurement can show.

## Tenant-scoped catalog page

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id FROM products
WHERE tenant_id = :tenant
ORDER BY name, id
LIMIT 50;
```

Plan:

- Index Scan using `ix_products_tenant_id`
- Index Cond on `tenant_id`
- Sort by `name, id` (quicksort, 25 kB)
- Actual rows: 2
- Execution time: 0.038 ms
- Planning time: 0.199 ms
- Buffers: shared hit 9 during execution

`ix_products_name_id` exists for keyset paging of a larger catalog. On this tenant the planner uses the tenant index and sorts the two rows. That is the right plan at this size.

An unscoped `SELECT id FROM products ORDER BY name, id LIMIT 50` (no tenant predicate) used `ix_products_name_id` and finished in 1.605 ms. The planner estimated 342 rows in the shared table. That statement is not what the API runs. ORM sessions add the tenant criterion, and request sessions cannot turn it off.

## Indexes already present

`products`: primary key, tenant id, category, category id, sub-category, brand, brand id, product model, model number, name+id, season, collection, gender, markdown event, trigram `search_text`, GIN `specifications`, and unique keys on SKU, barcode, PLU, and model+variant signature.

`inventory_levels`: primary key, product id, store id, tenant id, and a unique product+store key.

## Not changed

No sequential scan showed up on the catalog page. No duplicate index was dropped. Stock, price, and customer queries were not given new indexes, because this pass did not capture a slow plan for them. Caching stock in Redis was not added; a stale on-hand quantity is worse than the 0.038 ms read above. Category and settings reads already go through `list_cache` and the settings cache, both keyed by tenant, and a Redis error falls through to PostgreSQL.
