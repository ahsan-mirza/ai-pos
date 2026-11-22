import {
  Activity,
  Bell,
  Building2,
  ChevronDown,
  ClipboardCheck,
  ClipboardList,
  Download,
  Factory,
  Keyboard,
  LayoutDashboard,
  Monitor,
  Package,
  Palette,
  PanelLeftClose,
  PanelLeftOpen,
  Plug,
  Printer,
  Puzzle,
  Receipt,
  RefreshCw,
  Settings,
  ShieldCheck,
  Shirt,
  ShoppingCart,
  Tags,
  Users,
  UsersRound,
  Wallet,
  Wifi,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { PosButton, PosSearchInput } from "../../components/shell/posControls";
import { scopeLabel, type SettingsRoute } from "./settingsRoutes";

const ICONS: Record<string, LucideIcon> = {
  overview: LayoutDashboard,
  "business-profile": Building2,
  currency: Wallet,
  tax: Receipt,
  sales: ShoppingCart,
  catalogue: Package,
  customers: Users,
  staff: UsersRound,
  modules: Puzzle,
  workflows: Workflow,
  "laundry-services": Shirt,
  "laundry-workflows": Workflow,
  "laundry-stations": Factory,
  "laundry-machines": Settings,
  "laundry-quality": ClipboardCheck,
  "laundry-tags": Tags,
  integrations: Plug,
  notifications: Bell,
  audit: ClipboardList,
  terminal: Monitor,
  hardware: Printer,
  connectivity: Wifi,
  security: ShieldCheck,
  appearance: Palette,
  keyboard: Keyboard,
  sync: RefreshCw,
  updates: Download,
  diagnostics: Activity,
};

export function SettingsNavigationIcon({ id }: { id: string }) {
  const Icon = ICONS[id] ?? LayoutDashboard;
  return <Icon aria-hidden="true" className="h-[1.125rem] w-[1.125rem] shrink-0" />;
}

export function SettingsSectionCard({ children }: { children: ReactNode }) {
  return <section className="rounded-2xl border border-zinc-200 bg-white p-6">{children}</section>;
}

export function SettingsReadOnlyNotice({ title, detail }: { title: string; detail: string }) {
  return (
    <SettingsSectionCard>
      <h2 className="text-xl font-semibold text-zinc-900">{title}</h2>
      <p className="mt-2 text-sm text-zinc-600">{detail}</p>
    </SettingsSectionCard>
  );
}

export function SettingsEmptyState({ title, detail }: { title: string; detail: string }) {
  return <p className="rounded-2xl border border-dashed border-zinc-200 bg-white px-4 py-6 text-sm text-zinc-500">{title}. {detail}</p>;
}

export function SettingsConfirmationDialog({
  title,
  subtitle,
  busy,
  error,
  confirmLabel,
  onCancel,
  onConfirm,
  children,
}: {
  title: string;
  subtitle: string;
  busy: boolean;
  error: string | null;
  confirmLabel: string;
  onCancel: () => void;
  onConfirm: () => void;
  children: ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center" role="presentation" onMouseDown={onCancel}>
      <div role="dialog" aria-modal="true" aria-label={title} className="w-full max-w-lg rounded-3xl bg-white p-6 shadow-2xl" onMouseDown={(event) => event.stopPropagation()}>
        <h2 className="text-lg font-semibold text-zinc-900">{title}</h2>
        <p className="mt-1 text-sm text-zinc-500">{subtitle}</p>
        <div className="mt-4 space-y-3 text-sm text-zinc-700">{children}</div>
        {error ? <p role="alert" className="mt-3 text-sm text-red-700">{error}</p> : null}
        <div className="mt-5 flex justify-end gap-2">
          <PosButton variant="secondary" size="sm" disabled={busy} onClick={onCancel}>Cancel</PosButton>
          <PosButton size="sm" disabled={busy} onClick={onConfirm}>{confirmLabel}</PosButton>
        </div>
      </div>
    </div>
  );
}

export function SettingsNavigationItem({ item, active, collapsed, onSelect }: { item: SettingsRoute; active: boolean; collapsed: boolean; onSelect: () => void }) {
  return (
    <button
      type="button"
      aria-current={active ? "page" : undefined}
      aria-label={item.label}
      title={item.label}
      onClick={onSelect}
      className={`box-border flex h-10 w-full min-w-0 items-center overflow-hidden rounded-xl text-left text-sm ${collapsed ? "justify-center px-0" : "gap-2.5 px-2.5"} ${active ? "bg-primary text-white" : "text-white/70 hover:bg-white/10 hover:text-white"}`}
    >
      <SettingsNavigationIcon id={item.id} />
      {collapsed ? null : <span className="min-w-0 flex-1 truncate">{item.short}</span>}
    </button>
  );
}

export function SettingsNavigationGroup({
  label,
  open,
  collapsed,
  onToggle,
  children,
}: {
  label: string;
  open: boolean;
  collapsed: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <div className="min-w-0">
      {collapsed ? (
        <div className="mx-auto my-1 h-px w-8 bg-white/15" role="separator" aria-label={label} />
      ) : (
        <button type="button" aria-expanded={open} onClick={onToggle} className="box-border flex h-9 w-full min-w-0 items-center gap-2 overflow-hidden rounded-lg px-2.5 text-left text-[0.6875rem] font-semibold uppercase tracking-wide text-white/45 hover:bg-white/10 hover:text-white/70">
          <span className="min-w-0 flex-1 truncate">{label}</span>
          <ChevronDown aria-hidden="true" className={`h-3.5 w-3.5 shrink-0 transition-transform ${open ? "" : "-rotate-90"}`} />
        </button>
      )}
      {collapsed || open ? <div className="min-w-0 space-y-0.5">{children}</div> : null}
    </div>
  );
}

export function SettingsScopeBadge({ scope, managed }: { scope: SettingsRoute["scope"]; managed: boolean }) {
  return <span className="rounded-full bg-zinc-100 px-2.5 py-1 text-[0.6875rem] font-semibold text-zinc-600">{scopeLabel(scope, managed)}</span>;
}

export function SettingsSearch({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return <PosSearchInput tone="inverse" value={value} onChange={onChange} placeholder="Search settings" label="Search settings" />;
}

export function SettingsCategoryCard({ item, onOpen }: { item: SettingsRoute; onOpen: () => void }) {
  const Icon = ICONS[item.id] ?? LayoutDashboard;
  return (
    <button type="button" onClick={onOpen} className="flex h-full flex-col rounded-2xl border border-zinc-200 bg-white p-4 text-left hover:border-primary">
      <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary"><Icon aria-hidden="true" className="h-[1.125rem] w-[1.125rem]" /></span>
      <span className="mt-3 text-sm font-semibold text-zinc-900">{item.label}</span>
      <span className="mt-1 flex-1 text-xs text-zinc-500">{item.description}</span>
      <span className="mt-3"><SettingsScopeBadge scope={item.scope} managed={item.managed} /></span>
    </button>
  );
}

export function SettingsOverview({ business, system, onOpen }: { business: SettingsRoute[]; system: SettingsRoute[]; onOpen: (id: string) => void }) {
  return (
    <div className="space-y-6">
      <section>
        <h2 className="text-sm font-semibold text-zinc-900">Business settings</h2>
        <p className="mt-1 text-sm text-zinc-500">How this business operates. These values are shared unless a page says otherwise.</p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {business.map((item) => <SettingsCategoryCard key={item.id} item={item} onOpen={() => onOpen(item.id)} />)}
        </div>
      </section>
      <section>
        <h2 className="text-sm font-semibold text-zinc-900">System and register settings</h2>
        <p className="mt-1 text-sm text-zinc-500">How this POS terminal, its devices, and this screen behave.</p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {system.map((item) => <SettingsCategoryCard key={item.id} item={item} onOpen={() => onOpen(item.id)} />)}
        </div>
      </section>
    </div>
  );
}

export function SettingsSidebar({
  title,
  collapsed,
  onToggle,
  query,
  onQuery,
  business,
  system,
  results,
  active,
  businessOpen,
  systemOpen,
  onToggleBusiness,
  onToggleSystem,
  onSelect,
}: {
  title: string;
  collapsed: boolean;
  onToggle: () => void;
  query: string;
  onQuery: (value: string) => void;
  business: SettingsRoute[];
  system: SettingsRoute[];
  results: SettingsRoute[];
  active: string;
  businessOpen: boolean;
  systemOpen: boolean;
  onToggleBusiness: () => void;
  onToggleSystem: () => void;
  onSelect: (id: string) => void;
}) {
  const searching = query.trim() !== "";
  useEffect(() => {
    const current = document.querySelector("[aria-label='Settings sections'] [aria-current='page']");
    current?.scrollIntoView({ block: "nearest" });
  }, [active, collapsed]);
  return (
    <aside aria-label="Settings sections" className={`box-border flex h-full shrink-0 flex-col overflow-hidden bg-zinc-900 py-4 text-white ${collapsed ? "w-[4.5rem]" : "w-[14.5rem]"}`}>
      <div className={`flex items-start gap-2 ${collapsed ? "justify-center px-2" : "px-3"}`}>
        {collapsed ? null : (
          <div className="min-w-0 flex-1">
            <h2 className="text-sm font-semibold leading-5">{title}</h2>
            <p className="mt-0.5 text-xs leading-4 text-white/55">Each section opens on its own.</p>
          </div>
        )}
        <SettingsCollapseButton collapsed={collapsed} onClick={onToggle} />
      </div>
      {collapsed ? null : (
        <div className="px-3 pt-3">
          <SettingsSearch value={query} onChange={onQuery} />
        </div>
      )}
      <nav className="custom-scrollbar mt-4 min-h-0 min-w-0 flex-1 space-y-2 overflow-x-hidden overflow-y-auto px-2 pb-3">
        {searching ? (
          results.length === 0 ? (
            <p className="px-2 text-xs text-white/55">No matching settings.</p>
          ) : (
            results.map((item) => (
              <SettingsNavigationItem key={item.id} item={item} active={item.id === active} collapsed={collapsed} onSelect={() => onSelect(item.id)} />
            ))
          )
        ) : (
          <>
            <SettingsNavigationGroup label="Business settings" open={businessOpen} collapsed={collapsed} onToggle={onToggleBusiness}>
              {business.map((item) => (
                <SettingsNavigationItem key={item.id} item={item} active={item.id === active} collapsed={collapsed} onSelect={() => onSelect(item.id)} />
              ))}
            </SettingsNavigationGroup>
            <SettingsNavigationGroup label="System & register" open={systemOpen} collapsed={collapsed} onToggle={onToggleSystem}>
              {system.map((item) => (
                <SettingsNavigationItem key={item.id} item={item} active={item.id === active} collapsed={collapsed} onSelect={() => onSelect(item.id)} />
              ))}
            </SettingsNavigationGroup>
          </>
        )}
      </nav>
    </aside>
  );
}

export function SettingsCollapseButton({ collapsed, onClick }: { collapsed: boolean; onClick: () => void }) {
  return (
    <button type="button" aria-label={collapsed ? "Expand settings navigation" : "Collapse settings navigation"} onClick={onClick} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-white/70 hover:bg-white/10">
      {collapsed ? <PanelLeftOpen aria-hidden="true" className="h-4 w-4" /> : <PanelLeftClose aria-hidden="true" className="h-4 w-4" />}
    </button>
  );
}

export function SettingsPageHeader({
  title,
  subtitle,
  business,
  typeLabel,
  modules,
}: {
  title: string;
  subtitle: string;
  business: string;
  typeLabel: string;
  modules: number;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900">{title}</h1>
        <p className="mt-1 text-sm text-zinc-500">{subtitle}</p>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-semibold text-zinc-900">{business}</span>
        <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">{typeLabel}</span>
        <span className="text-zinc-500">{modules} modules</span>
      </div>
    </div>
  );
}

export function StoreInformationSummary({
  country,
  location,
  currency,
  storeCode,
  taxNumber,
}: {
  country: string;
  location: string;
  currency: string;
  storeCode: string;
  taxNumber: string;
}) {
  const fields = [
    ["Country", country],
    ["Location", location],
    ["Currency", currency],
    ["Store code", storeCode],
    ["Tax registration number", taxNumber],
  ];
  return (
    <dl className="grid gap-4 rounded-2xl border border-zinc-200 bg-white p-4 sm:grid-cols-2 xl:grid-cols-5">
      {fields.map(([label, value]) => (
        <div key={label}>
          <dt className="text-xs font-medium text-zinc-500">{label}</dt>
          <dd className="mt-1 text-sm font-semibold text-zinc-900">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function SettingsLayout({ sidebar, children }: { sidebar: ReactNode; children: ReactNode }) {
  return (
    <div className="flex min-h-0 flex-1 bg-slate-50">
      {sidebar}
      <div className="min-h-0 min-w-0 flex-1 overflow-y-auto p-4 md:p-6">{children}</div>
    </div>
  );
}
