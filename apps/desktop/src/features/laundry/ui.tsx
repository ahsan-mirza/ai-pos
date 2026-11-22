import { AxizTabs } from "@ai-pos/ui";
import { ChevronDown } from "lucide-react";
import type { ReactNode, SelectHTMLAttributes } from "react";
import { PosButton, PosSearchInput } from "../../components/shell/posControls";
import type { FloorNotice } from "./diagnostics";
import type { FloorGarment, StageColumn } from "./floorModel";
import type { LaundryTab } from "./laundryNav";
import type { Station } from "./productionAccess";

export const fieldClass = "min-h-12 w-full rounded-xl border border-zinc-200 bg-white px-3 text-sm text-charcoal outline-none focus:border-primary";
const selectClass = "min-h-12 appearance-none rounded-xl border border-zinc-200 bg-white ps-3 pe-10 text-sm text-charcoal outline-none focus:border-primary";
const labelClass = "mb-1 block text-xs font-semibold uppercase tracking-wide text-charcoal/55";
const fieldLabelClass = "block text-xs font-semibold uppercase tracking-wide text-charcoal/55";

/** Label and control share one gap, so fields in a row line up. */
export function FieldLabel({ label, className = "", children, error, hint }: { label: string; className?: string; children: ReactNode; error?: string; hint?: ReactNode }) {
  return (
    <label className={`${fieldLabelClass} ${className}`}>
      {label}
      <span className="mt-1 block">{children}</span>
      {hint ? <span className="mt-1 block font-normal normal-case tracking-normal text-charcoal/50">{hint}</span> : null}
      {error ? <span className="mt-1 block font-normal normal-case tracking-normal text-red-700">{error}</span> : null}
    </label>
  );
}

/** Native select with the arrow inset from the end edge. */
export function SelectControl({ className = "", full = true, children, ...props }: SelectHTMLAttributes<HTMLSelectElement> & { full?: boolean }) {
  return (
    <span className={`relative block ${full ? "w-full" : "w-fit max-w-full"}`}>
      <select {...props} className={`${selectClass} ${full ? "w-full" : "w-auto"} ${className}`}>{children}</select>
      <ChevronDown aria-hidden="true" strokeWidth={2} className="pointer-events-none absolute end-4 top-1/2 size-4 -translate-y-1/2 text-charcoal/55" />
    </span>
  );
}

export function money(cents: number): string {
  const sign = cents < 0 ? "-" : "";
  return `${sign}${(Math.abs(cents) / 100).toFixed(2)}`;
}

export function LaundryPageHeader({
  title,
  branch,
  operator,
  role,
  session,
  api,
  sync,
  actions,
}: {
  title: string;
  branch: string;
  operator: string;
  role: string;
  session: string;
  api: string;
  sync: string;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-charcoal/50">Laundry</p>
        <h1 className="text-2xl font-semibold text-charcoal">{title}</h1>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        {actions}
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3">
        <div><dt className="text-charcoal/50">Branch</dt><dd className="font-medium">{branch}</dd></div>
        <div><dt className="text-charcoal/50">Operator</dt><dd className="font-medium">{operator}</dd></div>
        <div><dt className="text-charcoal/50">Role</dt><dd className="font-medium">{role}</dd></div>
        <div><dt className="text-charcoal/50">Session</dt><dd className="font-medium">{session}</dd></div>
        <div><dt className="text-charcoal/50">API</dt><dd className="font-medium">{api}</dd></div>
        <div><dt className="text-charcoal/50">Sync</dt><dd className="font-medium">{sync}</dd></div>
      </dl>
      </div>
    </header>
  );
}

/** Same underline row as Inventory. One line, horizontal scroll, no pill or grouped card. */
export function LaundryStationNavigation({
  stations,
  active,
  onSelect,
}: {
  stations: Station[];
  active: string;
  counts?: Record<string, number>;
  onSelect: (id: string) => void;
}) {
  return (
    <AxizTabs
      ariaLabel="Laundry sections"
      className="sticky top-0 z-10"
      listClassName="overscroll-x-contain"
      tabs={stations.map((station) => ({
        id: station.id,
        label: station.label,
      }))}
      activeTab={active}
      onChange={onSelect}
    />
  );
}

