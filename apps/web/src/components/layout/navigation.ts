import { Capability, Permission, profileSpec, type BusinessProfile } from "@ai-pos/shared-types";
import {
  ArrowLeftRight,
  BadgeCheck,
  Ban,
  Banknote,
  Blocks,
  BookOpenCheck,
  ChartColumn,
  Boxes,
  ChefHat,
  ClipboardList,
  Clock,
  CreditCard,
  FileSpreadsheet,
  FileText,
  Gift,
  HandCoins,
  Handshake,
  Landmark,
  LayoutDashboard,
  LayoutGrid,
  Percent,
  Radar,
  ReceiptText,
  Repeat2,
  RotateCcw,
  ScanBarcode,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Smartphone,
  Sparkles,
  Tag,
  TicketPercent,
  Timer,
  Truck,
  UserCog,
  Users,
  UtensilsCrossed,
  Wallet,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { FASHION_PROFILES, FNB_PROFILES, RETAIL_PROFILES } from "../../lib/industry";
import { portalHomePath } from "../../lib/portal-home";

/** What the navigation adapts to: the business type (for names) and its switched-on modules (for visibility). */
export interface NavContext {
  profile: BusinessProfile;
  has: (capability: Capability) => boolean;
}

export interface NavItem {
  to: string;
  /** A function when the name depends on the business type or its modules. */
  label: string | ((ctx: NavContext) => string);
  icon: LucideIcon;
  permission: Permission;
  /** Hidden while this module is switched off for the business. */
  capability?: Capability;
  /** Hidden unless the tenant's business type is in this list. Stricter than the module switch. */
  profiles?: readonly BusinessProfile[];
  /** Business-wide settings need a manager who is not pinned to one store. */
  settingsOnly?: boolean;
  /** Platform files (the POS installer) are for the Super Admin role only. */
  superAdminOnly?: boolean;
  /** Opens the first Store settings tab this user is allowed to see. */
  hub?: boolean;
  isActive: (pathname: string, hash?: string) => boolean;
  /** Shows the AI mark in front of the label. */
  ai?: boolean;
}

/** Pages that live under Store settings. Users and Staff & payroll stay in the sidebar. */
export interface SettingsTab {
  to: string;
  label: string;
  permission: Permission;
  capability?: Capability;
  profiles?: readonly BusinessProfile[];
  settingsOnly?: boolean;
  superAdminOnly?: boolean;
  /** Exact match, so General is not selected on /settings/audit-logs. */
  end?: boolean;
}

export const settingsTabs: SettingsTab[] = [
  { to: "/settings", label: "General", permission: Permission.SettingsManage, settingsOnly: true, end: true },
  { to: "/settings/addons", label: "Add-ons", permission: Permission.SettingsManage, settingsOnly: true },
  { to: "/stores", label: "Stores", permission: Permission.PortalAccess },
  { to: "/roles", label: "Roles", permission: Permission.UsersRead },
  { to: "/settings/addon-access", label: "Add-on access", permission: Permission.UsersRead },
  { to: "/registers", label: "Registers", permission: Permission.DevicesManage },
  { to: "/downloads", label: "Downloads", permission: Permission.PortalAccess, superAdminOnly: true },
  { to: "/settings/currencies", label: "Currencies", permission: Permission.CurrenciesManage, capability: Capability.MultiCurrency },
  { to: "/settings/messaging", label: "Messaging", permission: Permission.MessagingManage },
  {
    to: "/settings/channels",
    label: "Delivery channels",
    permission: Permission.SettingsManage,
    capability: Capability.DeliveryChannels,
  },
  { to: "/settings/audit-logs", label: "Audit trail", permission: Permission.AuditRead },
];

export function settingsTabAllowed(
  tab: SettingsTab,
  gate: {
    can: (permission: Permission) => boolean;
    canManageSettings: boolean;
    superAdmin: boolean;
    has: (capability: Capability) => boolean;
    allows: (profiles?: readonly BusinessProfile[]) => boolean;
  },
): boolean {
  if (!gate.allows(tab.profiles)) return false;
  if (tab.capability !== undefined && !gate.has(tab.capability)) return false;
  if (tab.superAdminOnly && !gate.superAdmin) return false;
  if (tab.settingsOnly) return gate.canManageSettings;
  return gate.can(tab.permission);
}

export function inSettingsHub(pathname: string): boolean {
  return settingsTabs.some((tab) => pathname === tab.to || pathname.startsWith(`${tab.to}/`));
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export function labelOf(item: NavItem, ctx: NavContext): string {
  return typeof item.label === "function" ? item.label(ctx) : item.label;
}

/** "Store settings", "Restaurant settings", "Cafe settings"... */
export function settingsLabel(ctx: Pick<NavContext, "profile">): string {
  return profileSpec(ctx.profile).settingsLabel;
}

const under = (...prefixes: string[]) => (pathname: string) =>
  prefixes.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));

