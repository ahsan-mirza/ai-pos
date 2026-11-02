# Product creation failure

## What the screen shows

The New Product form posts `POST /api/v1/inventory/products`. The sentence "The server hit an unexpected error. Retry, and contact support if it keeps happening." is produced only by `unhandled_error` in `apps/api/app/core/errors.py` when the exception is an `internal_error` (HTTP 500). Schema mismatches and database outages use different sentences.

## Captured exception

On the local `baristo` tenant (restaurant profile, currency PKR, category Burgers, store MAIN), the same request with a normal selling rate succeeded and the same request with an out-of-range selling rate failed.

Successful body: `price_cents` 1500 (15.00), `item_type` PRE_PACKAGED, opening quantity 2, reorder level 1, unit `PIECE`, tax `STANDARD`. Response: **201**, then `GET /api/v1/products/{id}` **200**. The audit row was deleted afterward.

Failing body: the same fields with `price_cents` 3000000000 (a selling rate of 30,000,000.00). PostgreSQL rejected the insert:

```
psycopg.errors.NumericValueOutOfRange: integer out of range
sqlalchemy.exc.DataError
INSERT INTO products (..., price_cents, ...) VALUES (..., %(price_cents)s::INTEGER, ...)
parameter price_cents = 3000000000
```

The failure is on `Session.flush()` inside `create_product` (`apps/api/app/services/inventory.py`). `products.price_cents` is a 32-bit `INTEGER`. The largest value it can store is 2,147,483,647 cents, which is 21,474,836.47 in major units.

Before the fix the HTTP response was:

```json
{
  "error": {
    "code": "internal_error",
    "message": "The server hit an unexpected error. Retry, and contact support if it keeps happening.",
    "api": "POST /api/v1/inventory/products",
    "details": {"exception": "DataError", "detail": "integer out of range"}
  }
}
```

`ProductCreate.price_cents` only required `>= 0`. The form sends `Math.round(typedRate * 100)`, so any typed rate above 21,474,836.47 becomes an integer the column cannot store. `@portal_errors` translated `IntegrityError` into a 409 and left `DataError` uncaught, so the generic 500 handler ran. The server log kept the traceback; the browser did not.

## Fix

- `stored_cents` rejects a price above 2,147,483,647 before the insert. The form already maps `price_cents` onto the selling-price field, so the cashier sees "Selling price must be at most 21,474,836.47." Confirmed after the change: the overflow request returns **422** `invalid_request` with `field_errors.price_cents`.
- The same limit is applied to product updates and to variant-matrix prices and costs, which write the same integer columns.
- `DataError` is now a 422 `value_out_of_range` ("A number in this request is outside the range that can be stored.") and the inventory transaction is rolled back. The traceback stays in the server log.

A second crash on the way back out of create was closed as well. `variant_swatches` called `.get` on a swatch entry. A plain string in `axis_swatches` raised `AttributeError` after the product row was saved and became the same generic 500. Non-dict entries are now skipped. That path was not the one captured on `baristo`; the captured failure is the integer overflow.

## What this local tenant did successfully

Category, SKU, barcode, tax category, open price, minimum age, piece units, opening stock, and reorder level were accepted for in-range prices. `products_out` on the existing catalog did not raise. A specification key that belongs to another business type returns 422 `spec_not_for_business`, which is a validation result, not this 500.