/** Primary laundry sections and the section's own row. Both use the shared underline tabs. */
export function LaundrySectionBars({
  primary,
  secondary,
  activePrimary,
  activeSecondary,
  onPrimary,
  onSecondary,
}: {
  primary: LaundryTab[];
  secondary: LaundryTab[];
  activePrimary: string;
  activeSecondary: string;
  onPrimary: (id: string) => void;
  onSecondary: (id: string) => void;
}) {
  return (
    <div className="sticky top-0 z-10 bg-surface">
      <AxizTabs
        ariaLabel="Laundry sections"
        listClassName="overscroll-x-contain"
        tabs={primary}
        activeTab={activePrimary}
        onChange={onPrimary}
      />
      {secondary.length > 0 ? (
        <AxizTabs
          ariaLabel="Laundry subsection"
          listClassName="overscroll-x-contain"
          tabs={secondary}
          activeTab={activeSecondary}
          onChange={onSecondary}
        />
      ) : null}
    </div>
  );
}

export function LaundryMetricCard({ label, value, active, onOpen }: { label: string; value: number; active?: boolean; onOpen: () => void }) {
  return (
    <button type="button" onClick={onOpen} className={`min-h-11 rounded-2xl bg-white p-4 text-left ring-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary ${active ? "ring-primary" : "ring-zinc-200"}`}>
      <p className="text-sm text-charcoal/60">{label}</p>
      <p className="text-3xl font-semibold text-charcoal">{value}</p>
    </button>
  );
}

