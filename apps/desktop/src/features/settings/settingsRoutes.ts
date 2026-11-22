import { isSupportedCurrency } from "@ai-pos/shared-types";

export type SettingsGroup = "business" | "system";
export type SettingsScope = "business" | "branch" | "register";

export interface SettingsRoute {
  id: string;
  /** Full name. Used by the page title, search, and screen readers. */
  label: string;
  /** Short name shown in the settings sidebar. */
  short: string;
  description: string;
  group: SettingsGroup;
  scope: SettingsScope;
  /** Business Pro owns the edit. The register shows the current value. */
  managed: boolean;
  keywords: string[];
  /** Limit to these business profiles. */
  profiles?: string[];
  /** Shown only when this register can edit staff. */
  staff?: boolean;
}

const RAIL_KEY = "ai-pos.pos-settings-rail";

export function readSettingsRail(): boolean | null {
  try {
    const value = localStorage.getItem(RAIL_KEY);
    if (value === "collapsed") return true;
    if (value === "expanded") return false;
  } catch {
    /* Storage can be blocked. The sidebar still opens expanded. */
  }
  return null;
}

export function storeSettingsRail(collapsed: boolean): void {
  try {
    localStorage.setItem(RAIL_KEY, collapsed ? "collapsed" : "expanded");
  } catch {
    /* The choice still applies until the page is reloaded. */
  }
}

export const SETTINGS_ROUTES: readonly SettingsRoute[] = [
  { id: "overview", label: "Settings overview", short: "Overview", description: "Business operations and this register.", group: "business", scope: "business", managed: false, keywords: ["home"] },
  { id: "business-profile", label: "Business profile", short: "Business", description: "Legal name, address, business type, and branding.", group: "business", scope: "business", managed: true, keywords: ["legal", "address", "logo", "hours", "contact"] },
  { id: "currency", label: "Finance and currency", short: "Finance", description: "Business currency, exchange rates, and conversion estimates.", group: "business", scope: "business", managed: false, keywords: ["exchange", "rate", "money", "decimal"] },
  { id: "tax", label: "Tax and invoicing", short: "Tax & invoices", description: "VAT registration, tax-inclusive prices, and invoice identity.", group: "business", scope: "branch", managed: true, keywords: ["vat", "trn", "invoice", "branch tax"] },
  { id: "sales", label: "Sales and POS rules", short: "Sales rules", description: "Till rules, returns, and discounts.", group: "business", scope: "business", managed: true, keywords: ["till", "refund", "discount", "checkout"] },
  { id: "catalogue", label: "Products and inventory", short: "Products", description: "Catalogue, units, stock rules, and profile-specific items.", group: "business", scope: "business", managed: true, keywords: ["sku", "barcode", "expiry", "fefo", "weighed", "garment"] },
  { id: "customers", label: "Customers and loyalty", short: "Customers", description: "Customer rules and loyalty, when this business uses them.", group: "business", scope: "business", managed: true, keywords: ["loyalty", "points", "credit"] },
  { id: "staff", label: "Staff and permissions", short: "Staff & access", description: "Staff on this register and the roles they can be granted.", group: "business", scope: "branch", managed: false, staff: true, keywords: ["pin", "role", "cashier"] },
  { id: "modules", label: "Modules and add-ons", short: "Modules", description: "Modules this business has turned on.", group: "business", scope: "business", managed: true, keywords: ["addon", "subscription", "entitlement"] },
  { id: "workflows", label: "Workflows and operations", short: "Workflows", description: "Operating rules. Laundry production lives in its own pages.", group: "business", scope: "business", managed: true, keywords: ["approval", "workflow"] },
  { id: "laundry-services", label: "Laundry services", short: "Services", description: "Service catalogue, piece and kilogram pricing.", group: "business", scope: "business", managed: true, profiles: ["laundry"], keywords: ["garment", "kg", "service"] },
  { id: "laundry-workflows", label: "Laundry workflows", short: "Laundry flow", description: "Workflow templates and tracking mode.", group: "business", scope: "business", managed: true, profiles: ["laundry"], keywords: ["stages", "tracking", "express"] },
  { id: "laundry-stations", label: "Production stations", short: "Production", description: "Stations this role can open.", group: "business", scope: "branch", managed: true, profiles: ["laundry"], keywords: ["intake", "packing", "ready"] },
  { id: "laundry-machines", label: "Machines", short: "Machines", description: "Machine registration stays in Business Pro.", group: "business", scope: "branch", managed: true, profiles: ["laundry"], keywords: ["washer", "dryer", "cycle"] },
  { id: "laundry-quality", label: "Quality rules", short: "Quality", description: "Inspection checks recorded on the floor.", group: "business", scope: "business", managed: true, profiles: ["laundry"], keywords: ["stain", "rework", "inspector"] },
  { id: "laundry-tags", label: "Tags and labels", short: "Tags", description: "Tags issued when the server accepts an order.", group: "business", scope: "business", managed: true, profiles: ["laundry"], keywords: ["tag", "reprint"] },
  { id: "integrations", label: "Integrations", short: "Integrations", description: "Payment and accounting connections. Secrets stay off this register.", group: "business", scope: "business", managed: true, keywords: ["api", "erp", "payment"] },
  { id: "notifications", label: "Notifications", short: "Alerts", description: "Business alerts. This register does not edit the policy.", group: "business", scope: "business", managed: true, keywords: ["alert", "stock alert"] },
  { id: "audit", label: "Audit trail", short: "Audit trail", description: "Who last changed business settings. The trail is read-only.", group: "business", scope: "business", managed: true, keywords: ["history", "actor"] },
  { id: "terminal", label: "Register and terminal", short: "Register", description: "This terminal, its branch, and activation.", group: "system", scope: "register", managed: false, keywords: ["activation", "device", "terminal"] },
  { id: "hardware", label: "Receipt Printer & Cash Drawer", short: "Printer & drawer", description: "Receipt printer and the cash drawer connected through it, plus the scale on this register.", group: "system", scope: "register", managed: false, keywords: ["printer", "drawer", "scale", "scanner"] },
  { id: "connectivity", label: "Connectivity and offline", short: "Connectivity", description: "Whether this register can reach the API.", group: "system", scope: "register", managed: false, keywords: ["offline", "online", "api"] },
  { id: "security", label: "Security and session", short: "Security", description: "Lock and the local session. Policies stay central.", group: "system", scope: "register", managed: true, keywords: ["lock", "pin", "session"] },
  { id: "appearance", label: "Appearance and language", short: "Appearance", description: "Accent, theme, and checkout density on this register.", group: "system", scope: "register", managed: false, keywords: ["theme", "dark", "language", "density"] },
  { id: "keyboard", label: "Keyboard and shortcuts", short: "Shortcuts", description: "The touch keyboard on this register.", group: "system", scope: "register", managed: false, keywords: ["shortcut", "touch"] },
  { id: "sync", label: "Sync and local data", short: "Sync & data", description: "Queue health published by the open page.", group: "system", scope: "register", managed: false, keywords: ["queue", "pending", "conflict"] },
  { id: "updates", label: "Updates and downloads", short: "Updates", description: "The POS version on this register.", group: "system", scope: "register", managed: false, keywords: ["version", "installer"] },
  { id: "diagnostics", label: "Diagnostics and logs", short: "Diagnostics", description: "Reachability of business settings. No secrets are shown.", group: "system", scope: "register", managed: false, keywords: ["health", "error"] },
];

