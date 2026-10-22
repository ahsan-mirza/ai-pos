import { Capability, profileSpec, type ProductUpsert } from "@ai-pos/shared-types";
import {
  Boxes,
  Clock,
  Lock,
  MonitorUp,
  PanelLeftClose,
  PanelLeftOpen,
  RefreshCw,
  RotateCcw,
  Settings,
  ShoppingCart,
  Timer,
  UtensilsCrossed,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { BranchCheckModal } from "../../features/checkout/BranchCheckModal";
import { terminal } from "../../config/terminal";
import { loadCatalog, store } from "../../features/checkout/catalog";
import { openDisplayWindow } from "../../features/display/displayChannel";
import { ShiftModal } from "../../features/shifts/ShiftModal";
import { SyncCenterModal } from "../../features/sync/SyncCenterModal";
import { ClockModal } from "../../features/timeclock/ClockModal";
import { useCapabilities } from "../../lib/capabilities";
import { inTauri, rejectedCount } from "../../lib/tauri";
import { useRegisterLayout } from "../RegisterLayout";
import type { RegisterView } from "./ShellContext";
import { useShell } from "./ShellContext";

type Tool = "inventory" | "clock" | "shift" | "sync" | "display" | "settings";

interface SidebarNavProps {
  busy: boolean;
  onNavigate: (view: RegisterView) => void;
  onLock: () => void;
}

const allPages: { id: RegisterView; label: string; icon: LucideIcon; capability?: Capability }[] = [
  { id: "checkout", label: "Checkout", icon: ShoppingCart },
  { id: "orders", label: "Orders & Tables", icon: UtensilsCrossed, capability: Capability.OpenOrders },
  { id: "repairs", label: "Repairs", icon: Wrench, capability: Capability.Repairs },
  { id: "returns", label: "Returns & Exchanges", icon: RotateCcw },
];

const allTools: { id: Tool; label: string; hint: string; icon: LucideIcon; desktopOnly: boolean; capability?: Capability }[] = [
  { id: "inventory", label: "Inventory", hint: "Stock at every branch and the warehouse", icon: Boxes, desktopOnly: false },
  { id: "clock", label: "Time clock", hint: "Clock in and out with your PIN", icon: Timer, desktopOnly: true },
  { id: "shift", label: "Shift", hint: "X report, pay in / out, close", icon: Clock, desktopOnly: true },
  { id: "sync", label: "Sync Center", hint: "Queued and rejected register events", icon: RefreshCw, desktopOnly: true },
  { id: "display", label: "Customer display", hint: "Open the second screen facing the customer", icon: MonitorUp, desktopOnly: false },
  { id: "settings", label: "Settings", hint: "Accent color, receipt printer and cash drawer", icon: Settings, desktopOnly: false },
];

function initialsOf(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

/** Hover / focus label shown beside an icon while the sidebar is collapsed. */
function Tip({ show, children }: { show: boolean; children: ReactNode }) {
  if (!show) return null;
  return (
    <span
      role="tooltip"
      className="pointer-events-none absolute left-full top-1/2 z-50 ml-3 -translate-y-1/2 whitespace-nowrap rounded-lg bg-zinc-900 px-2.5 py-1.5 text-xs font-medium text-white opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100 dark:bg-zinc-100 dark:text-zinc-900"
    >
      {children}
    </span>
  );
}

const itemBase =
  "group relative flex h-11 w-full items-center gap-3 rounded-xl px-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50 disabled:cursor-not-allowed disabled:opacity-40";
const itemIdle =
  "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-white/5 dark:hover:text-zinc-100";
const itemActive = "bg-primary-500 text-white shadow-md shadow-primary-500/25";

/** The register's one navigation sidebar: pages, register tools, cashier and lock. Shared by every page. */
export function SidebarNav({ busy, onNavigate, onLock }: SidebarNavProps) {
  const { session, view } = useShell();
  const activation = terminal();
  const { railCollapsed: collapsed, toggleRail } = useRegisterLayout();
  const [tool, setTool] = useState<Tool | null>(null);
  const [products, setProducts] = useState<ProductUpsert[] | null>(null);
  const [rejected, setRejected] = useState(0);
  const desktop = inTauri();
  const { enabled, profile, foodAndBeverage } = useCapabilities();
  const spec = profileSpec(profile);
  const pages = allPages.filter((page) => page.capability === undefined || enabled.has(page.capability));
  const tools = allTools
    .filter((item) => item.capability === undefined || enabled.has(item.capability))
    .map((item) => (item.id === "settings" ? { ...item, label: spec.settingsLabel } : item));
  const who = `${session.user.full_name} · ${session.user.role_name}${session.mode === "offline" ? " · offline unlock" : ""}`;

  useEffect(() => {
    if (!desktop) return;
    const poll = () => void rejectedCount().then(setRejected).catch(() => undefined);
    poll();
    const timer = window.setInterval(poll, 15_000);
    return () => window.clearInterval(timer);
  }, [desktop, tool]);

  useEffect(() => {
    if (tool !== "inventory" || products !== null) return;
    loadCatalog()
      .then((catalog) => setProducts(catalog.products))
      .catch(() => setProducts([]));
  }, [tool, products]);

  const toolAvailable = (item: (typeof allTools)[number]) =>
    (!item.desktopOnly || desktop) &&
    !(busy && item.id === "shift") &&
    !(busy && item.id === "settings" && view !== "settings");

  const navItem = (key: string, label: string, Icon: LucideIcon, props: { active?: boolean; disabled?: boolean; onClick: () => void; badge?: number; title?: string }) => (
    <button
      key={key}
      type="button"
      aria-label={collapsed ? label : undefined}
      aria-current={props.active ? "page" : undefined}
      title={!collapsed ? props.title : undefined}
      disabled={props.disabled}
      onClick={props.onClick}
      className={`${itemBase} ${collapsed ? "justify-center px-0" : ""} ${props.active ? itemActive : itemIdle}`}
    >
      <Icon size={20} strokeWidth={1.75} aria-hidden="true" className="shrink-0" />
      {collapsed ? null : <span className="truncate">{label}</span>}
      {props.badge ? (
        <span
          className={`flex h-5 min-w-5 items-center justify-center rounded-full bg-primary-500 px-1 text-[10px] font-bold tabular-nums text-white ${
            collapsed ? "absolute right-1 top-1" : "ml-auto"
          }`}
        >
          {props.badge}
        </span>
      ) : null}
      <Tip show={collapsed}>{props.title ?? label}</Tip>
    </button>
  );

  const pageButtons = pages.map(({ id, label, icon }) =>
    navItem(id, label, icon, { active: view === id, disabled: busy && view !== id, onClick: () => onNavigate(id) }),
  );
  const openTool = (id: Tool) => {
    if (id === "display") void openDisplayWindow();
    else if (id === "settings") onNavigate("settings");
    else setTool(id);
  };
  const toolButtons = tools.map((item) =>
    navItem(item.id, item.label, item.icon, {
      active: item.id === "settings" && view === "settings",
      disabled: !toolAvailable(item),
      onClick: () => openTool(item.id),
      badge: item.id === "sync" ? rejected : 0,
      title: item.desktopOnly && !desktop ? `${item.label}: available in the desktop app` : `${item.label}: ${item.hint}`,
    }),
  );

  return (
    <>
      <header className="flex shrink-0 items-center gap-1 overflow-x-auto border-b border-zinc-200 bg-white px-3 py-2 md:hidden dark:border-zinc-800 dark:bg-zinc-900">
        <span className="mr-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-500 text-sm font-bold text-white">
          ai
        </span>
        {pages.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            aria-label={label}
            aria-current={view === id ? "page" : undefined}
            disabled={busy && view !== id}
            onClick={() => onNavigate(id)}
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${view === id ? itemActive : itemIdle}`}
          >
            <Icon size={18} aria-hidden="true" />
          </button>
        ))}
        {tools.map((item) => (
          <button
            key={item.id}
            type="button"
            aria-label={item.label}
            aria-current={item.id === "settings" && view === "settings" ? "page" : undefined}
            disabled={!toolAvailable(item)}
            onClick={() => openTool(item.id)}
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl disabled:opacity-40 ${
              item.id === "settings" && view === "settings" ? itemActive : itemIdle
            }`}
          >
            <item.icon size={18} aria-hidden="true" />
          </button>
        ))}
        <button
          type="button"
          aria-label="Lock register"
          onClick={onLock}
          disabled={busy}
          className={`ml-auto flex h-10 w-10 shrink-0 items-center justify-center rounded-xl disabled:opacity-40 ${itemIdle}`}
        >
          <Lock size={18} aria-hidden="true" />
        </button>
      </header>

      <aside
        aria-label="Register navigation"
        className={`hidden h-full shrink-0 flex-col border-r border-zinc-200 bg-white text-zinc-900 transition-[width] duration-200 ease-out motion-reduce:transition-none md:flex dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-100 ${
          collapsed ? "w-20" : "w-64"
        }`}
      >
        <div className={`flex h-16 shrink-0 items-center gap-3 border-b border-zinc-200 dark:border-zinc-800 ${collapsed ? "justify-center px-2" : "px-4"}`}>
          {collapsed ? null : (
            <>
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary-500 text-sm font-bold text-white">
                ai
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-bold tracking-tight" title={activation?.tenant_domain}>
                  {activation?.tenant_name || "AI POS"}
                </span>
                <span
                  className="block truncate text-[11px] text-zinc-500 dark:text-zinc-400"
                  title={`${spec.label} · ${store.code} · ${store.name}${activation?.register_code ? ` · ${activation.register_code}` : ""}`}
                >
                  {spec.shortLabel} · {store.code} · {store.name}
                  {activation?.register_code ? ` · ${activation.register_code}` : ""}
                </span>
              </span>
            </>
          )}
          <button
            type="button"
            onClick={toggleRail}
            aria-expanded={!collapsed}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50 ${
              collapsed ? "bg-primary-500 text-white hover:bg-primary-600" : itemIdle
            }`}
          >
            {collapsed ? (
              <PanelLeftOpen size={18} strokeWidth={1.75} aria-hidden="true" />
            ) : (
              <PanelLeftClose size={18} strokeWidth={1.75} aria-hidden="true" />
            )}
          </button>
        </div>

        <nav aria-label="Register" className={`flex-1 px-3 py-4 ${collapsed ? "" : "custom-scrollbar overflow-y-auto"}`}>
          {collapsed ? null : <p className="mb-2 px-3 text-[11px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">{foodAndBeverage ? "Service" : "Sell"}</p>}
          <div className="flex flex-col gap-1">{pageButtons}</div>
          {collapsed ? (
            <div className="mx-auto my-4 h-px w-8 bg-zinc-200 dark:bg-zinc-800" />
          ) : (
            <p className="mb-2 mt-6 px-3 text-[11px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">Register</p>
          )}
          <div className="flex flex-col gap-1">{toolButtons}</div>
        </nav>

        <div className="shrink-0 space-y-1 border-t border-zinc-200 p-3 dark:border-zinc-800">
          <div
            tabIndex={collapsed ? 0 : undefined}
            role={collapsed ? "img" : undefined}
            aria-label={collapsed ? `Signed in: ${who}` : undefined}
            className={`group relative flex items-center gap-3 rounded-xl py-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50 ${
              collapsed ? "justify-center px-0" : "bg-zinc-50 px-2.5 ring-1 ring-zinc-200 dark:bg-zinc-800/40 dark:ring-zinc-800"
            }`}
            title={collapsed ? undefined : who}
          >
            <span className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary-500/15 text-xs font-bold text-primary-600 ring-1 ring-primary-500/20 dark:text-primary-400">
              {initialsOf(session.user.full_name)}
              {session.mode === "offline" ? (
                <span className="absolute -right-0.5 -top-0.5 h-3 w-3 rounded-full border-2 border-white bg-amber-500 dark:border-zinc-900" />
              ) : null}
            </span>
            {collapsed ? null : (
              <span className="min-w-0">
                <span className="block truncate text-sm font-semibold">{session.user.full_name}</span>
                <span className="block truncate text-xs text-zinc-500 dark:text-zinc-400">{session.user.role_name}</span>
              </span>
            )}
            <Tip show={collapsed}>
              <span className="block font-semibold">{session.user.full_name}</span>
              <span className="block text-[11px] opacity-70">
                {session.user.role_name}
                {session.mode === "offline" ? " · offline unlock" : ""}
              </span>
            </Tip>
          </div>
          {navItem("lock", "Lock Register", Lock, { disabled: busy, onClick: onLock, title: "Lock register / switch cashier" })}
        </div>
      </aside>

      {tool === "inventory" ? (
        products === null ? null : <BranchCheckModal product={null} products={products} onClose={() => setTool(null)} />
      ) : null}
      {tool === "shift" ? <ShiftModal session={session} onClose={() => setTool(null)} /> : null}
      {tool === "clock" ? <ClockModal session={session} onClose={() => setTool(null)} /> : null}
      {tool === "sync" ? <SyncCenterModal session={session} onClose={() => setTool(null)} /> : null}
    </>
  );
}
