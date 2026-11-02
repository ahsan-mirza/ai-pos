# Security and tenant isolation

The API does not take the tenant from the JSON body. `TenantContextMiddleware` resolves `X-Tenant-Domain` or the Host subdomain, loads that store from the control plane, and binds it for the request. Tokens carry a `tid` claim. `get_principal` rejects a token whose `tid` is not the bound tenant.

## Executed

`tests/test_tenancy.py` passed in this session. It covers:

- The tenant comes from the header or the subdomain.
- An unknown domain is 404 `tenant_not_found`.
- A missing tenant is 400 `tenant_required`.
- A domain outside the configured base is `tenant_invalid`.
- A suspended tenant is 403 `tenant_suspended`.
- A password that works for tenant alpha is 401 on tenant bravo.
- Alpha's access token is 401 when presented to bravo's domain.

`tests/test_tenant_scope.py` is in the suite and was not re-run in this session.

Live checks against the local development tenant:

| Attempt | Result |
| --- | --- |
| Product list with `X-Tenant-Domain: not-a-store` and a valid local token | 404 `tenant_not_found` |
| Product list on the real tenant with a token minted for a different tenant id | 401 `invalid_token` |
| Product create with no tenant header | 404 `tenant_not_found` (the test client host is not a registered store) |

The catalog query plan in `DATABASE_OPTIMIZATION_REPORT.md` is filtered by `tenant_id`. Request sessions raise if code tries to set `include_all_tenants`.

## Not claimed

This pass did not log in as two real customers and attempt to read the other's sales, customers, or stock. The automated tenant tests and the token mismatch check are the evidence collected here. RBAC was not bypassed. The product-create timing used a user who already holds `portal:inventory_manage`.