const ALIASES: Record<string, string> = {
  receipts: "hardware",
  "till-rules": "sales",
  "branch-tax": "tax",
  vat: "tax",
  "module-settings": "modules",
  "module-setup": "modules",
  addons: "modules",
  "addon-access": "modules",
  stores: "business-profile",
  roles: "staff",
  registers: "terminal",
  downloads: "updates",
  currencies: "currency",
  "laundry-floor": "laundry-workflows",
};

const KNOWN = new Set(SETTINGS_ROUTES.map((item) => item.id));

export function settingsSection(hash: string): string {
  const path = (hash.startsWith("#") ? hash.slice(1) : hash).split("?")[0] ?? "";
  if (path === "/settings" || path === "/settings/") return "overview";
  if (!path.startsWith("/settings/")) return "overview";
  const raw = path.slice("/settings/".length);
  const id = ALIASES[raw] ?? raw;
  return KNOWN.has(id) ? id : "overview";
}

export function settingsLocation(id: string): string {
  if (id === "overview") return "#/settings";
  return `#/settings/${KNOWN.has(id) ? id : "overview"}`;
}

export function visibleSettings(profile: string, staff: boolean): SettingsRoute[] {
  return SETTINGS_ROUTES.filter((item) => {
    if (item.profiles && !item.profiles.includes(profile)) return false;
    if (item.staff && !staff) return false;
    return true;
  });
}

export function searchSettings(routes: readonly SettingsRoute[], query: string): SettingsRoute[] {
  const text = query.trim().toLowerCase();
  if (text === "") return [];
  return routes.filter((item) =>
    [item.label, item.short, item.description, item.scope, ...item.keywords].join(" ").toLowerCase().includes(text),
  );
}

export function scopeLabel(scope: SettingsScope, managed: boolean): string {
  if (managed && scope !== "register") return "Managed in Business Pro";
  if (scope === "business") return "Business-wide";
  if (scope === "branch") return "Branch-specific";
  return "Register-specific";
}

/** Save stays off until a different supported currency is chosen and the user may change it. */
export function currencySaveEnabled(current: string, choice: string, canManage: boolean, busy: boolean): boolean {
  return canManage && !busy && choice !== current && isSupportedCurrency(choice);
}
