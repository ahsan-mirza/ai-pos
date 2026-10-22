import {
  CAPABILITIES,
  CAPABILITY_GROUP_LABELS,
  type CapabilityGroup,
  type ConsoleCustomer,
  type ModuleState,
  type OverrideState,
  type TenantDetail,
} from "@ai-pos/shared-types";
import { ArrowRightLeft, RefreshCw, ShieldAlert, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";
import { ErrorNote, Field, GhostButton, Modal, PrimaryButton, Stat, StatusBadge } from "../components/ui";
import { api, errorText } from "../lib/api";
import { bytes, date, money, when } from "../lib/format";
import { useSession } from "../lib/session";
import { MigrationModal } from "./MigrationModal";

type Tab = "modules" | "requests" | "audit" | "customers";
type Choice = OverrideState | "default";

const GROUP_OF = new Map(CAPABILITIES.map((spec) => [spec.id as string, spec.group]));
const GROUPS = Object.keys(CAPABILITY_GROUP_LABELS) as CapabilityGroup[];

function ReasonModal({
  title,
  subtitle,
  confirm,
  onClose,
  onConfirm,
}: {
  title: string;
  subtitle: string;
  confirm: string;
  onClose: () => void;
  onConfirm: (reason: string) => Promise<void>;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <Modal
      title={title}
      subtitle={subtitle}
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton
            disabled={busy || reason.trim().length < 3}
            onClick={() => {
              setBusy(true);
              setError(null);
              onConfirm(reason.trim()).catch((caught: unknown) => {
                setError(errorText(caught, "That did not work."));
                setBusy(false);
              });
            }}
          >
            {busy ? "Working…" : confirm}
          </PrimaryButton>
        </>
      }
    >
      <Field label="Reason (kept in the audit log)" value={reason} maxLength={500} onChange={(event) => setReason(event.target.value)} placeholder="e.g. Ticket 1234: customer asked" />
      <ErrorNote message={error} />
    </Modal>
  );
}

function ModuleRow({ module, choice, onChoose }: { module: ModuleState; choice: Choice; onChoose: (choice: Choice) => void }) {
  return (
    <li className="flex flex-wrap items-center gap-3 px-4 py-3">
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-2 text-sm font-medium">
          {module.label}
          {module.fits_type ? null : <span className="rounded-full bg-surface px-2 py-0.5 text-[10px] font-semibold uppercase text-charcoal/50">outside type</span>}
          {module.selected ? <span className="rounded-full bg-surface px-2 py-0.5 text-[10px] font-semibold uppercase text-charcoal/50">store's choice</span> : null}
        </span>
        <span className={`text-xs ${module.enabled ? "text-emerald-700" : "text-charcoal/50"}`}>{module.enabled ? "On for the store" : "Off for the store"}</span>
      </span>
      <div className="inline-flex rounded-full bg-surface p-1" role="group" aria-label={`${module.label} override`}>
        {(["default", "on", "off"] as const).map((value) => (
          <button
            key={value}
            type="button"
            aria-pressed={choice === value}
            disabled={!module.available && value === "on"}
            onClick={() => onChoose(value)}
            className={`h-8 rounded-full px-3 text-xs font-semibold capitalize disabled:opacity-40 ${
              choice === value ? (value === "default" ? "bg-white text-charcoal shadow-sm" : value === "on" ? "bg-accent text-white" : "bg-charcoal text-white") : "text-charcoal/60"
            }`}
          >
            {value === "default" ? "Default" : `Force ${value}`}
          </button>
        ))}
      </div>
    </li>
  );
}

function ModulesTab({ detail, onSaved }: { detail: TenantDetail; onSaved: () => void }) {
  const initial = useMemo(
    () => Object.fromEntries(detail.modules.map((module) => [module.key, (module.override ?? "default") as Choice])),
    [detail.modules],
  );
  const [choices, setChoices] = useState<Record<string, Choice>>(initial);
  const [confirming, setConfirming] = useState(false);
  useEffect(() => setChoices(initial), [initial]);

  const changes = Object.entries(choices).filter(([key, value]) => value !== initial[key]);
  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="text-sm text-charcoal/60">
          Default follows the business type and the store's own choices. A forced module cannot be changed by the store.
        </p>
        <PrimaryButton disabled={changes.length === 0} onClick={() => setConfirming(true)}>
          Save {changes.length > 0 ? `${changes.length} change${changes.length === 1 ? "" : "s"}` : "overrides"}
        </PrimaryButton>
      </div>
      <div className="space-y-4">
        {GROUPS.map((group) => {
          const modules = detail.modules.filter((module) => GROUP_OF.get(module.key) === group);
          if (modules.length === 0) return null;
          return (
            <fieldset key={group}>
              <legend className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-charcoal/50">{CAPABILITY_GROUP_LABELS[group]}</legend>
              <ul className="divide-y divide-line rounded-2xl border border-line">
                {modules.map((module) => (
                  <ModuleRow key={module.key} module={module} choice={choices[module.key] ?? "default"} onChoose={(value) => setChoices({ ...choices, [module.key]: value })} />
                ))}
              </ul>
            </fieldset>
          );
        })}
      </div>
      {confirming ? (
        <ReasonModal
          title={`Apply ${changes.length} module change${changes.length === 1 ? "" : "s"}`}
          subtitle={`${detail.tenant.name} sees it at once; registers pick it up on their next sync.`}
          confirm="Apply"
          onClose={() => setConfirming(false)}
          onConfirm={async (reason) => {
            const overrides = Object.fromEntries(changes.map(([key, value]) => [key, value === "default" ? null : value]));
            await api.put(`/tenants/${detail.tenant.id}/modules`, { overrides, reason });
            setConfirming(false);
            onSaved();
          }}
        />
      ) : null}
    </div>
  );
}

