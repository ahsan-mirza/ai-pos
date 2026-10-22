import { AUDIT_ACTION_LABELS, type AuditActionType, type AuditClientDevice } from "@ai-pos/shared-types";
import { Cpu, Globe, Monitor, TerminalSquare, type LucideIcon } from "lucide-react";

const badgeStyles: Record<AuditActionType, string> = {
  CREATE: "bg-surface text-charcoal",
  UPDATE: "bg-surface text-charcoal",
  DELETE: "border border-charcoal bg-white text-charcoal",
  MANUAL_STOCK_ADJUSTMENT: "bg-accent text-white",
  PRICE_OVERRIDE: "bg-accent text-white",
  CREDIT_LIMIT_OVERRIDE: "bg-accent text-white",
  ROLE_CHANGE: "bg-accent text-white",
  REFUND_PROCESSED: "bg-accent/10 text-accent",
  MANAGER_OVERRIDE: "bg-accent text-white",
  LOGIN_PIN: "bg-charcoal text-white",
  LOGIN_PASSWORD: "bg-charcoal text-white",
  EXPORT_DATA: "bg-charcoal/10 text-charcoal",
  DRAWER_OPEN: "bg-accent/10 text-accent",
  CASH_DROP: "bg-charcoal/10 text-charcoal",
  ITEM_VOID: "bg-accent/10 text-accent",
  EXPIRED_STOCK_SOLD: "bg-accent/10 text-accent",
};

const dotStyles: Partial<Record<AuditActionType, string>> = {
  CREATE: "bg-accent",
  UPDATE: "bg-charcoal",
  DELETE: "bg-charcoal",
};

export function ActionBadge({ type, className = "" }: { type: AuditActionType; className?: string }) {
  const dot = dotStyles[type];
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-semibold ${badgeStyles[type]} ${className}`}
    >
      {dot ? <span className={`h-1.5 w-1.5 rounded-full ${dot}`} aria-hidden="true" /> : null}
      {AUDIT_ACTION_LABELS[type] ?? type}
    </span>
  );
}

const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]!.toUpperCase())
    .join("") || "?";

const avatarTones = ["bg-charcoal text-white", "bg-accent text-white", "bg-surface text-charcoal"];

export function Avatar({ name, size = "md" }: { name: string | null; size?: "sm" | "md" }) {
  const label = name ?? "System";
  const hash = [...label].reduce((sum, char) => sum + char.charCodeAt(0), 0);
  const tone = name === null ? "border border-dashed border-line bg-white text-charcoal/50" : avatarTones[hash % 3];
  const box = size === "sm" ? "h-7 w-7 text-[10px]" : "h-9 w-9 text-xs";
  return (
    <span
      className={`grid shrink-0 place-items-center rounded-full font-bold tracking-tight ${box} ${tone}`}
      aria-hidden="true"
    >
      {name === null ? "SY" : initials(label)}
    </span>
  );
}

const devices: Record<AuditClientDevice, { icon: LucideIcon; label: string }> = {
  web: { icon: Globe, label: "Web portal" },
  desktop: { icon: Monitor, label: "POS register" },
  api: { icon: TerminalSquare, label: "API client" },
  system: { icon: Cpu, label: "System" },
};

export function DeviceLabel({ device }: { device: AuditClientDevice }) {
  const { icon: Icon, label } = devices[device] ?? devices.system;
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-charcoal/60">
      <Icon size={13} aria-hidden="true" />
      {label}
    </span>
  );
}

export const formatStamp = (value: string) => {
  const date = new Date(value);
  return {
    day: date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }),
    time: date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
  };
};

export const shortId = (id: string | null) => (id ? id.slice(0, 8) : null);
