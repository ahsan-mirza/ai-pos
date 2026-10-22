import { Permission, isValidImei } from "@ai-pos/shared-types";
import { listCustomersRemote, loginPin, pushBatch, registerSerialsRemote } from "../../lib/api";
import {
  approveManager,
  availableSerialsLocal,
  checkSerialsLocal,
  countSerialsLocal,
  createCustomerLocal,
  flushSync,
  inTauri,
  refreshCustomers,
  refreshSerials,
  searchCustomersLocal,
  type CashierProfile,
  type NewRegisterCustomer,
  type RegisterCustomer,
  type RegisterSerial,
  type SerialCheck,
} from "../../lib/tauri";
import type { CashierSession } from "../auth/session";

let browserCustomers: RegisterCustomer[] = [];

export interface CustomerSync {
  count: number;
  source: "api" | "cache";
  message: string | null;
}

/** Refreshes the register's customer and IMEI caches together; both fall back to what is cached. */
export async function syncWholesaleCaches(): Promise<CustomerSync> {
  if (inTauri()) {
    const [customers] = await Promise.all([refreshCustomers(), refreshSerials()]);
    return { count: customers.customers.length, source: customers.source, message: customers.message };
  }
  try {
    browserCustomers = await listCustomersRemote();
    return { count: browserCustomers.length, source: "api", message: null };
  } catch (error) {
    return { count: browserCustomers.length, source: "cache", message: error instanceof Error ? error.message : null };
  }
}

export async function searchCustomers(query: string, limit = 8): Promise<RegisterCustomer[]> {
  if (inTauri()) return searchCustomersLocal(query, limit);
  const needle = query.trim().toLowerCase();
  return browserCustomers
    .filter((customer) =>
      [customer.name, customer.company_name, customer.code, customer.phone, customer.trn_vat_number]
        .filter(Boolean)
        .some((field) => String(field).toLowerCase().includes(needle)),
    )
    .sort((left, right) => (left.customer_type === right.customer_type ? 0 : left.customer_type === "WHOLESALE" ? -1 : 1))
    .slice(0, limit);
}

export async function availableSerials(productId: string, limit: number, exclude: string[]): Promise<RegisterSerial[]> {
  if (inTauri()) return availableSerialsLocal(productId, limit, exclude);
  const skip = new Set(exclude);
  const rows = await registerSerialsRemote(productId);
  return rows.filter((row) => !skip.has(row.value)).slice(0, limit);
}

export async function countSerials(productId: string): Promise<number | null> {
  try {
    if (inTauri()) return await countSerialsLocal(productId);
    return (await registerSerialsRemote(productId)).length;
  } catch {
    return null;
  }
}

export async function checkSerials(productId: string, values: string[]): Promise<SerialCheck[]> {
  if (inTauri()) return checkSerialsLocal(productId, values);
  let known: RegisterSerial[] = [];
  try {
    known = await registerSerialsRemote(productId);
  } catch {
    known = [];
  }
  const byValue = new Map(known.map((row) => [row.value.toUpperCase(), row]));
  return values.map((value) => {
    const row = byValue.get(value.toUpperCase());
    return row
      ? { value: row.value, status: "available", product_id: row.product_id, kind: row.kind }
      : { value, status: "unknown", product_id: null, kind: null };
  });
}

/** Splits a pasted block or scan into identifiers, normalizing serials to upper case. */
export function parseIdentifiers(raw: string): { value: string; kind: "imei" | "serial"; valid: boolean }[] {
  return raw
    .split(/[\s,;]+/)
    .map((token) => token.trim())
    .filter((token) => token !== "")
    .map((token) => {
      if (/^\d{15}$/.test(token)) return { value: token, kind: "imei" as const, valid: isValidImei(token) };
      return { value: token.toUpperCase(), kind: "serial" as const, valid: /^[A-Za-z0-9-]{4,64}$/.test(token) };
    });
}

export type QuickCustomerInput = Omit<NewRegisterCustomer, "id" | "at">;

/** Adds a customer at the till. The shell caches it and queues it, so offline sales can carry it at once. */
export async function createCustomer(session: CashierSession, input: QuickCustomerInput): Promise<RegisterCustomer> {
  const draft: NewRegisterCustomer = { ...input, id: crypto.randomUUID(), at: new Date().toISOString() };
  if (inTauri()) {
    const created = await createCustomerLocal(draft);
    void flushSync().catch(() => undefined);
    return created;
  }
  const { at, ...fields } = draft;
  const manager = session.user.permissions.includes(Permission.CustomersManage);
  const wholesale = fields.customer_type === "WHOLESALE";
  const payload = {
    ...fields,
    created_by_id: session.user.id,
    company_name: wholesale ? fields.company_name : null,
    trn_vat_number: wholesale ? fields.trn_vat_number : null,
    price_tier: wholesale && manager ? fields.price_tier : "RETAIL",
    credit_limit_cents: wholesale && manager ? fields.credit_limit_cents : 0,
    payment_terms: wholesale && manager ? fields.payment_terms : "DUE_ON_RECEIPT",
  };
  await pushBatch([
    { idempotency_key: `customer-${draft.id}`, entity_type: "customer", operation: "upsert", payload, occurred_at: at },
  ]);
  const created = (await listCustomersRemote()).find((row) => row.id === draft.id);
  if (!created) throw new Error("The customer was saved but could not be loaded. Search for them again.");
  browserCustomers = [created, ...browserCustomers.filter((row) => row.id !== created.id)];
  return created;
}

/** Online first in the browser preview; the desktop shell also accepts the manager's cached PIN. */
export async function verifyManager(
  session: CashierSession,
  username: string,
  pin: string,
  permission: Permission,
): Promise<CashierProfile> {
  if (inTauri()) return approveManager(username, pin, permission);
  const { user } = await loginPin(username, pin);
  if (!user.permissions.includes(permission)) {
    const actions: Partial<Record<Permission, string>> = {
      [Permission.PosPriceOverride]: "price overrides",
      [Permission.PosBelowFloorOverride]: "prices below the margin floor",
      [Permission.PosDiscount]: "discounts",
    };
    throw new Error(`${user.full_name} cannot approve ${actions[permission] ?? "credit limit overrides"}.`);
  }
  if (user.store_id !== null && session.user.store_id !== null && user.store_id !== session.user.store_id) {
    throw new Error(`${user.full_name} is not assigned to this store.`);
  }
  return {
    id: user.id,
    username: user.username,
    full_name: user.full_name,
    store_id: user.store_id,
    role_name: user.role.name,
    permissions: user.permissions,
    max_discount_bps: user.role.max_discount_bps ?? null,
  };
}