const inventoryOwn = (pathname: string) =>
  under("/inventory")(pathname) &&
  !under(
    "/inventory/purchase-orders",
    "/inventory/transfers",
    "/inventory/serials",
    "/inventory/modifiers",
    "/inventory/markdowns",
    "/inventory/size-curve",
    "/inventory/floor-plan",
    "/inventory/kitchen",
    "/inventory/kitchen-agent",
    "/inventory/recipes",
    "/inventory/recipe-usage",
  )(pathname);

/** Grouped by domain; a group whose items are all switched off for this business type disappears. */
export const navGroups: NavGroup[] = [
  {
    label: "Workspace",
    items: [
      { to: portalHomePath(), label: "Dashboard", icon: LayoutDashboard, permission: Permission.PortalReportsRead, isActive: (path) => path === "/" || path === "/dashboard" },
      { to: "/assistant", label: "AI assistant", icon: Sparkles, permission: Permission.PortalReportsRead, isActive: under("/assistant") },
      { to: "/insights", label: "AI insights", icon: Radar, ai: true, permission: Permission.PortalReportsRead, isActive: under("/insights") },
      { to: "/m", label: "Manager app", icon: Smartphone, permission: Permission.PortalReportsRead, isActive: under("/m") },
      {
        to: "/inventory",
        label: (ctx) => (profileSpec(ctx.profile).group === "food_beverage" ? "Inventory" : "Inventory & Batches"),
        icon: Boxes,
        permission: Permission.PortalAccess,
        isActive: inventoryOwn,
      },
      {
        to: "/inventory/purchase-orders",
        label: "Purchase Orders",
        icon: FileText,
        permission: Permission.PortalAccess,
        isActive: under("/inventory/purchase-orders"),
      },
      {
        to: "/inventory/transfers",
        label: (ctx) =>
          ctx.profile === "electronics_wholesale" && ctx.has(Capability.SerialTracking) ? "Transfers & IMEI" : "Transfers",
        icon: ArrowLeftRight,
        permission: Permission.PortalAccess,
        isActive: under("/inventory/transfers"),
      },
      {
        to: "/inventory/serials",
        label: "IMEI / Serial tracking",
        icon: ScanBarcode,
        permission: Permission.PortalAccess,
        capability: Capability.SerialTracking,
        isActive: under("/inventory/serials"),
      },
      {
        to: "/inventory/markdowns",
        label: "Markdowns",
        icon: Percent,
        permission: Permission.PortalAccess,
        capability: Capability.VariantsMatrix,
        profiles: FASHION_PROFILES,
        isActive: under("/inventory/markdowns"),
      },
      {
        to: "/inventory/size-curve",
        label: "Size & color matrix",
        icon: ChartColumn,
        permission: Permission.PortalReportsRead,
        capability: Capability.VariantsMatrix,
        profiles: FASHION_PROFILES,
        isActive: under("/inventory/size-curve"),
      },
      {
        to: "/customers",
        label: (ctx) => (ctx.profile === "electronics_wholesale" ? "Customers & B2B credit" : "Suppliers & CRM"),
        icon: Users,
        permission: Permission.CustomersManage,
        isActive: under("/customers"),
      },
    ],
  },
  {
    label: "Sales",
    items: [
      {
        to: "/returns",
        label: "Returns",
        icon: RotateCcw,
        permission: Permission.PortalReportsRead,
        profiles: RETAIL_PROFILES,
        isActive: under("/returns"),
      },
      { to: "/payments", label: "Card & pay later", icon: CreditCard, permission: Permission.PortalReportsRead, isActive: under("/payments") },
      {
        to: "/promotions",
        label: "Promotions",
        icon: Tag,
        permission: Permission.PromotionsManage,
        capability: Capability.Promotions,
        isActive: under("/promotions"),
      },
      {
        to: "/store-credit",
        label: "Store credit",
        icon: TicketPercent,
        permission: Permission.PortalReportsRead,
        isActive: under("/store-credit"),
      },
      {
        to: "/gift-cards",
        label: "Gift cards",
        icon: Gift,
        permission: Permission.GiftCardsManage,
        capability: Capability.GiftCards,
        isActive: under("/gift-cards"),
      },
      { to: "/margin", label: "Margin guard", icon: ShieldCheck, permission: Permission.PortalReportsRead, isActive: under("/margin") },
      { to: "/shifts", label: "Shifts & drawers", icon: Clock, permission: Permission.PortalReportsRead, isActive: under("/shifts") },
    ],
  },
  {
    label: "Wholesale & credit",
    items: [
      {
        to: "/sales/quotations",
        label: "Quotations & layaway",
        icon: ReceiptText,
        permission: Permission.PortalReportsRead,
        capability: Capability.QuotesLayaway,
        isActive: under("/sales"),
      },
      {
        to: "/sales-orders",
        label: "Sales orders",
        icon: Truck,
        permission: Permission.SalesOrders,
        capability: Capability.SalesOrders,
        isActive: under("/sales-orders"),
      },
      {
        to: "/reorders",
        label: "Reorder management",
        icon: Repeat2,
        permission: Permission.CustomersManage,
        capability: Capability.CustomerReorders,
        isActive: under("/reorders"),
      },
      {
        to: "/cheques",
        label: "Cheques & PDCs",
        icon: Banknote,
        permission: Permission.ChequesManage,
        capability: Capability.Cheques,
        isActive: under("/cheques"),
      },
      {
        to: "/consignment",
        label: "Consignment",
        icon: Handshake,
        permission: Permission.PayablesManage,
        capability: Capability.Consignment,
        isActive: under("/consignment"),
      },
    ],
  },
  {
    label: "Service",
    items: [
      {
        to: "/repairs",
        label: "Repairs & warranties",
        icon: Wrench,
        permission: Permission.PortalAccess,
        capability: Capability.Repairs,
        isActive: under("/repairs"),
      },
      {
        to: "/warranties",
        label: "Warranties",
        icon: BadgeCheck,
        permission: Permission.PortalAccess,
        capability: Capability.Warranty,
        isActive: under("/warranties"),
      },
      {
        to: "/trade-ins",
        label: "Trade-ins",
        icon: Repeat2,
        permission: Permission.PortalReportsRead,
        capability: Capability.TradeIn,
        isActive: under("/trade-ins"),
      },
    ],
  },
  {
    label: "Food & Beverage",
    items: [
      {
        to: "/inventory/floor-plan",
        label: "Floor plan & tables",
        icon: LayoutGrid,
        permission: Permission.PortalAccess,
        capability: Capability.Tables,
        isActive: under("/inventory/floor-plan"),
      },
      {
        to: "/inventory/kitchen",
        label: "Kitchen display",
        icon: ChefHat,
        permission: Permission.PortalAccess,
        capability: Capability.Kds,
        isActive: (pathname) => pathname === "/inventory/kitchen" || pathname.startsWith("/inventory/kitchen/"),
      },
      {
        to: "/inventory/kitchen-agent",
        label: "Kitchen agent",
        icon: ClipboardList,
        ai: true,
        permission: Permission.PortalAccess,
        capability: Capability.Recipes,
        isActive: under("/inventory/kitchen-agent"),
      },
      {
        to: "/inventory/recipes",
        label: "Recipes & ingredients",
        icon: UtensilsCrossed,
        permission: Permission.PortalAccess,
        capability: Capability.Recipes,
        isActive: under("/inventory/recipes", "/inventory/recipe-usage"),
      },
      {
        to: "/inventory/modifiers",
        label: "Menu modifiers",
        icon: SlidersHorizontal,
        permission: Permission.PortalAccess,
        capability: Capability.MenuModifiers,
        isActive: under("/inventory/modifiers"),
      },
      {
        to: "/settings#void-policy",
        label: "Void & comp",
        icon: Ban,
        permission: Permission.SettingsManage,
        settingsOnly: true,
        profiles: FNB_PROFILES,
        isActive: () => false,
      },
    ],
  },
  {
    label: "Finance",
    items: [
      { to: "/payables", label: "Payables", icon: HandCoins, permission: Permission.PayablesManage, isActive: under("/payables") },
      { to: "/expenses", label: "Expenses", icon: Wallet, permission: Permission.ExpensesManage, isActive: under("/expenses") },
      { to: "/accounting", label: "Accounting", icon: BookOpenCheck, permission: Permission.AccountingManage, isActive: under("/accounting") },
      { to: "/bank", label: "Bank reconciliation", icon: Landmark, permission: Permission.BankingManage, isActive: under("/bank") },
      { to: "/reports/vat", label: "VAT report", icon: Percent, permission: Permission.ReportsVat, isActive: under("/reports/vat") },
      { to: "/reports/exports", label: "Exports & loyalty", icon: FileSpreadsheet, permission: Permission.ReportsVat, isActive: under("/reports/exports") },
      {
        to: "/reports/management",
        label: "Management reports",
        icon: ChartColumn,
        permission: Permission.PortalReportsRead,
        isActive: under("/reports/management"),
      },
      {
        to: "/reports/tips",
        label: "Tips & service",
        icon: HandCoins,
        permission: Permission.PortalReportsRead,
        capability: Capability.TipsServiceCharge,
        isActive: under("/reports/tips"),
      },
    ],
  },
  {
    label: "Administration",
    items: [
      { to: "/users", label: "Users", icon: UserCog, permission: Permission.UsersRead, isActive: under("/users") },
      { to: "/staff", label: "Staff & payroll", icon: Timer, permission: Permission.StaffManage, isActive: under("/staff") },
      {
        to: "/settings#add-modules",
        label: "Add modules",
        icon: Blocks,
        permission: Permission.SettingsManage,
        settingsOnly: true,
        isActive: (pathname, hash) => pathname === "/settings" && hash === "#add-modules",
      },
      {
        to: "/settings",
        label: settingsLabel,
        icon: Settings,
        permission: Permission.PortalAccess,
        hub: true,
        isActive: (pathname, hash) => inSettingsHub(pathname) && hash !== "#add-modules",
      },
    ],
  },
];

