import seed from "@ai-pos/catalog/seed.json";
import {
  DEFAULT_TAX_POLICY,
  forCustomer,
  type ReceiptProfile,
  type StoreUpsert,
  type TaxAuthority,
  type TaxPolicy,
} from "@ai-pos/shared-types";
import { useSyncExternalStore } from "react";
import { env } from "../../config/env";
import { terminal } from "../../config/terminal";
import { getBusinessSettings, getReceiptProfile } from "../../lib/api";
import { applyProfile, capabilityScope, type ProfileSnapshot } from "../../lib/capabilities";
import { fetchBusinessCurrency, inTauri } from "../../lib/tauri";

/** The register charges in the business currency a Super Admin picks in the portal, never in a local choice. */
let current: string = seed.store.currency;
const listeners = new Set<() => void>();

/** Offline with nothing cached, registers keep the seed's 5% on top so totals match what the API accepts. */
let taxPolicy: TaxPolicy = { ...DEFAULT_TAX_POLICY, standard_rate_bps: seed.tax_rate_bps };

export interface InvoiceIdentity {
  trn: string | null;
  legalName: string | null;
  legalNameAr: string | null;
  taxAuthority: TaxAuthority;
}

let identity: InvoiceIdentity = { trn: null, legalName: null, legalNameAr: null, taxAuthority: "fta" };

/** Receipt branding and this branch's address and phone; null until the register has reached the API once. */
let receipt: ReceiptProfile | null = null;

export function receiptProfile(): ReceiptProfile | null {
  return receipt;
}

export function businessCurrency(): string {
  return current;
}

export function businessTax(): TaxPolicy {
  return taxPolicy;
}

/** The business's VAT with the attached customer's treatment (zero-rated export, exempt...) applied. */
export function customerTax(customer: Parameters<typeof forCustomer>[1]): TaxPolicy {
  return forCustomer(taxPolicy, customer);
}

export function invoiceIdentity(): InvoiceIdentity {
  return identity;
}

interface TaxSnapshot {
  enforced?: boolean;
  vat_registered?: boolean;
  prices_include_vat?: boolean;
  standard_rate_bps?: number;
  trn?: string | null;
  legal_name?: string | null;
  legal_name_ar?: string | null;
  tax_authority?: string | null;
  tax_configuration_required?: boolean;
  updated_at?: string | null;
  updated_by_name?: string | null;
  country?: string | null;
  location?: string | null;
  timezone?: string | null;
  entitlement_revision?: number | null;
}

export interface BusinessSettingsMeta {
  legalName: string | null;
  legalNameAr: string | null;
  country: string | null;
  location: string | null;
  updatedAt: string;
  updatedByName: string | null;
  timezone: string;
  entitlementRevision: number;
}

const emptyMeta: BusinessSettingsMeta = {
  legalName: null,
  legalNameAr: null,
  country: null,
  location: null,
  updatedAt: "",
  updatedByName: null,
  timezone: "Asia/Dubai",
  entitlementRevision: 0,
};

let meta: BusinessSettingsMeta = emptyMeta;

function rememberIdentity(raw: TaxSnapshot): boolean {
  const next: BusinessSettingsMeta = {
    legalName: raw.legal_name ?? null,
    legalNameAr: raw.legal_name_ar ?? null,
    country: raw.country ?? null,
    location: raw.location ?? null,
    updatedAt: raw.updated_at?.trim() ?? "",
    updatedByName: raw.updated_by_name ?? null,
    timezone: raw.timezone?.trim() || "Asia/Dubai",
    entitlementRevision: raw.entitlement_revision ?? 0,
  };
  const same =
    meta.legalName === next.legalName &&
    meta.legalNameAr === next.legalNameAr &&
    meta.country === next.country &&
    meta.location === next.location &&
    meta.updatedAt === next.updatedAt &&
    meta.updatedByName === next.updatedByName &&
    meta.timezone === next.timezone &&
    meta.entitlementRevision === next.entitlementRevision;
  if (same) return false;
  meta = next;
  return true;
}

/** Last identity metadata applied from a settings response. The object identity changes only when a field does. */
export function businessSettingsMeta(): BusinessSettingsMeta {
  return meta;
}

export function useBusinessSettingsMeta(): BusinessSettingsMeta {
  return useSyncExternalStore(subscribe, businessSettingsMeta, businessSettingsMeta);
}

let branchTaxBlocked = false;
let apiReachable = false;

/** True after this register's own settings request succeeds. An empty sync queue does not set this. */
export function businessApiReachable(): boolean {
  return apiReachable;
}

export function taxConfigurationRequired(): boolean {
  return branchTaxBlocked;
}

/** Keeps a settings body only when the server names the tenant this register was activated for. */
function applyScopedProfile(raw: (ProfileSnapshot & { store_code?: string | null }) | null | undefined): void {
  if (!raw?.capabilities) return;
  const bound = capabilityScope();
  const returned = (raw.tenant_id ?? raw.store_code ?? "").trim();
  if (bound === null || returned === "" || returned !== bound.tenantId) return;
  applyProfile({ ...raw, tenant_id: bound.tenantId, environment: bound.environment });
}

function applyTax(raw: TaxSnapshot | null | undefined): boolean {
  if (!raw) return false;
  taxPolicy = {
    enforced: Boolean(raw.enforced ?? raw.vat_registered),
    prices_include_vat: Boolean(raw.prices_include_vat),
    standard_rate_bps: raw.standard_rate_bps ?? taxPolicy.standard_rate_bps,
  };
  identity = {
    trn: raw.trn ?? null,
    legalName: raw.legal_name ?? null,
    legalNameAr: raw.legal_name_ar ?? null,
    taxAuthority: raw.tax_authority === "zatca" ? "zatca" : "fta",
  };
  branchTaxBlocked = Boolean(raw.tax_configuration_required);
  return rememberIdentity(raw);
}

const branches: StoreUpsert[] = [seed.store, ...seed.branches];
const activated = terminal();
const home: StoreUpsert =
  activated?.activated && activated.store_name
    ? { id: activated.store_id, code: activated.store_code, name: activated.store_name, currency: seed.store.currency }
    : (branches.find((branch) => branch.id === env.storeId) ?? { ...seed.store, id: env.storeId, code: "MAIN" });

/** This register's branch. Only identity fields are synced so registers never overwrite branch settings. */
export function activeStore(): StoreUpsert {
  return { id: home.id, code: home.code, name: home.name, currency: current };
}

export async function syncBusinessCurrency(): Promise<string> {
  let next: string | null = null;
  let identityChanged = false;
  try {
    if (inTauri()) {
      const snapshot = await fetchBusinessCurrency();
      next = snapshot.currency;
      identityChanged = applyTax(snapshot.tax);
      applyScopedProfile(snapshot.profile);
      if (snapshot.receipt) receipt = snapshot.receipt;
      // A cached or seeded profile is not a live settings response.
      apiReachable = snapshot.source === "api";
    } else {
      const settings = await getBusinessSettings();
      next = settings.currency;
      identityChanged = applyTax(settings);
      applyScopedProfile(settings);
      receipt = await getReceiptProfile(home.id).catch(() => receipt);
      apiReachable = true;
    }
  } catch {
    apiReachable = false;
    // Offline with nothing cached: keep the last known currency.
  }
  const currencyChanged = next !== null && next !== current;
  if (currencyChanged && next !== null) current = next;
  if (currencyChanged || identityChanged) {
    for (const listener of listeners) listener();
  }
  return current;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useBusinessCurrency(): string {
  return useSyncExternalStore(subscribe, businessCurrency, businessCurrency);
}
