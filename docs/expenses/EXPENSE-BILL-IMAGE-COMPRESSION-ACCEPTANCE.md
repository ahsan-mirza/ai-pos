# Bill image compression — acceptance

Status: **BLOCKED**

Business Pro expenses do not store a bill or tax invoice file. The expense table has a boolean `has_tax_invoice` and the supplier TRN. There is no expense attachment id, storage path, or shared upload route.

The register therefore records the same tax-invoice flag and TRN. It does not upload, compress, or preview a bill image. Adding register-only file storage would leave Business Pro unable to show the same attachment.

When a shared expense document service exists, compression should validate file content, drop location metadata, resize for a readable invoice, and store the file behind the existing authorized download path. That work is not started.