function RequestsTab({ detail, onMigrate, onChanged }: { detail: TenantDetail; onMigrate: (requestId: string, target: string) => void; onChanged: () => void }) {
  const [closing, setClosing] = useState<{ id: string; action: "resolve" | "reject" } | null>(null);
  if (detail.change_requests.length === 0) return <p className="text-sm text-charcoal/60">No change requests from this store.</p>;
  return (
    <ul className="space-y-2">
      {detail.change_requests.map((request) => (
        <li key={request.id} className="rounded-2xl border border-line p-4 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge value={request.status} />
            <span className="font-semibold">
              {request.kind === "BUSINESS_TYPE" ? "Business type" : "Module"}: {request.current_value} → {request.requested_value}
            </span>
            <span className="ml-auto text-xs text-charcoal/50">{when(request.created_at)}</span>
          </div>
          <p className="mt-2 text-charcoal/80">{request.reason}</p>
          <p className="mt-1 text-xs text-charcoal/50">
            {request.requested_by_name} · {request.requested_by_email} · {Object.entries(request.snapshot).map(([key, value]) => `${value} ${key}`).join(", ")}
          </p>
          {request.resolution_notes ? <p className="mt-1 text-xs text-charcoal/60">Notes: {request.resolution_notes}</p> : null}
          {request.status === "PENDING" ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {request.kind === "BUSINESS_TYPE" ? (
                <PrimaryButton onClick={() => onMigrate(request.id, request.requested_value)}>
                  <ArrowRightLeft size={15} aria-hidden="true" /> Migrate
                </PrimaryButton>
              ) : null}
              <GhostButton onClick={() => setClosing({ id: request.id, action: "resolve" })}>Mark resolved</GhostButton>
              <GhostButton onClick={() => setClosing({ id: request.id, action: "reject" })}>Reject</GhostButton>
            </div>
          ) : null}
        </li>
      ))}
      {closing ? (
        <ReasonModal
          title={closing.action === "resolve" ? "Resolve request" : "Reject request"}
          subtitle="The store sees these notes on its Business profile page."
          confirm={closing.action === "resolve" ? "Resolve" : "Reject"}
          onClose={() => setClosing(null)}
          onConfirm={async (notes) => {
            await api.post(`/change-requests/${closing.id}/${closing.action}`, { notes });
            setClosing(null);
            onChanged();
          }}
        />
      ) : null}
    </ul>
  );
}

function AuditTab({ detail }: { detail: TenantDetail }) {
  if (detail.audit.length === 0) return <p className="text-sm text-charcoal/60">No console actions on this store yet.</p>;
  return (
    <ul className="divide-y divide-line rounded-2xl border border-line text-sm">
      {detail.audit.map((entry) => (
        <li key={entry.id} className="px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs font-semibold">{entry.action}</span>
            <span className="text-xs text-charcoal/50">{entry.operator_email ?? "system"}</span>
            <span className="ml-auto text-xs text-charcoal/50">{when(entry.created_at)}</span>
          </div>
          {entry.reason ? <p className="mt-1 text-charcoal/70">{entry.reason}</p> : null}
          {entry.after ? <p className="mt-1 truncate font-mono text-[11px] text-charcoal/50">{JSON.stringify(entry.after)}</p> : null}
        </li>
      ))}
    </ul>
  );
}

