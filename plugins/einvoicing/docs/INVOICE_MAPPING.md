# Invoice mapping

`canonical()` builds a JSON document from a `SourceDocument`. It does not build UBL. The existing exporter `export_service.pint_ae_invoice` remains the on-demand PINT AE XML download. That XML was not validated against an official XSD in this change.

| Canonical field | Source |
|---|---|
| `profile` | `pint-ae-billing-1@ae-1` |
| `document_type` | `380` for an invoice, `381` for a credit note. These are the UNCL codes already used by the exporter's invoice type. They were not re-checked against a downloaded code list. |
| `number` | Posted invoice number, or the return's credit-note number. |
| `issue_date` | Sale date as stored, `YYYY-MM-DD`. |
| `currency` | Sale currency. |
| `transaction` | `B2B` or `B2G`. |
| `seller.name`, `seller.trn` | `business_settings.legal_name` and `business_settings.trn`. |
| `buyer.name`, `buyer.trn` | Customer name and `customers.trn_vat_number`. |
| `lines[].net`, `lines[].tax` | `sale_items` net and `tax_cents`, formatted by `money()`. |
| `lines[].rate_bps` | Stored `tax_rate_bps`. 500 means 5%. |
| `net`, `tax`, `total` | `sales.subtotal_cents`, `sales.tax_cents`, `sales.total_cents`. |

`payload_hash` is SHA-256 of `json.dumps(sort_keys=True, separators=(",", ":"))`.

Rounding: there is none in the plugin. Half-up rounding already happened in `line_tax` when the sale was posted. A line sum that does not equal the sale header becomes `VALIDATION_FAILED`. Service charge that sits outside the line nets fails closed for that reason.

Credit notes copy `returns.subtotal_cents`, `tax_refund_cents`, and `total_refund_cents`, and they store the original invoice id.
