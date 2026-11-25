# Bill attachments — acceptance

Status: **PASSED WITH LIMITATIONS**

One bill image can be sent with the expense. The API checks the file bytes, not only the name. JPEG, PNG, and WebP are accepted. Other bytes are rejected. The image is rotated from EXIF, saved as WebP without the original metadata, and limited to a 2000-pixel edge at quality 85. The row stores the original size, the stored size, a checksum, and a private storage key under `storage/expense-bills`. It is not placed on the public `/media` URL.

`GET /api/v1/expenses/{id}/bill` requires `expenses:manage` and the same branch scope as the expense. The POS form previews a compressed copy and shows both sizes before save. Opening the expense loads the stored image. If processing fails, the form stays filled and the expense is not committed.

PDF is not accepted. The original unmodified file is not kept beside the WebP. There is no expense document-retention rule that requires the source file. Replacing or deleting a stored bill after save is not offered, so a recorded bill is not removed by the form.

Automated: the category-and-bill API test uploads a PNG, reads back WebP, and rejects plain text. Desktop `compressBill.test.ts` checks the byte sniff. A native window was not used to photograph a bill.