function CustomersTab({ detail }: { detail: TenantDetail }) {
  const { operator } = useSession();
  const [reason, setReason] = useState("");
  const [reveal, setReveal] = useState(false);
  const [rows, setRows] = useState<ConsoleCustomer[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const params = new URLSearchParams({ reason: reason.trim(), limit: "50" });
    if (reveal) params.set("reveal", "true");
    try {
      const result = await api.page<ConsoleCustomer>(`/tenants/${detail.tenant.id}/customers?${params.toString()}`);
      setRows(result.rows);
      setTotal(result.total);
      setError(null);
    } catch (caught) {
      setError(errorText(caught, "Could not load the customers."));
    }
  }

  return (
    <div>
      <div className="flex gap-3 rounded-2xl bg-accent/10 p-4 text-sm text-charcoal">
        <ShieldAlert size={18} className="mt-0.5 shrink-0 text-accent" aria-hidden="true" />
        <p>Customer records are personal data. Each look is logged with your reason; contacts stay masked unless a console admin reveals them.</p>
      </div>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <Field label="Reason" value={reason} maxLength={300} onChange={(event) => setReason(event.target.value)} placeholder="Ticket number and why" className="min-w-72 flex-1" />
        {operator?.role === "ADMIN" ? (
          <label className="flex h-11 items-center gap-2 text-sm">
            <input type="checkbox" checked={reveal} onChange={(event) => setReveal(event.target.checked)} className="h-4 w-4 accent-accent" />
            Reveal contacts
          </label>
        ) : null}
        <PrimaryButton disabled={reason.trim().length < 3} onClick={() => void load()}>
          Show customers
        </PrimaryButton>
      </div>
      <ErrorNote message={error} />
      {rows ? (
        <table className="mt-4 w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-charcoal/50">
              <th className="py-2">Name</th>
              <th className="py-2">Phone</th>
              <th className="py-2">Email</th>
              <th className="py-2">Type</th>
              <th className="py-2 text-right">Balance</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-b border-line/60">
                <td className="py-2 font-medium">{row.name}</td>
                <td className="py-2 font-mono text-xs">{row.phone ?? "—"}</td>
                <td className="py-2 font-mono text-xs">{row.email ?? "—"}</td>
                <td className="py-2 text-xs">{row.customer_type.toLowerCase()}</td>
                <td className="py-2 text-right tabular-nums">{money(row.balance_cents, detail.tenant.stats.currency)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={5} className="pt-2 text-xs text-charcoal/50">
                Showing {rows.length} of {total}.
              </td>
            </tr>
          </tfoot>
        </table>
      ) : null}
    </div>
  );
}

/** A tenant's profile, stats, module overrides, requests, audit and break-glass customers. */
export function TenantDrawer() {
  const { tenantId } = useParams();
  const navigate = useNavigate();
  const { reload } = useOutletContext<{ reload: () => Promise<void> }>();
  const [detail, setDetail] = useState<TenantDetail | null>(null);
  const [tab, setTab] = useState<Tab>("modules");
  const [error, setError] = useState<string | null>(null);
  const [statusChange, setStatusChange] = useState<"suspended" | "active" | null>(null);
  const [migrating, setMigrating] = useState<{ requestId: string | null; target: string | null } | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    if (!tenantId) return;
    try {
      setDetail(await api.get<TenantDetail>(`/tenants/${tenantId}/details`));
      setError(null);
    } catch (caught) {
      setError(errorText(caught, "Could not load the tenant."));
    }
  }, [tenantId]);

  useEffect(() => {
    setDetail(null);
    void load();
  }, [load]);

  const changed = () => {
    void load();
    void reload();
  };
  const close = () => navigate("/tenants");
  const tenant = detail?.tenant;

  return (
    <div className="frost fixed inset-0 z-40 flex justify-end bg-black/40 backdrop-blur-sm" role="presentation" onClick={close}>
      <aside
        aria-label="Tenant detail"
        className="drawer flex h-full w-full max-w-3xl flex-col overflow-y-auto rounded-l-3xl bg-white shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-start gap-4 border-b border-line bg-white/95 px-6 py-5 backdrop-blur">
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-2xl font-semibold">{tenant?.name ?? "Loading…"}</h2>
            {tenant ? (
              <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-charcoal/60">
                <span className="font-mono">{tenant.domain}</span>
                <StatusBadge value={tenant.status} />
                <span>{tenant.profile_label}</span>
                <span className="capitalize">· {tenant.plan}</span>
              </p>
            ) : null}
          </div>
          <button type="button" aria-label="Close" onClick={close} className="flex h-9 w-9 items-center justify-center rounded-full hover:bg-surface">
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <div className="px-6 py-5">
          <ErrorNote message={error} />
          {detail?.unreachable ? (
            <p className="mb-3 rounded-2xl bg-amber-50 px-4 py-2.5 text-sm text-amber-800">
              The store's database did not answer ({detail.unreachable}); modules show the last snapshot.
            </p>
          ) : null}
          {tenant && detail ? (
            <>
              <div className="flex flex-wrap gap-2">
                <PrimaryButton onClick={() => setMigrating({ requestId: null, target: null })}>
                  <ArrowRightLeft size={15} aria-hidden="true" /> Change business type
                </PrimaryButton>
                <GhostButton onClick={() => setStatusChange(tenant.status === "active" ? "suspended" : "active")}>
                  {tenant.status === "active" ? "Suspend store" : "Reactivate store"}
                </GhostButton>
                <GhostButton
                  disabled={refreshing}
                  onClick={() => {
                    setRefreshing(true);
                    api
                      .post(`/tenants/${tenant.id}/refresh-stats`, {})
                      .then(changed)
                      .catch((caught: unknown) => setError(errorText(caught, "Could not refresh the stats.")))
                      .finally(() => setRefreshing(false));
                  }}
                >
                  <RefreshCw size={14} aria-hidden="true" className={refreshing ? "animate-spin" : ""} /> Refresh stats
                </GhostButton>
              </div>
              <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Stat label="Stores" value={tenant.stats.stores} />
                <Stat label="Registers" value={tenant.stats.registers} />
                <Stat label="Customers" value={tenant.stats.customers} />
                <Stat label="Products" value={tenant.stats.products} />
                <Stat label="Sales (30 d)" value={money(tenant.stats.sales_30d_cents, tenant.stats.currency)} />
                <Stat label="Orders (30 d)" value={tenant.stats.sales_30d_count} />
                <Stat label="Database" value={bytes(tenant.stats.db_size_bytes)} />
                <Stat label="Last sale" value={date(tenant.stats.last_sale_at)} />
              </div>
              <p className="mt-2 text-xs text-charcoal/50">
                Owner {tenant.owner_email ?? "not set"} · {tenant.stats.onboarded ? "onboarded" : "still onboarding"} · stats from {when(tenant.stats.collected_at)}
              </p>

              <div className="mt-6 inline-flex rounded-full bg-surface p-1" role="tablist" aria-label="Tenant sections">
                {(["modules", "requests", "audit", "customers"] as const).map((value) => (
                  <button
                    key={value}
                    type="button"
                    role="tab"
                    aria-selected={tab === value}
                    onClick={() => setTab(value)}
                    className={`h-9 rounded-full px-4 text-sm font-semibold capitalize ${tab === value ? "bg-charcoal text-white" : "text-charcoal/60"}`}
                  >
                    {value}
                    {value === "requests" && tenant.pending_requests > 0 ? ` (${tenant.pending_requests})` : ""}
                  </button>
                ))}
              </div>
              <div className="mt-4">
                {tab === "modules" ? <ModulesTab detail={detail} onSaved={changed} /> : null}
                {tab === "requests" ? (
                  <RequestsTab detail={detail} onChanged={changed} onMigrate={(requestId, target) => setMigrating({ requestId, target })} />
                ) : null}
                {tab === "audit" ? <AuditTab detail={detail} /> : null}
                {tab === "customers" ? <CustomersTab detail={detail} /> : null}
              </div>
            </>
          ) : null}
        </div>
      </aside>
      {statusChange && tenant ? (
        <div onClick={(event) => event.stopPropagation()}>
          <ReasonModal
            title={statusChange === "suspended" ? `Suspend ${tenant.name}?` : `Reactivate ${tenant.name}?`}
            subtitle={statusChange === "suspended" ? "Its portal and registers stop working until it is reactivated." : "The store can sign in again at once."}
            confirm={statusChange === "suspended" ? "Suspend" : "Reactivate"}
            onClose={() => setStatusChange(null)}
            onConfirm={async (reason) => {
              await api.patch(`/tenants/${tenant.id}`, { status: statusChange, reason });
              setStatusChange(null);
              changed();
            }}
          />
        </div>
      ) : null}
      {migrating && tenant ? (
        <div onClick={(event) => event.stopPropagation()}>
          <MigrationModal
            tenant={tenant}
            requestId={migrating.requestId}
            initialTarget={migrating.target}
            onClose={() => setMigrating(null)}
            onDone={() => {
              setMigrating(null);
              changed();
            }}
          />
        </div>
      ) : null}
    </div>
  );
}
