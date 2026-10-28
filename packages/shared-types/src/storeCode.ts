/** Tenant store code. Mirrors `normalize_store_code` and `SLUG` in apps/api/app/tenancy/registry.py. */

const STORE_CODE = /^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$/;

/** Removes every whitespace character, then lowercases. Other characters are left unchanged. */
export function normalizeStoreCode(value: string): string {
  return value.replace(/\s/gu, "").toLowerCase();
}

export function isStoreCode(value: string): boolean {
  return STORE_CODE.test(value);
}

/** Empty after normalization, or a code the API would reject. */
export function storeCodeError(value: string): string | undefined {
  const code = normalizeStoreCode(value);
  if (code === "") return "Enter the store code.";
  if (!isStoreCode(code)) return "Use letters, numbers, and hyphens only.";
  return undefined;
}