export function LaundryStatusBadge({ value }: { value: string }) {
  const tone = /READY|PASS|AVAILABLE|accepted/i.test(value)
    ? "bg-emerald-50 text-emerald-800"
    : /HOLD|FAIL|MAINTENANCE|OUT_OF_SERVICE|failed|session/i.test(value)
      ? "bg-red-50 text-red-800"
      : /RUNNING|REWORK|pending/i.test(value)
        ? "bg-amber-50 text-amber-950"
        : "bg-sky-50 text-sky-900";
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${tone}`}>{value || "Unknown"}</span>;
}

export function LaundryGarmentCard({ garment, selected, onOpen }: { garment: FloorGarment; selected?: boolean; onOpen?: () => void }) {
  return (
    <article className={`rounded-2xl bg-white p-3 ring-1 ${selected ? "ring-primary" : "ring-zinc-200"}`}>
      <div className="flex items-start justify-between gap-2">
        <p className="font-semibold text-charcoal">{garment.tag_code || garment.order_code}</p>
        <LaundryStatusBadge value={garment.hold ? "HOLD" : garment.stage} />
      </div>
      <p className="mt-1 text-sm">{garment.order_code} · {garment.customer_name}</p>
      <p className="text-sm text-charcoal/70">{garment.description || garment.service_name}</p>
      <p className="text-sm text-charcoal/70">{[garment.colour, garment.fabric, garment.condition].filter(Boolean).join(" · ") || "No colour or fabric recorded"}</p>
      {onOpen ? <button type="button" className="mt-2 min-h-11 text-sm font-semibold text-charcoal underline" onClick={onOpen}>Open</button> : null}
    </article>
  );
}

export function LaundryOrderCard({ code, customer, status, due }: { code: string; customer: string; status: string; due: string }) {
  return (
    <article className="rounded-2xl bg-white p-4 ring-1 ring-zinc-200">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">{code}</h2>
        <LaundryStatusBadge value={status} />
      </div>
      <p className="text-sm text-charcoal/70">{customer}</p>
      <p className="text-sm">Balance {due}</p>
    </article>
  );
}

export function LaundryScanInput({ value, busy, onChange, onSubmit }: { value: string; busy: boolean; onChange: (value: string) => void; onSubmit: () => void }) {
  return (
    <form
      className="flex flex-col gap-2 sm:flex-row"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <label className="flex-1">
        <span className={labelClass}>Garment tag</span>
        <input className={`${fieldClass} text-lg`} value={value} autoFocus onChange={(event) => onChange(event.target.value)} placeholder="Scan or type a tag" />
      </label>
      <PosButton type="submit" className="mt-5" disabled={busy || value.trim() === ""}>
        {busy ? "Looking up" : "Find garment"}
      </PosButton>
    </form>
  );
}

export function LaundryCustomerSelector({ customers, value, query, onQuery, onChange, error, branch }: { customers: { id: string; name: string }[]; value: string; query: string; onQuery: (value: string) => void; onChange: (id: string) => void; error?: string; branch?: ReactNode }) {
  const shown = customers.filter((row) => row.name.toLowerCase().includes(query.trim().toLowerCase()));
  return (
    <>
      <FieldLabel label="Find customer">
        <PosSearchInput value={query} onChange={onQuery} placeholder="Name" label="Find customer" />
      </FieldLabel>
      {branch}
      <FieldLabel label="Customer" error={error}>
        <SelectControl required value={value} onChange={(event) => onChange(event.target.value)}>
          <option value="">Select a customer</option>
          {shown.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
        </SelectControl>
      </FieldLabel>
    </>
  );
}

export function LaundryServiceSelector({ services, value, onChange, error }: { services: { id: string; name: string; pricing_unit: string }[]; value: string; onChange: (id: string) => void; error?: string }) {
  return (
    <FieldLabel label="Service" error={error}>
      <SelectControl value={value} onChange={(event) => onChange(event.target.value)}>
        {services.map((row) => <option key={row.id} value={row.id}>{row.name} · {row.pricing_unit}</option>)}
      </SelectControl>
    </FieldLabel>
  );
}

export function LaundryWeightInput({ gross, tare, onGross, onTare, grossError, tareError }: { gross: string; tare: string; onGross: (value: string) => void; onTare: (value: string) => void; grossError?: string; tareError?: string }) {
  return (
    <div className="grid items-start gap-2 sm:grid-cols-2">
      <FieldLabel label="Gross grams" error={grossError}><input className={fieldClass} inputMode="numeric" value={gross} onChange={(event) => onGross(event.target.value)} /></FieldLabel>
      <FieldLabel label="Tare grams" error={tareError}><input className={fieldClass} inputMode="numeric" value={tare} onChange={(event) => onTare(event.target.value)} /></FieldLabel>
    </div>
  );
}

export function LaundryPhotoUploader({ photos, onAdd, onRemove }: { photos: { key: string; name: string; dataUrl: string }[]; onAdd: (files: FileList) => void; onRemove: (key: string) => void }) {
  return (
    <div>
      <label className={labelClass}>
        Order photos
        <input className="mt-1 block w-full text-sm" type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={(event) => { if (event.target.files) onAdd(event.target.files); event.target.value = ""; }} />
      </label>
      <ul aria-label="Photo preview" className="mt-2 flex flex-wrap gap-2">
        {photos.map((photo) => (
          <li key={photo.key} className="rounded-xl bg-zinc-50 p-2 ring-1 ring-zinc-200">
            <img src={photo.dataUrl} alt={photo.name} width={96} height={96} className="h-24 w-24 object-cover" />
            <button type="button" className="mt-1 min-h-11 text-sm underline" onClick={() => onRemove(photo.key)}>Remove photo</button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function LaundryOrderSummary({ garments, bags, weight, services }: { garments: number; bags: number; weight: number; services: { name: string; count: number }[] }) {
  return (
    <aside className="rounded-2xl bg-white p-4 ring-1 ring-zinc-200" aria-label="Order summary">
      <h2 className="text-lg font-semibold">Order summary</h2>
      <dl className="mt-3 space-y-1 text-sm">
        <div className="flex justify-between"><dt>Garments</dt><dd>{garments}</dd></div>
        <div className="flex justify-between"><dt>Bags</dt><dd>{bags}</dd></div>
        <div className="flex justify-between"><dt>Net weight</dt><dd>{weight} g</dd></div>
      </dl>
      <ul className="mt-3 space-y-1 text-sm text-charcoal/80">
        {services.map((row) => <li key={row.name}>{row.name} · {row.count}</li>)}
      </ul>
      <p className="mt-3 text-sm text-charcoal/60">Tax, express surcharge, and the total are calculated by the server when the order is created.</p>
    </aside>
  );
}

export function LaundryPaymentSummary({ total, tax, paid, due, status }: { total: number; tax: number; paid: number; due: number; status: string }) {
  return (
    <article aria-label="Price summary" className="rounded-2xl bg-zinc-900 p-4 text-white">
      <p className="text-xs uppercase tracking-wide text-white/60">Server totals</p>
      <p className="text-3xl font-semibold">{money(total)}</p>
      <dl className="mt-2 space-y-1 text-sm">
        <div className="flex justify-between"><dt>Tax</dt><dd>{money(tax)}</dd></div>
        <div className="flex justify-between"><dt>Deposit paid</dt><dd>{money(paid)}</dd></div>
        <div className="flex justify-between"><dt>Balance due</dt><dd>{money(due)}</dd></div>
      </dl>
      <p className="mt-2 text-sm">Payment status <LaundryStatusBadge value={status} /></p>
    </article>
  );
}

export function LaundryProductionBoard({ columns, onOpen }: { columns: StageColumn[]; onOpen: (id: string) => void }) {
  if (columns.length === 0) return <LaundryEmptyState title="No garments on this workflow" detail="Scan a tag or choose another workflow." />;
  return (
    <div className="flex gap-3 overflow-x-auto pb-2" aria-label="Production board">
      {columns.map((column) => (
        <section key={column.id} className="w-64 shrink-0 rounded-2xl bg-zinc-100 p-2">
          <h3 className="px-1 text-sm font-semibold">{column.title} · {column.cards.length}</h3>
          <div className="mt-2 space-y-2">
            {column.cards.map((card) => <LaundryGarmentCard key={card.id} garment={card} onOpen={() => onOpen(card.id)} />)}
          </div>
        </section>
      ))}
    </div>
  );
}

export function LaundryExceptionPanel({ title, detail, children }: { title: string; detail: string; children?: ReactNode }) {
  return (
    <section className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-amber-950">
      <h2 className="font-semibold">{title}</h2>
      <p className="text-sm">{detail}</p>
      {children}
    </section>
  );
}

export function LaundryTimeline({ events }: { events: { label: string; detail: string }[] }) {
  if (events.length === 0) return <p className="text-sm text-charcoal/60">No production events yet.</p>;
  return (
    <ol aria-label="Production history" className="space-y-2">
      {events.map((event, index) => (
        <li key={`${event.label}-${index}`} className="rounded-xl bg-white px-3 py-2 text-sm ring-1 ring-zinc-200">
          <p className="font-semibold">{event.label}</p>
          <p className="text-charcoal/70">{event.detail}</p>
        </li>
      ))}
    </ol>
  );
}

export function LaundryEmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-zinc-300 bg-white p-6 text-center">
      <p className="font-semibold text-charcoal">{title}</p>
      <p className="text-sm text-charcoal/60">{detail}</p>
    </div>
  );
}

export function LaundryErrorState({
  notice,
  onRetry,
  onUnlock,
}: {
  notice: FloorNotice;
  onRetry?: () => void;
  onUnlock?: () => void;
}) {
  const session = notice.kind === "unauthenticated" || notice.tone === "session";
  const tone = session
    ? "border-amber-200 bg-amber-50 text-zinc-900"
    : notice.tone === "offline"
      ? "border-zinc-200 bg-zinc-50 text-zinc-900"
      : "border-red-200 bg-red-50 text-zinc-900";
  return (
    <div role="alert" className={`rounded-2xl border p-4 text-sm selection:bg-amber-100 selection:text-zinc-900 ${tone}`}>
      <p className="font-semibold text-zinc-900">{notice.title}</p>
      <p className="mt-1 text-zinc-800">{notice.detail}</p>
      {notice.requestId || notice.serverMessage ? (
        <details className="mt-2 text-zinc-600">
          <summary className="min-h-11 cursor-pointer font-medium">Support reference</summary>
          {notice.requestId ? <p>Request {notice.requestId}</p> : null}
          {notice.serverMessage ? <p>{notice.serverMessage}</p> : null}
        </details>
      ) : null}
      {session && onUnlock ? (
        <PosButton className="mt-3" onClick={onUnlock}>Unlock register</PosButton>
      ) : null}
      {notice.canRetry && onRetry ? (
        <PosButton variant="secondary" className="mt-3" onClick={onRetry}>Retry</PosButton>
      ) : null}
    </div>
  );
}

export function LaundrySyncStatus({
  api,
  session,
  queue,
  sync,
  notice,
  onRetry,
  onSyncCenter,
}: {
  api: string;
  session: string;
  queue: number;
  sync: string;
  notice: FloorNotice | null;
  onRetry?: () => void;
  onSyncCenter?: () => void;
}) {
  return (
    <section aria-label="Laundry connection" className="rounded-2xl bg-white p-4 ring-1 ring-zinc-200">
      <div className="flex flex-wrap gap-2 text-sm">
        <LaundryStatusBadge value={api} />
        <LaundryStatusBadge value={session} />
        <LaundryStatusBadge value={queue > 0 ? `${queue} queued` : "Queue empty"} />
        <LaundryStatusBadge value={sync} />
      </div>
      <p className="mt-2 text-sm text-charcoal/70">API reachable, cashier signed in, and laundry sync are three separate states. The footer API light stays green when the server answers, even if this window has no access token.</p>
      {notice && notice.tone !== "ok" ? <div className="mt-3"><LaundryErrorState notice={notice} onRetry={onRetry} /></div> : null}
      {onSyncCenter ? <button type="button" className="mt-3 min-h-11 text-sm font-semibold underline" onClick={onSyncCenter}>View Sync Center</button> : null}
    </section>
  );
}

export function LaundryGarmentEditor({
  line,
  services,
  errors,
  onChange,
  onRemove,
}: {
  line: { key: string; service_id: string; quantity: string; garment_type: string; description: string; brand: string; colour: string; fabric: string; size: string; condition: string; stains: string; instructions: string; gross: string; tare: string };
  services: { id: string; name: string; pricing_unit: string }[];
  errors: Record<string, string>;
  onChange: (patch: Partial<{ service_id: string; quantity: string; garment_type: string; description: string; brand: string; colour: string; fabric: string; size: string; condition: string; stains: string; instructions: string; gross: string; tare: string }>) => void;
  onRemove?: () => void;
}) {
  const service = services.find((row) => row.id === line.service_id);
  const weighed = service?.pricing_unit === "KG";
  return (
    <article className="space-y-3 rounded-2xl bg-white p-4 ring-1 ring-zinc-200">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">{weighed ? "Weight bag" : "Garment"}</h3>
        {onRemove ? <button type="button" className="min-h-11 text-sm underline" onClick={onRemove}>Remove</button> : null}
      </div>
      <LaundryServiceSelector services={services} value={line.service_id} onChange={(service_id) => onChange({ service_id })} error={errors[`line-${line.key}-service`]} />
      {weighed ? (
        <LaundryWeightInput gross={line.gross} tare={line.tare} onGross={(gross) => onChange({ gross })} onTare={(tare) => onChange({ tare })} grossError={errors[`line-${line.key}-gross`]} tareError={errors[`line-${line.key}-tare`]} />
      ) : (
        <Field label="Quantity" value={line.quantity} onChange={(quantity) => onChange({ quantity })} error={errors[`line-${line.key}-quantity`]} />
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Garment type" value={line.garment_type} onChange={(garment_type) => onChange({ garment_type })} />
        <Field label="Description" value={line.description} onChange={(description) => onChange({ description })} />
        <Field label="Brand" value={line.brand} onChange={(brand) => onChange({ brand })} />
        <Field label="Colour" value={line.colour} onChange={(colour) => onChange({ colour })} />
        <Field label="Fabric" value={line.fabric} onChange={(fabric) => onChange({ fabric })} />
        <Field label="Size" value={line.size} onChange={(size) => onChange({ size })} />
        <Field label="Condition" value={line.condition} onChange={(condition) => onChange({ condition })} />
        <Field label="Stains or damage" value={line.stains} onChange={(stains) => onChange({ stains })} />
      </div>
      <Field label="Special care" value={line.instructions} onChange={(instructions) => onChange({ instructions })} />
      <p className="text-xs text-charcoal/50">A tag is issued after the server accepts the order.</p>
    </article>
  );
}

export function Field({ label, value, onChange, error }: { label: string; value: string; onChange: (value: string) => void; error?: string }) {
  return (
    <FieldLabel label={label} error={error}>
      <input className={fieldClass} value={value} onChange={(event) => onChange(event.target.value)} />
    </FieldLabel>
  );
}

export function PrimaryButton({ children, disabled, type = "button", onClick }: { children: ReactNode; disabled?: boolean; type?: "button" | "submit"; onClick?: () => void }) {
  return <PosButton type={type} disabled={disabled} onClick={onClick}>{children}</PosButton>;
}

export function SecondaryButton({ children, disabled, onClick, type = "button" }: { children: ReactNode; disabled?: boolean; onClick?: () => void; type?: "button" | "submit" }) {
  return <PosButton variant="secondary" type={type} disabled={disabled} onClick={onClick}>{children}</PosButton>;
}
