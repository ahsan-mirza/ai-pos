import type {
  Availability,
  Customer,
  DesktopAuditActionType,
  ModuleSettings,
  PosPolicy,
  ProductSearchHit,
  ProductUpsert,
  Quote,
  QuoteUpsert,
  Receipt,
  ReceiptProfile,
  ReturnUpsert,
  SaleUpsert,
  SyncEvent,
} from "@ai-pos/shared-types";
import { env } from "../config/env";

export interface SyncReport {
  pending: number;
  applied: number;
  duplicates: number;
  message: string;
}

export interface BatchStatus {
  status: "pending" | "synced" | "rejected";
  error: string | null;
}

export interface CatalogSnapshot {
  products: ProductUpsert[];
  source: "api" | "cache";
  message: string | null;
}

export interface CashierProfile {
  id: string;
  username: string;
  full_name: string;
  store_id: string | null;
  role_name: string;
  permissions: string[];
  /** Largest discount (basis points) given without a manager; null uses the business default. */
  max_discount_bps?: number | null;
}

export interface CashierSession {
  user: CashierProfile;
  mode: "online" | "offline";
  unlocked_at: number;
}

export interface AppUpdate {
  version: string;
  notes: string | null;
  sha256: string;
  url: string;
}

/** Null when this version is current, or when the till cannot reach the server. */
export function checkAppUpdate(): Promise<AppUpdate | null> {
  return invoke<AppUpdate | null>("check_app_update");
}

/** Downloads the published installer, runs it silently, then the installer restarts the register. */
export function installAppUpdate(): Promise<void> {
  return invoke("install_app_update");
}

export function pinLogin(username: string, pin: string): Promise<CashierSession> {
  return invoke<CashierSession>("pin_login", { username, pin });
}

export function currentSession(): Promise<CashierSession | null> {
  return invoke<CashierSession | null>("current_session");
}

export function lockSession(): Promise<void> {
  return invoke("lock_session");
}

const PREVIEW_TERMINAL_KEY = "ai-pos.preview-terminal";

interface TauriBridge {
  invoke: (command: string, args?: Record<string, unknown>) => Promise<unknown>;
}

function bridge(): TauriBridge | null {
  if (typeof window === "undefined") return null;
  const internals = (window as Window & { __TAURI_INTERNALS__?: { invoke?: unknown } }).__TAURI_INTERNALS__;
  return typeof internals?.invoke === "function" ? (internals as TauriBridge) : null;
}

/** True only inside the desktop window. A browser tab on the Vite URL has no Tauri bridge. */
export function inTauri(): boolean {
  return bridge() !== null;
}

/** Activated identity of this register (no device token; that stays in Rust). */
export interface TerminalStatus {
  activated: boolean;
  source: "activation" | "env" | "none";
  tenant_slug: string;
  tenant_name: string;
  tenant_domain: string;
  tenant_url: string;
  store_id: string;
  store_code: string;
  store_name: string;
  register_id: string;
  register_code: string;
  register_name: string;
}

export function terminalStatus(): Promise<TerminalStatus> {
  return invoke<TerminalStatus>("terminal_status");
}

interface ActivationResponse {
  tenant_slug: string;
  tenant_name: string;
  tenant_domain: string;
  tenant_url: string;
  store_id: string;
  store_code: string;
  store_name: string;
  register_id: string;
  register_code: string;
  register_name: string;
  device_token: string;
}

interface PreviewTerminal {
  status: TerminalStatus;
  device_token: string;
}

function baseDomain(): string {
  const raw = import.meta.env.VITE_TENANT_BASE_DOMAIN;
  const value = typeof raw === "string" ? raw.trim() : "";
  return (value || "axizpos.com").replace(/^\./, "").toLowerCase();
}

function directIp(host: string): boolean {
  return /^\d{1,3}(?:\.\d{1,3}){3}$/.test(host) || host.includes(":");
}

