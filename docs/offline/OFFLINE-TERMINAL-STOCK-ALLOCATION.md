# Per-terminal stock allocation

Status: not implemented.

Stock on the register is `products.stock_quantity`. Two offline terminals can sell the same cached quantity. There is no allocation row for tenant, branch, terminal, device, product, lot, or serial.

The 100 / 40 / 35 / 25 acceptance was not run. No disposable terminals were created for it.

Rules that stay in force until that work exists:

- A terminal consumes only its own allocation.
- An allocation is not taken back only because the terminal looks offline.
- An offline return is not spendable stock.
- Pharmacy medicine sales stay blocked offline.
- Laundry garments in process are not saleable stock.
