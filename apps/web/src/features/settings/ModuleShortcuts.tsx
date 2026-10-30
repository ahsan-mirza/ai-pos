import { Capability, capabilitySpec } from "@ai-pos/shared-types";
import {
  BadgeCheck,
  CalendarClock,
  ChevronRight,
  Coins,
  Handshake,
  Layers,
  ScanLine,
  SlidersHorizontal,
  Tag,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router-dom";
import { useCapabilities } from "../../lib/capabilities";

interface Shortcut {
  capability: Capability;
  to: string;
  title: string;
  icon: LucideIcon;
}

/** Where each module is set up; only modules switched on for this business type are listed. */
const SHORTCUTS: Shortcut[] = [
  { capability: Capability.WholesalePricing, to: "/inventory/pricing", title: "Tier pricing", icon: Layers },
  { capability: Capability.SerialTracking, to: "/inventory/serials", title: "IMEI tracker", icon: ScanLine },
  { capability: Capability.MenuModifiers, to: "/inventory/modifiers", title: "Menu modifiers", icon: SlidersHorizontal },
  { capability: Capability.Fefo, to: "/inventory/expiring", title: "Expiring stock", icon: CalendarClock },
  { capability: Capability.MultiCurrency, to: "/settings/currencies", title: "Currencies", icon: Coins },
  { capability: Capability.Promotions, to: "/promotions", title: "Promotions", icon: Tag },
  { capability: Capability.Warranty, to: "/warranties", title: "Warranty plans", icon: BadgeCheck },
  { capability: Capability.Consignment, to: "/consignment", title: "Consignment", icon: Handshake },
];

export function ModuleShortcuts() {
  const { has } = useCapabilities();
  const shortcuts = SHORTCUTS.filter((shortcut) => has(shortcut.capability));
  if (shortcuts.length === 0) return null;
  return (
    <div className="rounded-card border border-line bg-white p-6">
      <div className="flex items-center gap-3">
        <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-charcoal text-white">
          <Zap size={20} aria-hidden="true" />
        </span>
        <div>
          <h2 className="text-2xl font-semibold">Module setup</h2>
          <p className="text-sm text-charcoal/60">Shortcuts to where each of your switched-on modules is configured.</p>
        </div>
      </div>
      <ul className="mt-5 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {shortcuts.map(({ capability, to, title, icon: Icon }) => (
          <li key={capability}>
            <Link
              to={to}
              className="group flex h-full items-center gap-3 rounded-2xl border border-line p-3 transition-colors hover:border-charcoal/20 hover:bg-surface"
            >
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-accent/10 text-accent">
                <Icon size={17} aria-hidden="true" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-semibold">{title}</span>
                <span className="block truncate text-xs text-charcoal/55">{capabilitySpec(capability).label}</span>
              </span>
              <ChevronRight size={16} aria-hidden="true" className="shrink-0 text-charcoal/30 group-hover:text-charcoal/60" />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