export function readPreviewTerminal(): PreviewTerminal | null {
  if (typeof localStorage === "undefined") return null;
  const raw = localStorage.getItem(PREVIEW_TERMINAL_KEY);
  if (raw === null) return null;
  try {
    const parsed = JSON.parse(raw) as PreviewTerminal;
    if (!parsed.status?.activated || parsed.device_token === "") return null;
    return parsed;
  } catch {
    return null;
  }
}

export function applyPreviewTerminal(saved: PreviewTerminal): void {
  env.apiKey = saved.device_token;
  env.storeId = saved.status.store_id;
  if (saved.status.tenant_domain) env.tenantDomain = saved.status.tenant_domain;
}

/** The desktop window stores this in terminal.bin. The browser preview calls the same API and keeps the token locally. */
export async function activateTerminal(subdomain: string, activationKey: string): Promise<TerminalStatus> {
  if (inTauri()) return invoke<TerminalStatus>("activate_terminal", { subdomain, activationKey });
  const slug = subdomain.trim().toLowerCase();
  const host = baseDomain();
  const domain = directIp(host) ? slug : `${slug}.${host}`;
  const apiBaseUrl = directIp(host) ? `http://${host}` : env.apiBaseUrl;
  const key = activationKey.toUpperCase().replace(/[^A-Z0-9]/g, "");
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/api/v1/terminals/activate`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Tenant-Domain": domain },
      body: JSON.stringify({ activation_key: key, machine_name: "Browser preview" }),
    });
  } catch {
    throw new Error(`Could not reach the API at ${apiBaseUrl}.`);
  }
  const body = (await response.json().catch(() => null)) as { error?: { message?: string } } | ActivationResponse | null;
  if (!response.ok || body === null || !("device_token" in body)) {
    const message = body && "error" in body ? body.error?.message : null;
    throw new Error(message || `Activation failed (${response.status}).`);
  }
  const status: TerminalStatus = {
    activated: true,
    source: "activation",
    tenant_slug: body.tenant_slug,
    tenant_name: body.tenant_name,
    tenant_domain: body.tenant_domain || domain,
    tenant_url: body.tenant_url,
    store_id: body.store_id,
    store_code: body.store_code,
    store_name: body.store_name,
    register_id: body.register_id,
    register_code: body.register_code,
    register_name: body.register_name,
  };
  const saved = { status, device_token: body.device_token };
  localStorage.setItem(PREVIEW_TERMINAL_KEY, JSON.stringify(saved));
  applyPreviewTerminal(saved);
  return status;
}

export function deactivateTerminal(username: string, pin: string): Promise<void> {
  return invoke("deactivate_terminal", { username, pin });
}

/** The activated register's device token, so the cashier screen can open the table socket. */
export function terminalApiKey(): Promise<string> {
  return invoke<string>("terminal_api_key");
}

/** Keeps the latest table-sync frames in the register's SQLite file when the cloud socket blips. */
export function cacheTableEvent(storeId: string, payload: string): Promise<void> {
  return invoke("cache_table_event", { storeId, payload });
}

async function invoke<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  if (bridge() === null) {
    throw new Error("This action only works in the AI POS desktop window.");
  }
  const core = await import("@tauri-apps/api/core");
  return core.invoke<T>(command, args);
}

export function searchProductsLocal(query: string, limit = 50): Promise<ProductSearchHit<ProductUpsert>[]> {
  return invoke<ProductSearchHit<ProductUpsert>[]>("search_products", { query, limit });
}

export function searchProductsViaShell(query: string, limit = 50): Promise<ProductSearchHit<ProductUpsert>[]> {
  return invoke<ProductSearchHit<ProductUpsert>[]>("remote_search", { query, limit });
}

export function checkBranchesViaShell(params: { productId?: string; serial?: string }): Promise<Availability> {
  return invoke<Availability>("check_branches", { productId: params.productId ?? null, serial: params.serial ?? null });
}

export function enqueueBatch(batchId: string, events: SyncEvent[]): Promise<void> {
  const queued = events.map((event) => ({ id: crypto.randomUUID(), ...event }));
  return invoke("enqueue_events", { batchId, events: queued });
}

export function batchStatus(batchId: string): Promise<BatchStatus | null> {
  return invoke<BatchStatus | null>("batch_status", { batchId });
}

export function flushSync(): Promise<SyncReport> {
  return invoke<SyncReport>("flush_sync");
}

export function pendingCount(): Promise<number> {
  return invoke<number>("pending_count");
}

export function refreshProducts(): Promise<CatalogSnapshot> {
  return invoke<CatalogSnapshot>("refresh_products");
}

export interface CurrencySnapshot {
  currency: string | null;
  tax: {
    enforced: boolean;
    prices_include_vat: boolean;
    standard_rate_bps: number;
    trn: string | null;
    legal_name: string | null;
    legal_name_ar: string | null;
    tax_authority?: "fta" | "zatca";
  } | null;
  /** Null when the API has never sent a profile: every module stays on. */
  profile: {
    business_profile: string | null;
    capabilities: string[];
    planned_capabilities: string[];
    module_settings?: Partial<ModuleSettings> | null;
    practice_mode?: boolean;
    pos_policy?: Partial<PosPolicy> | null;
  } | null;
  /** Receipt branding and this branch's contact lines; null until the register has fetched them once. */
  receipt?: ReceiptProfile | null;
  source: "api" | "cache" | "seed";
  message: string | null;
}

export interface SeriesStatus {
  registered: boolean;
  device_code: string | null;
  message: string | null;
}

export function refreshSeries(): Promise<SeriesStatus> {
  return invoke<SeriesStatus>("refresh_series");
}

/** Next number in this register's offline series, or null when the API numbers its documents. */
export function nextDocumentNumber(docType: "INV" | "CN" | "Z"): Promise<string | null> {
  return invoke<string | null>("next_document_number", { docType });
}

export interface PrinterSettings {
  transport: "none" | "tcp" | "windows";
  address: string;
  paper_dots: 384 | 576;
  drawer_kick: boolean;
  auto_print: boolean;
  copies: number;
}

export interface RasterJob {
  width: number;
  height: number;
  data: number[];
  kick_drawer: boolean;
}

export function printerSettings(): Promise<PrinterSettings> {
  return invoke<PrinterSettings>("printer_settings");
}

export function savePrinterSettings(settings: PrinterSettings): Promise<PrinterSettings> {
  return invoke<PrinterSettings>("save_printer_settings", { settings });
}

export function printRaster(job: RasterJob): Promise<void> {
  return invoke("print_receipt", { job });
}

export function openCashDrawer(): Promise<void> {
  return invoke("open_cash_drawer");
}

export function openDocumentPdf(
  kind: "invoice" | "credit_note" | "gift_receipt",
  id: string,
  number: string,
): Promise<string> {
  return invoke<string>("open_document_pdf", { kind, id, number });
}

export interface LocalShift {
  id: string;
  opened_at: string;
  opened_by_name: string;
  opening_float_cents: number;
  currency: string;
  status: "OPEN" | "CLOSED";
  closed_at: string | null;
  closed_by_name: string | null;
  counted_cash_cents: number | null;
  expected_cash_cents: number | null;
  z_number: string | null;
}

export interface ShiftSummary {
  shift: LocalShift;
  sales_count: number;
  sales_total_cents: number;
  /** Tips on top of the sales, owed to staff; cash tips are already in the drawer. */
  tips_cents?: number;
  tenders: Record<string, number>;
  returns_count: number;
  refund_tenders: Record<string, number>;
  pay_in_cents: number;
  pay_out_cents: number;
  drops_cents: number;
  no_sale_count: number;
  /** Zero while the shift is open for cashiers without pos:shift_manage (blind count). */
  expected_cash_cents: number;
  /** Foreign cash received per currency, in that currency's minor units. */
  foreign_cash?: Record<string, number>;
}

export type CashMovementKind = "PAY_IN" | "PAY_OUT" | "CASH_DROP" | "NO_SALE";

export interface LocalTimeEntry {
  id: string;
  user_name: string;
  clock_in_at: string;
  clock_out_at: string | null;
  break_minutes: number;
}

export function clockStatus(): Promise<LocalTimeEntry | null> {
  return invoke<LocalTimeEntry | null>("clock_status");
}

export function clockIn(input: { id: string; at: string }): Promise<LocalTimeEntry> {
  return invoke<LocalTimeEntry>("clock_in", { input });
}

export function clockOut(input: { at: string; break_minutes: number }): Promise<LocalTimeEntry> {
  return invoke<LocalTimeEntry>("clock_out", { input });
}

export function onDuty(): Promise<LocalTimeEntry[]> {
  return invoke<LocalTimeEntry[]>("on_duty");
}

export function currentShift(): Promise<LocalShift | null> {
  return invoke<LocalShift | null>("current_shift");
}

export function openShift(input: { id: string; opened_at: string; opening_float_cents: number; currency: string }): Promise<LocalShift> {
  return invoke<LocalShift>("open_shift", { input });
}

export function recordCashMovement(input: {
  id: string;
  kind: CashMovementKind;
  amount_cents: number;
  reason: string;
  occurred_at: string;
}): Promise<void> {
  return invoke("record_cash_movement", { input });
}

export function shiftSummary(shiftId?: string): Promise<ShiftSummary | null> {
  return invoke<ShiftSummary | null>("shift_summary", { shiftId: shiftId ?? null });
}

export function closeShift(input: {
  closed_at: string;
  counted_cash_cents: number;
  z_number: string | null;
  notes: string;
  counted_foreign?: Record<string, number>;
}): Promise<ShiftSummary> {
  return invoke<ShiftSummary>("close_shift", { input });
}

export interface QueuedBatch {
  batch_id: string;
  status: "pending" | "synced" | "rejected" | "discarded";
  entity_types: string[];
  event_count: number;
  attempts: number;
  last_error: string | null;
  created_at: string;
  summary: string;
}

export function listBatches(status: QueuedBatch["status"] | null, limit = 50): Promise<QueuedBatch[]> {
  return invoke<QueuedBatch[]>("list_batches", { status, limit });
}

export function resolveBatch(batchId: string, action: "retry" | "discard"): Promise<void> {
  return invoke("resolve_batch", { batchId, action });
}

export function rejectedCount(): Promise<number> {
  return invoke<number>("rejected_count");
}

export function fetchBusinessCurrency(): Promise<CurrencySnapshot> {
  return invoke<CurrencySnapshot>("business_currency");
}

export interface LocalReturn {
  id: string;
  sale_id: string;
  batch_id: string;
  status: BatchStatus["status"];
  error: string | null;
  created_at: number;
  payload: ReturnUpsert;
}

export interface ReceiptLookup {
  source: "api" | "cache" | "register";
  receipt: Receipt | null;
  queued_sale: SaleUpsert | null;
  local_returns: LocalReturn[];
  message: string | null;
}

export function lookupReceiptViaShell(code: string): Promise<ReceiptLookup> {
  return invoke<ReceiptLookup>("lookup_receipt", { code });
}

export function approveReturn(username: string, pin: string): Promise<CashierProfile> {
  return invoke<CashierProfile>("approve_return", { username, pin });
}

export function enqueueReturn(batchId: string, events: SyncEvent[]): Promise<void> {
  const queued = events.map((event) => ({ id: crypto.randomUUID(), ...event }));
  return invoke("enqueue_return", { batchId, events: queued });
}

export function recentReturns(limit = 20): Promise<LocalReturn[]> {
  return invoke<LocalReturn[]>("recent_returns", { limit });
}

/** Checkout overrides: "pos:price_override" for prices, "customers:manage" for credit limits. */
export function approveManager(username: string, pin: string, permission: string): Promise<CashierProfile> {
  return invoke<CashierProfile>("approve_manager", { username, pin, permission });
}

/** Cached customer row; balances include on-account sales still queued on this register. */
export type RegisterCustomer = Customer & { pending_on_account_cents?: number };

export interface CustomerSnapshot {
  customers: RegisterCustomer[];
  source: "api" | "cache";
  message: string | null;
}

export function refreshCustomers(): Promise<CustomerSnapshot> {
  return invoke<CustomerSnapshot>("refresh_customers");
}

export function searchCustomersLocal(query: string, limit = 20): Promise<RegisterCustomer[]> {
  return invoke<RegisterCustomer[]>("search_customers", { query, limit });
}

/** A customer added at the register: cached locally at once and queued for the server. */
export interface NewRegisterCustomer {
  id: string;
  name: string;
  phone: string | null;
  email: string | null;
  customer_type: "RETAIL" | "WHOLESALE";
  company_name: string | null;
  trn_vat_number: string | null;
  price_tier: string;
  credit_limit_cents: number;
  payment_terms: string;
  at: string;
}

export function createCustomerLocal(input: NewRegisterCustomer): Promise<RegisterCustomer> {
  return invoke<RegisterCustomer>("create_customer", { input });
}

export interface RegisterSerial {
  id: string;
  product_id: string;
  kind: "imei" | "serial";
  value: string;
}

export interface SerialRefresh {
  count: number;
  source: "api" | "cache";
  message: string | null;
}

export type SerialCheckStatus = "available" | "taken" | "other_product" | "unknown";

export interface SerialCheck {
  value: string;
  status: SerialCheckStatus;
  product_id: string | null;
  kind: "imei" | "serial" | null;
}

export function refreshSerials(): Promise<SerialRefresh> {
  return invoke<SerialRefresh>("refresh_serials");
}

export function availableSerialsLocal(productId: string, limit: number, exclude: string[]): Promise<RegisterSerial[]> {
  return invoke<RegisterSerial[]>("available_serials", { productId, limit, exclude });
}

export function countSerialsLocal(productId: string): Promise<number> {
  return invoke<number>("count_serials", { productId });
}

export function checkSerialsLocal(productId: string, values: string[]): Promise<SerialCheck[]> {
  return invoke<SerialCheck[]>("check_serials", { productId, values });
}

export function createQuoteViaShell(payload: QuoteUpsert): Promise<Quote> {
  return invoke<Quote>("create_quote", { payload });
}

export function openQuotePdfViaShell(quoteId: string, number: string): Promise<string> {
  return invoke<string>("open_quote_pdf", { quoteId, number });
}

/** Register-floor actions the checkout screen logs; logins and manager approvals are logged by the shell. */
export interface RegisterAuditInput {
  action_type: Extract<DesktopAuditActionType, "DRAWER_OPEN" | "CASH_DROP" | "ITEM_VOID">;
  action: string;
  target_entity: string;
  target_entity_id?: string | null;
  reason_notes?: string | null;
  old_values?: Record<string, unknown> | null;
  new_values?: Record<string, unknown> | null;
  details?: Record<string, unknown>;
}

export interface LocalAuditEvent {
  id: string;
  occurred_at: string;
  action_type: DesktopAuditActionType;
  action: string;
  user_name: string;
  reason_notes: string | null;
  details: Record<string, unknown> | null;
  status: "pending" | "synced" | "rejected";
  last_error: string | null;
}

export interface AuditQueueStatus {
  pending: number;
  rejected: number;
  last_error: string | null;
}

export function logAuditEvent(event: RegisterAuditInput): Promise<string> {
  return invoke<string>("log_audit_event", { event });
}

export function auditStatus(): Promise<AuditQueueStatus> {
  return invoke<AuditQueueStatus>("audit_status");
}

export function recentAuditEvents(limit = 20): Promise<LocalAuditEvent[]> {
  return invoke<LocalAuditEvent[]>("recent_audit_events", { limit });
}

export interface ScaleConfig {
  port: string;
  baud: number;
  protocol: "continuous" | "request";
}

export interface ScaleReading {
  grams: number;
  stable: boolean;
  raw: string;
}

export function scalePorts(): Promise<string[]> {
  return invoke<string[]>("scale_ports");
}

export function readScale(config: ScaleConfig): Promise<ScaleReading> {
  return invoke<ScaleReading>("read_scale", { config });
}
