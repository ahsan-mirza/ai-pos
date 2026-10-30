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
import { applyProfile } from "../../lib/capabilities";
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
}

let branchTaxBlocked = false;

export function taxConfigurationRequired(): boolean {
  return branchTaxBlocked;
}

function applyTax(raw: TaxSnapshot | null | undefined): void {
  if (!raw) return;
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
  try {
    if (inTauri()) {
      const snapshot = await fetchBusinessCurrency();
      next = snapshot.currency;
      applyTax(snapshot.tax);
      applyProfile(snapshot.profile);
      if (snapshot.receipt) receipt = snapshot.receipt;
    } else {
      const settings = await getBusinessSettings();
      next = settings.currency;
      applyTax(settings);
      applyProfile(settings);
      receipt = await getReceiptProfile(home.id).catch(() => receipt);
    }
  } catch {
    // Offline with nothing cached: keep the last known currency.
  }
  if (next !== null && next !== current) {
    current = next;
    for (const listener of listeners) listener();
  }
  return current;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useBusinessCurrency(): string {
  return useSyncExternalStore(subscribe, businessCurrency);
}