export interface Crumb {
  label: string;
  to?: string;
}

const inventoryPages: Record<string, string> = {
  stock: "Stock",
  products: "Products",
  pricing: "Pricing",
  categories: "Categories",
  brands: "Brands",
  models: "Models",
  batches: "Purchase Batches",
  markdowns: "Markdowns",
  "size-curve": "Size & color matrix",
  "floor-plan": "Floor plan & tables",
  kitchen: "Kitchen display",
  "kitchen-agent": "Kitchen agent",
  recipes: "Recipes & ingredients",
  "recipe-usage": "Ingredient usage",
  expiring: "Expiring stock",
  modifiers: "Modifiers",
  meals: "Meals & combos",
  "purchase-orders": "Purchase Orders",
  replenishment: "Replenishment",
  counts: "Stock Counts",
  transfers: "Transfers",
  serials: "IMEI Tracker",
};

const singlePages: Record<string, Crumb[]> = {
  "/": [{ label: "Dashboard" }],
  "/dashboard": [{ label: "Dashboard" }],
  "/customers": [{ label: "Suppliers & CRM" }, { label: "Customers & B2B ledger" }],
  "/returns": [{ label: "Sales" }, { label: "Returns & fraud monitoring" }],
  "/payments": [{ label: "Sales" }, { label: "Card, QR & pay-later payments" }],
  "/promotions": [{ label: "Sales" }, { label: "Promotions & coupons" }],
  "/store-credit": [{ label: "Sales" }, { label: "Store credit" }],
  "/gift-cards": [{ label: "Sales" }, { label: "Gift cards" }],
  "/margin": [{ label: "Sales" }, { label: "Margin guard" }],
  "/shifts": [{ label: "Sales" }, { label: "Shifts & cash drawers" }],
  "/sales/quotations": [{ label: "Wholesale & credit" }, { label: "Wholesale quotations" }],
  "/sales-orders": [{ label: "Wholesale & credit" }, { label: "Sales orders & deliveries" }],
  "/cheques": [{ label: "Wholesale & credit" }, { label: "Cheques & PDCs" }],
  "/consignment": [{ label: "Wholesale & credit" }, { label: "Consignment stock" }],
  "/repairs": [{ label: "Service" }, { label: "Repairs" }],
  "/warranties": [{ label: "Service" }, { label: "Warranties" }],
  "/trade-ins": [{ label: "Service" }, { label: "Trade-ins" }],
  "/inventory/modifiers": [{ label: "Food & Beverage" }, { label: "Menu modifiers" }],
  "/payables": [{ label: "Finance" }, { label: "Accounts payable" }],
  "/expenses": [{ label: "Finance" }, { label: "Expenses & petty cash" }],
  "/accounting": [{ label: "Finance" }, { label: "Accounting" }],
  "/bank": [{ label: "Finance" }, { label: "Bank reconciliation" }],
  "/reports/vat": [{ label: "Finance" }, { label: "VAT report" }],
  "/reports/exports": [{ label: "Finance" }, { label: "Accounting exports & loyalty" }],
  "/reports/management": [{ label: "Finance" }, { label: "Management reports" }],
  "/reports/tips": [{ label: "Finance" }, { label: "Tips & service charge" }],
  "/insights": [{ label: "Workspace" }, { label: "AI insights" }],
  "/assistant": [{ label: "Workspace" }, { label: "AI assistant" }],
  "/account": [{ label: "Your account" }],
  "/users": [{ label: "Administration" }, { label: "Users" }],
  "/staff": [{ label: "Administration" }, { label: "Staff, timesheets & payroll" }],
};

export function crumbsFor(pathname: string, ctx: NavContext): Crumb[] {
  if (inSettingsHub(pathname)) {
    const hub = settingsLabel(ctx);
    const tab = settingsTabs
      .filter((item) => (item.end ? pathname === item.to : pathname === item.to || pathname.startsWith(`${item.to}/`)))
      .sort((left, right) => right.to.length - left.to.length)[0];
    if (tab === undefined || tab.to === "/settings") return [{ label: "Administration" }, { label: hub }];
    return [{ label: "Administration" }, { label: hub, to: "/settings" }, { label: tab.label }];
  }
  const exact = singlePages[pathname];
  if (exact) return exact;
  const section = /^\/inventory\/([^/]+)/.exec(pathname)?.[1];
  const page = section ? inventoryPages[section] : undefined;
  if (page) return [{ label: "Inventory", to: "/inventory" }, { label: page }];
  if (pathname.startsWith("/customers/")) {
    return [{ label: "Suppliers & CRM" }, { label: "Customers", to: "/customers" }, { label: "Statement" }];
  }
  return [{ label: "AxizPOS Business" }];
}
