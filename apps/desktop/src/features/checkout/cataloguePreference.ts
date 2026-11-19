/**
 * The cashier's product catalogue view.
 *
 * Stored per tenant and user. A sign-out drops the in-memory copy and leaves the
 * saved row in place. Sync is separate from the sales queue: a failed request
 * keeps the local row dirty and the next online reconcile sends it.
 */

export const CATALOGUE_VIEWS = ["grid", "list", "compact"] as const;
export type CatalogueView = (typeof CATALOGUE_VIEWS)[number];
export const DEFAULT_CATALOGUE_VIEW: CatalogueView = "grid";
export const CATALOGUE_VIEW_KEY = "product_catalogue_view";

export interface CataloguePreference {
  tenantId: string;
  userId: string;
  value: CatalogueView;
  updatedAt: string;
  revision: number;
  dirty: boolean;
}

export interface RemoteCatalogue {
  product_catalogue_view: CatalogueView;
  updated_at: string | null;
  revision: number;
}

export interface CatalogueTransport {
  /** Null when the register cannot reach the account. */
  read(): Promise<RemoteCatalogue | null>;
  /** Null when the save could not reach the account. The local row stays dirty. */
  write(local: CataloguePreference): Promise<RemoteCatalogue | null>;
}

export interface DurableCatalogueStore {
  read(tenantId: string, userId: string): Promise<CataloguePreference | null>;
  write(preference: CataloguePreference): Promise<void>;
}

interface KeyValue {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export interface CatalogueSessionState {
  userId: string | null;
  view: CatalogueView;
}

export type CatalogueSessionAction =
  | { type: "sign_in"; userId: string; stored: CatalogueView | null }
  | { type: "sign_out" }
  | { type: "choose"; view: CatalogueView }
  | { type: "adopt"; view: CatalogueView };

const memoryFallback = new Map<string, string>();
let storageOverride: KeyValue | null = null;
let durable: DurableCatalogueStore | null = null;
let active: { userId: string; view: CatalogueView } | null = null;
/** Bumps when the cashier picks a view so an older sync cannot write over that pick. */
let writeGeneration = 0;

export function parseCatalogueView(value: unknown): CatalogueView | null {
  return CATALOGUE_VIEWS.find((item) => item === value) ?? null;
}

export function catalogueStorageKey(tenantId: string, userId: string): string {
  return `axiz.pos.pref.v1:${tenantId}:${userId}:${CATALOGUE_VIEW_KEY}`;
}

export function preferenceTime(value: string | null | undefined): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

/** Sign-out drops the cashier currently on screen. The saved preference stays. */
export function clearCataloguePreferenceMemory(): void {
  active = null;
}

export function setDurableCatalogueStore(store: DurableCatalogueStore | null): void {
  durable = store;
}

export function resetCataloguePreferences(next?: KeyValue): void {
  active = null;
  durable = null;
  writeGeneration = 0;
  storageOverride = next ?? mapStorage(new Map());
}

function mapStorage(map: Map<string, string>): KeyValue {
  return {
    getItem: (key) => map.get(key) ?? null,
    setItem: (key, value) => {
      map.set(key, value);
    },
    removeItem: (key) => {
      map.delete(key);
    },
  };
}

function bucket(): KeyValue {
  if (storageOverride) return storageOverride;
  if (typeof localStorage !== "undefined") return localStorage;
  return mapStorage(memoryFallback);
}

export function readPreference(tenantId: string, userId: string): CataloguePreference | null {
  if (!tenantId || !userId) return null;
  const raw = bucket().getItem(catalogueStorageKey(tenantId, userId));
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<CataloguePreference>;
    const value = parseCatalogueView(parsed.value);
    if (!value || parsed.tenantId !== tenantId || parsed.userId !== userId) return null;
    if (typeof parsed.updatedAt !== "string" || typeof parsed.revision !== "number") return null;
    return {
      tenantId,
      userId,
      value,
      updatedAt: parsed.updatedAt,
      revision: parsed.revision,
      dirty: parsed.dirty === true,
    };
  } catch {
    return null;
  }
}

export function writePreference(preference: CataloguePreference): void {
  bucket().setItem(catalogueStorageKey(preference.tenantId, preference.userId), JSON.stringify(preference));
  if (active?.userId === preference.userId) active = { userId: preference.userId, view: preference.value };
}

export function storedCatalogueView(tenantId: string, userId: string): CatalogueView {
  if (active?.userId === userId) return active.view;
  return readPreference(tenantId, userId)?.value ?? DEFAULT_CATALOGUE_VIEW;
}

export function reduceCatalogueSession(state: CatalogueSessionState, action: CatalogueSessionAction): CatalogueSessionState {
  switch (action.type) {
    case "sign_out":
      return { userId: null, view: DEFAULT_CATALOGUE_VIEW };
    case "sign_in":
      return { userId: action.userId, view: action.stored ?? DEFAULT_CATALOGUE_VIEW };
    case "choose":
    case "adopt":
      if (state.userId === null) return state;
      return { ...state, view: action.view };
    default:
      return state;
  }
}

