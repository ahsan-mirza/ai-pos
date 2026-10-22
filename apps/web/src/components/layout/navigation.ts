import { Capability, Permission, profileSpec, type BusinessProfile } from "@ai-pos/shared-types";
import {
  ArrowLeftRight,
  BadgeCheck,
  Ban,
  Banknote,
  BookOpenCheck,
  ChartColumn,
  Boxes,
  ChefHat,
  Clock,
  Coins,
  CreditCard,
  Download,
  FileSpreadsheet,
  FileText,
  Gift,
  HandCoins,
  Handshake,
  Landmark,
  LayoutDashboard,
  LayoutGrid,
  MessageCircle,
  MonitorSmartphone,
  Percent,
  Radar,
  ReceiptText,
  Repeat2,
  RotateCcw,
  ScanBarcode,
  ScrollText,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Smartphone,
  Sparkles,
  Store,
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
import { ELECTRONICS_PROFILES, FASHION_PROFILES, FNB_PROFILES, RETAIL_PROFILES } from "../../lib/industry";

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
  isActive: (pathname: string) => boolean;
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
    "/inventory/recipes",
    "/inventory/recipe-usage",
  )(pathname);

/** Grouped by domain; a group whose items are all switched off for this business type disappears. */
export const navGroups: NavGroup[] = [
  {
    label: "Workspace",
    items: [
      { to: "/", label: "Dashboard", icon: LayoutDashboard, permission: Permission.PortalReportsRead, isActive: (path) => path === "/" },
      { to: "/assistant", label: "AI assistant", icon: Sparkles, permission: Permission.PortalReportsRead, isActive: under("/assistant") },
      { to: "/insights", label: "AI insights", icon: Radar, permission: Permission.PortalReportsRead, isActive: under("/insights") },
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
        profiles: ELECTRONICS_PROFILES,
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
        profiles: FASHION_PROFILES,
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
        to: "/cheques",
        label: "Cheques & PDCs",
        icon: Banknote,
        permission: Permission.ChequesManage,
        capability: Capability.Cheques,
        profiles: ELECTRONICS_PROFILES,
        isActive: under("/cheques"),
      },
      {
        to: "/consignment",
        label: "Consignment",
        icon: Handshake,
        permission: Permission.PayablesManage,
        capability: Capability.Consignment,
        profiles: RETAIL_PROFILES,
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
        profiles: ELECTRONICS_PROFILES,
        isActive: under("/repairs"),
      },
      {
        to: "/warranties",
        label: "Warranties",
        icon: BadgeCheck,
        permission: Permission.PortalAccess,
        capability: Capability.Warranty,
        profiles: ELECTRONICS_PROFILES,
        isActive: under("/warranties"),
      },
      {
        to: "/trade-ins",
        label: "Trade-ins",
        icon: Repeat2,
        permission: Permission.PortalReportsRead,
        capability: Capability.TradeIn,
        profiles: ELECTRONICS_PROFILES,
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
        profiles: FNB_PROFILES,
        isActive: under("/inventory/floor-plan"),
      },
      {
        to: "/inventory/kitchen",
        label: "Kitchen display",
        icon: ChefHat,
        permission: Permission.PortalAccess,
        capability: Capability.Kds,
        profiles: FNB_PROFILES,
        isActive: under("/inventory/kitchen"),
      },
      {
        to: "/inventory/recipes",
        label: "Recipes & ingredients",
        icon: UtensilsCrossed,
        permission: Permission.PortalAccess,
        capability: Capability.Recipes,
        profiles: FNB_PROFILES,
        isActive: under("/inventory/recipes", "/inventory/recipe-usage"),
      },
      {
        to: "/inventory/modifiers",
        label: "Menu modifiers",
        icon: SlidersHorizontal,
        permission: Permission.PortalAccess,
        capability: Capability.MenuModifiers,
        profiles: FNB_PROFILES,
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
        profiles: FNB_PROFILES,
        isActive: under("/reports/tips"),
      },
    ],
  },
  {
    label: "Administration",
    items: [
      { to: "/stores", label: "Stores", icon: Store, permission: Permission.PortalAccess, isActive: under("/stores") },
      { to: "/users", label: "Users", icon: UserCog, permission: Permission.UsersRead, isActive: under("/users") },
      { to: "/staff", label: "Staff & payroll", icon: Timer, permission: Permission.StaffManage, isActive: under("/staff") },
      { to: "/roles", label: "Roles", icon: ShieldCheck, permission: Permission.UsersRead, isActive: under("/roles") },
      {
        to: "/registers",
        label: "Registers",
        icon: MonitorSmartphone,
        permission: Permission.DevicesManage,
        isActive: under("/registers"),
      },
      {
        to: "/downloads",
        label: "Downloads",
        icon: Download,
        permission: Permission.PortalAccess,
        superAdminOnly: true,
        isActive: under("/downloads"),
      },
      {
        to: "/settings/currencies",
        label: "Currencies",
        icon: Coins,
        permission: Permission.CurrenciesManage,
        capability: Capability.MultiCurrency,
        isActive: under("/settings/currencies"),
      },
      {
        to: "/settings/messaging",
        label: "Messaging",
        icon: MessageCircle,
        permission: Permission.MessagingManage,
        isActive: under("/settings/messaging"),
      },
      {
        to: "/settings/channels",
        label: "Delivery channels",
        icon: Truck,
        permission: Permission.SettingsManage,
        capability: Capability.DeliveryChannels,
        profiles: FNB_PROFILES,
        isActive: under("/settings/channels"),
      },
      {
        to: "/settings/audit-logs",
        label: "Audit trail",
        icon: ScrollText,
        permission: Permission.AuditRead,
        isActive: under("/settings/audit-logs"),
      },
      {
        to: "/settings",
        label: settingsLabel,
        icon: Settings,
        permission: Permission.SettingsManage,
        settingsOnly: true,
        isActive: (path) => path === "/settings",
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
  batches: "Purchase Batches",
  markdowns: "Markdowns",
  "size-curve": "Size & color matrix",
  "floor-plan": "Floor plan & tables",
  kitchen: "Kitchen display",
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
  "/stores": [{ label: "Administration" }, { label: "Stores" }],
  "/users": [{ label: "Administration" }, { label: "Users" }],
  "/staff": [{ label: "Administration" }, { label: "Staff, timesheets & payroll" }],
  "/roles": [{ label: "Administration" }, { label: "Roles & permissions" }],
  "/registers": [{ label: "Administration" }, { label: "Registers & device keys" }],
  "/downloads": [{ label: "Administration" }, { label: "Downloads" }],
  "/settings/audit-logs": [{ label: "Administration" }, { label: "Audit trail" }],
  "/settings/messaging": [{ label: "Administration" }, { label: "Messaging & jobs" }],
  "/settings/currencies": [{ label: "Administration" }, { label: "Currencies & exchange rates" }],
  "/settings/channels": [{ label: "Administration" }, { label: "Delivery channels" }],
};

export function crumbsFor(pathname: string, ctx: NavContext): Crumb[] {
  if (pathname === "/settings") return [{ label: "Administration" }, { label: settingsLabel(ctx) }];
  const exact = singlePages[pathname];
  if (exact) return exact;
  const section = /^\/inventory\/([^/]+)/.exec(pathname)?.[1];
  const page = section ? inventoryPages[section] : undefined;
  if (page) return [{ label: "Inventory", to: "/inventory" }, { label: page }];
  if (pathname.startsWith("/customers/")) {
    return [{ label: "Suppliers & CRM" }, { label: "Customers", to: "/customers" }, { label: "Statement" }];
  }
  return [{ label: "AI POS" }];
}
