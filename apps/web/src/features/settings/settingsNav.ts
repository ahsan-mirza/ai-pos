import type { LucideIcon } from "lucide-react";
import {
  Building2,
  CircleDollarSign,
  ClipboardList,
  Coins,
  Download,
  KeyRound,
  Landmark,
  LayoutGrid,
  Monitor,
  Palette,
  Printer,
  Puzzle,
  Scale,
  ScrollText,
  Settings,
  SlidersHorizontal,
  Store,
  Shield,
  Truck,
} from "lucide-react";

/** How much of the settings navigation is on screen. */
export type SettingsNavMode = "expanded" | "compact" | "collapsed";

export const SETTINGS_NAV_KEY = "ai-pos.settings-nav";

export const SETTINGS_NAV_WIDTH: Record<SettingsNavMode, number> = {
  expanded: 268,
  compact: 180,
  collapsed: 72,
};

export interface SettingsNavItem {
  id: string;
  label: string;
  short: string;
  icon: LucideIcon;
}

/** Sections on the General page. They stay in one list with the other settings pages. */
export const generalSections: SettingsNavItem[] = [
  { id: "currency", label: "Business currency", short: "Currency", icon: Coins },
  { id: "branch-tax", label: "Branch tax", short: "Branch tax", icon: Landmark },
  { id: "vat", label: "VAT and tax invoices", short: "VAT & tax", icon: ScrollText },
  { id: "receipts", label: "Receipt layout", short: "Receipts", icon: Printer },
  { id: "till-rules", label: "Till rules", short: "Till", icon: Scale },
  { id: "appearance", label: "Appearance", short: "Theme", icon: Palette },
  { id: "business-profile", label: "Business profile", short: "Profile", icon: Building2 },
  { id: "module-settings", label: "Module settings", short: "Modules", icon: SlidersHorizontal },
  { id: "module-setup", label: "Module setup", short: "Setup", icon: LayoutGrid },
];

const tabMeta: Record<string, { short: string; icon: LucideIcon }> = {
  "/settings": { short: "General", icon: Settings },
  "/settings/addons": { short: "Add-ons", icon: Puzzle },
  "/stores": { short: "Stores", icon: Store },
  "/roles": { short: "Roles", icon: Shield },
  "/settings/addon-access": { short: "Access", icon: KeyRound },
  "/registers": { short: "Registers", icon: Monitor },
  "/downloads": { short: "Downloads", icon: Download },
  "/settings/currencies": { short: "Currencies", icon: CircleDollarSign },
  "/settings/channels": { short: "Delivery", icon: Truck },
  "/settings/audit-logs": { short: "Audit", icon: ClipboardList },
};

export const sectionHints: Record<string, string> = {
  "/settings": "Currency, tax, receipts, and appearance",
  "/settings/addons": "Browse and purchase add-ons",
  "/stores": "Branches and warehouses",
  "/roles": "What each role is allowed to do",
  "/settings/addon-access": "Who can use each add-on",
  "/registers": "Devices that sell",
  "/downloads": "POS installer",
  "/settings/currencies": "Extra currencies and rates",
  "/settings/channels": "How delivery orders arrive",
  "/settings/audit-logs": "Who changed what",
};

export function tabAppearance(path: string): { short: string; icon: LucideIcon } {
  return tabMeta[path] ?? { short: "Settings", icon: Settings };
}

/** Drawer below a phone-width content area. Compact and collapsed follow the space that is left. */
export function automaticSettingsNav(width: number): SettingsNavMode | "drawer" {
  if (width < 680) return "drawer";
  if (width < 960) return "collapsed";
  if (width < 1200) return "compact";
  return "expanded";
}

const rank: Record<SettingsNavMode, number> = { collapsed: 0, compact: 1, expanded: 2 };

/** A saved choice stays until the content area is too narrow for it. */
export function resolveSettingsNav(preference: SettingsNavMode | null, width: number): SettingsNavMode | "drawer" {
  const automatic = automaticSettingsNav(width);
  if (automatic === "drawer" || preference === null) return automatic;
  return rank[preference] > rank[automatic] ? automatic : preference;
}

export function readSettingsNavPreference(): SettingsNavMode | null {
  try {
    const stored = localStorage.getItem(SETTINGS_NAV_KEY);
    if (stored === "expanded" || stored === "compact" || stored === "collapsed") return stored;
  } catch {
    /* Storage can be blocked. Automatic sizing still applies. */
  }
  return null;
}

export function storeSettingsNavPreference(mode: SettingsNavMode): void {
  try {
    localStorage.setItem(SETTINGS_NAV_KEY, mode);
  } catch {
    /* The choice still applies until the page is reloaded. */
  }
}

/** The next control the header button should offer for this width. */
export function settingsNavAction(
  mode: SettingsNavMode,
  width: number,
): { next: SettingsNavMode | "drawer"; label: string } {
  if (mode === "expanded") return { next: "compact", label: "Show compact labels" };
  if (mode === "compact") return { next: "collapsed", label: "Show icons only" };
  if (resolveSettingsNav("expanded", width) === "expanded") return { next: "expanded", label: "Expand navigation" };
  if (resolveSettingsNav("compact", width) === "compact") return { next: "compact", label: "Show compact labels" };
  return { next: "drawer", label: "Expand navigation" };
}
