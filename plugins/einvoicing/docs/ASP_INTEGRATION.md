# ASP integration

`MockAsp` is the only adapter. Its code is `mock`. `provider_for` raises `KeyError` for any other code. Connection status `MOCK_CONNECTED` and acceptance status `MOCK_ACCEPTED` are test outcomes.

The interface the mock implements, and that a later adapter must implement, is:

- `test_connection()`
- `submit(document)` returning `ProviderResult` with `outcome`, `provider_status`, `reference`, and `detail`

Outcomes the worker understands: `accepted`, `rejected`, `timeout`, `rate_limited`. Timeout and rate limit move the invoice to `RETRY_PENDING`. Rejection moves it to `REJECTED`. A reference is stored only when the outcome is `accepted`.

Buyer-name hooks exist only for the mock: `REJECT`, `TIMEOUT`, `RATELIMIT`.

Webhook verification for the mock is HMAC-SHA256 over `timestamp + "." + body`, compared in constant time, with a 300 second window. The tenant is the `ProviderAccount` whose `participant_id` matches the header. A `tenant_id` in the body that disagrees is rejected. The same event id is stored once.

A real adapter needs that provider's published API, a sandbox credential issued to the tenant, and a conformance note in this file. Until that exists, `dashboard.mock_only` is `true` and the portal says the mock is not an accredited ASP.
