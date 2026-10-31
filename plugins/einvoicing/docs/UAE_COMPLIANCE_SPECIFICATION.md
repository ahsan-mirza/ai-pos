# UAE compliance notes

This is a reading of public FTA and Ministry of Finance pages as of 31 October 2026. It is not a legal opinion and it is not evidence that AxizPOS conforms.

## Sources

| Source | What it states | What this plugin does |
|---|---|---|
| FTA e-Invoicing page, https://tax.gov.ae/en/content/uae.einvoicing.aspx | An e-invoice is structured data exchanged electronically and reported to the FTA. PDF, Word, images, and email are not e-invoices. The Ministry of Finance portal is the official source. | The POS receipt and the PDF tax invoice stay in place. They are not marked as e-invoices. |
| MoF eInvoicing portal, https://mof.gov.ae/en/about-us/initiatives/einvoicing/ | The model is described as Decentralized Continuous Transaction Control and Exchange (DCTCE) through an Accredited Service Provider, using OpenPeppol. | Submission is only through the plugin's ASP adapter. The register never calls a provider. |
| Ministerial Decision 243 of 2025 | The system decision. The February 2026 guidelines say business transactions, including intra-VAT-group supplies, are in scope unless excluded. | In-scope classification is B2B (buyer TRN) or B2G (configured customer id). |
| Ministerial Decision 244 of 2025, Article 5 as quoted by the FTA PDF and the guidelines v1.0 of 23 February 2026 | B2C is not subject to the system until a later ministerial decision. A person who only does B2C is not subject until then. Voluntary use from 1 July 2026. Mandatory phases by revenue. | A sale with no buyer TRN and no government-customer flag is not queued. |
| FTA media note, 25 October 2026 | Persons at or above AED 50 million must appoint an ASP by 30 October 2026 and implement by 1 January 2027. Below AED 50 million: appoint by 31 March 2027, implement by 1 July 2027. The February guidelines still print 31 July 2026 for the first appointment date. | `revenue_band` stores the tenant's own declaration. It does not prove the band and it does not submit anything. |
| UAE Electronic Invoicing Guidelines v1.0, 23 February 2026 | PINT-AE defines content by document type and scenario. TRN is 15 digits. TIN is the first 10. Electronic credit notes reference the original invoice. Partial credit notes are allowed. Eight scenarios exist, including Free Zone beneficiary data and margin scheme. | 15-digit TRN check. Credit notes copy refund cents and the original invoice number. Free Zone beneficiary, margin scheme, and self-billing are not mapped yet. |
| MoF list of pre-approved providers | Accreditation is a Ministry process. The page links a provider list. | No provider from that list is implemented. `mock` is a test double. |

## Unresolved

- The text of Ministerial Decision 197 of 2026 and Ministerial Resolution 66 of 2026 was listed on the MoF page and was not extracted here. Where those amend the dates above, the later decision wins.
- The PINT AE schema package was not downloaded into this repo. Profile id stored on a snapshot is `pint-ae-billing-1@ae-1`, matching the existing exporter's CustomizationID. A future pack can be a new `profile_version` without rewriting the register.
- XML examples on the Peppol site were not executed.
- Administrative penalty amounts were mentioned in the FTA note (AED 5,000 per month, as reported on that page). The plugin does not calculate penalties.

## Transaction classes

| Class | Treatment |
|---|---|
| B2C | Standard receipt and tax invoice. No e-invoice row. |
| B2B | Buyer TRN present and `b2b_enabled`. Snapshot, then queue. |
| B2G | Customer id listed on the tenant's e-invoicing settings and `b2g_enabled`. |
| Anything else | Rejected by `validate_snapshot` or never queued. |

## Validation implemented

- Seller legal name and 15-digit seller TRN.
- Buyer name and 15-digit buyer TRN for an in-scope document.
- Sum of stored line net and line VAT equals the stored sale net and VAT.
- Stored net plus stored VAT equals the stored total.
- SHA-256 of the canonical JSON. The same snapshot hashes the same. A different snapshot hashes differently.
- Issued payload is not edited in place. A retry resubmits the stored payload.

## Validation not implemented

- Official XSD and PINT AE schematron.
- Free Zone beneficiary, margin scheme display rules, exempt and out-of-scope category codes beyond the cents already stored.
- Emirate code lists and unit-of-measure code lists from the data dictionary.
- A real ASP's response codes.