export function planCatalogueSync(
  local: CataloguePreference | null,
  remote: RemoteCatalogue | null,
): { view: CatalogueView; pushLocal: boolean; adoptRemote: boolean } {
  if (local === null && remote === null) {
    return { view: DEFAULT_CATALOGUE_VIEW, pushLocal: false, adoptRemote: false };
  }
  if (local === null && remote) {
    return { view: remote.product_catalogue_view, pushLocal: false, adoptRemote: true };
  }
  if (local === null) return { view: DEFAULT_CATALOGUE_VIEW, pushLocal: false, adoptRemote: false };
  if (remote === null) return { view: local.value, pushLocal: local.dirty, adoptRemote: false };
  const remoteTime = preferenceTime(remote.updated_at);
  if (remoteTime === null) {
    const push = local.dirty || local.value !== DEFAULT_CATALOGUE_VIEW;
    return { view: local.value, pushLocal: push, adoptRemote: false };
  }
  const localTime = preferenceTime(local.updatedAt) ?? 0;
  if (local.dirty && localTime > remoteTime) return { view: local.value, pushLocal: true, adoptRemote: false };
  if (local.dirty && localTime <= remoteTime) {
    return { view: remote.product_catalogue_view, pushLocal: false, adoptRemote: true };
  }
  if (remoteTime > localTime) return { view: remote.product_catalogue_view, pushLocal: false, adoptRemote: true };
  return { view: local.value, pushLocal: false, adoptRemote: false };
}

export async function loadLocalPreference(tenantId: string, userId: string): Promise<CataloguePreference | null> {
  const browser = readPreference(tenantId, userId);
  if (!durable) return browser;
  try {
    const row = await durable.read(tenantId, userId);
    if (!row || row.tenantId !== tenantId || row.userId !== userId) return browser;
    const rowTime = preferenceTime(row.updatedAt) ?? 0;
    const browserTime = browser ? (preferenceTime(browser.updatedAt) ?? 0) : -1;
    if (browser && browserTime > rowTime) return browser;
    writePreference(row);
    return row;
  } catch {
    return browser;
  }
}

function remember(userId: string, view: CatalogueView): void {
  active = { userId, view };
}

function adoptRemote(tenantId: string, userId: string, remote: RemoteCatalogue): CataloguePreference {
  const saved: CataloguePreference = {
    tenantId,
    userId,
    value: remote.product_catalogue_view,
    updatedAt: remote.updated_at ?? new Date().toISOString(),
    revision: remote.revision,
    dirty: false,
  };
  writePreference(saved);
  return saved;
}

async function mirrorDurable(preference: CataloguePreference): Promise<void> {
  if (!durable) return;
  try {
    await durable.write(preference);
  } catch {
    // The browser copy is already current. The next reconcile retries the durable copy.
  }
}

function stillCurrent(generation: number): boolean {
  return generation === writeGeneration;
}

export async function saveCatalogueView(
  tenantId: string,
  userId: string,
  view: CatalogueView,
  transport: CatalogueTransport,
): Promise<CatalogueView> {
  const generation = ++writeGeneration;
  const previous = await loadLocalPreference(tenantId, userId);
  const local: CataloguePreference = {
    tenantId,
    userId,
    value: view,
    updatedAt: new Date().toISOString(),
    revision: (previous?.revision ?? 0) + 1,
    dirty: true,
  };
  writePreference(local);
  remember(userId, view);
  await mirrorDurable(local);
  const remote = await transport.write(local);
  if (!stillCurrent(generation)) return (await loadLocalPreference(tenantId, userId))?.value ?? view;
  if (remote === null) return view;
  const saved = adoptRemote(tenantId, userId, remote);
  await mirrorDurable(saved);
  remember(userId, saved.value);
  return saved.value;
}

export async function reconcileCatalogueView(
  tenantId: string,
  userId: string,
  transport: CatalogueTransport,
): Promise<CatalogueView> {
  const generation = writeGeneration;
  const remote = await transport.read();
  if (!stillCurrent(generation)) return (await loadLocalPreference(tenantId, userId))?.value ?? DEFAULT_CATALOGUE_VIEW;
  const local = await loadLocalPreference(tenantId, userId);
  if (remote === null) {
    const view = local?.value ?? DEFAULT_CATALOGUE_VIEW;
    remember(userId, view);
    return view;
  }
  const plan = planCatalogueSync(local, remote);
  if (plan.pushLocal && local) {
    const pushed = await transport.write(local);
    if (!stillCurrent(generation)) return (await loadLocalPreference(tenantId, userId))?.value ?? local.value;
    if (pushed === null) {
      remember(userId, local.value);
      return local.value;
    }
    const saved = adoptRemote(tenantId, userId, pushed);
    await mirrorDurable(saved);
    remember(userId, saved.value);
    return saved.value;
  }
  if (plan.adoptRemote) {
    if (!stillCurrent(generation)) return (await loadLocalPreference(tenantId, userId))?.value ?? plan.view;
    const saved = adoptRemote(tenantId, userId, remote);
    await mirrorDurable(saved);
    remember(userId, saved.value);
    return saved.value;
  }
  remember(userId, plan.view);
  return plan.view;
}
