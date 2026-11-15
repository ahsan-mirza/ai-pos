import { useEffect, useMemo, useState } from "react";
import { ErrorNote, Field, GhostButton, Modal, PrimaryButton } from "../components/ui";
import { api, errorText } from "../lib/api";

interface Category {
  id: string;
  group: string;
  label: string;
  kind: string;
  warning: string;
}

interface Branch {
  id: string;
  name: string;
  code: string;
}

interface CountRow {
  table: string;
  label: string;
  category: string;
  records: number;
}

interface Operation {
  id: string;
  scope: string;
  categories: string[];
  status: string;
  ready: boolean;
  snapshot_records: number;
  records_reset: number;
  records_restored: number;
  conflicts?: { table: string; id: string; resolution: string }[];
  failure: string | null;
  expires_at: string | null;
  created_at: string | null;
  completed_at: string | null;
  restored_at: string | null;
  created_by: string;
  snapshot_reference: string | null;
  preview: {
    ready?: boolean;
    tenant_name?: string;
    branches?: Branch[];
    categories?: string[];
    counts?: CountRow[];
    total_records?: number;
    dependencies?: { category: string; reason: string }[];
    required_categories?: string[];
    skipped_shared?: { label: string; reason: string }[];
    protected?: string[];
  };
}

interface RestorePreview extends Operation {
  records_to_restore: number;
  conflicts: { table: string; id: string; resolution: string }[];
  conflict_count: number;
}

const GROUPS = [
  "Products & Inventory",
  "Sales & Customers",
  "Purchasing & Suppliers",
  "Restaurant & Operations",
  "Finance",
  "Configuration & Staff",
  "Other operational data",
];

function when(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function DataResetSection({ tenantId, tenantName, onChanged }: { tenantId: string; tenantName: string; onChanged: () => void }) {
  const [history, setHistory] = useState<Operation[]>([]);
  const [open, setOpen] = useState<"reset" | "restore" | null>(null);

  const load = () => {
    api
      .get<Operation[]>(`/tenants/${tenantId}/data-reset`)
      .then(setHistory)
      .catch(() => setHistory([]));
  };

  useEffect(() => {
    load();
  }, [tenantId]);

  const restorable = history.filter((row) => row.snapshot_reference && row.status !== "PREVIEWED" && row.status !== "AUTHORIZED");

  return (
    <section className="mt-5 rounded-2xl border border-line p-4">
      <h3 className="text-sm font-semibold">Data Management</h3>
      <p className="mt-1 text-xs text-charcoal/60">
        Reset selected business data for this tenant. A recovery snapshot is created first, and your console password is required.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => setOpen("reset")}
          className="inline-flex h-10 items-center rounded-full border border-amber-300 bg-amber-50 px-4 text-sm font-semibold text-amber-950"
        >
          Reset Data
        </button>
        <GhostButton disabled={restorable.length === 0} onClick={() => setOpen("restore")}>
          Restore Data
        </GhostButton>
      </div>
      {history.length === 0 ? (
        <p className="mt-3 text-sm text-charcoal/60">No reset snapshots yet.</p>
      ) : (
        <ul className="mt-3 divide-y divide-line text-sm">
          {history.slice(0, 8).map((row) => (
            <li key={row.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span>
                <span className="font-medium">{row.scope === "tenant" ? "All branches" : "One branch"}</span>
                <span className="text-charcoal/50"> · {row.categories.join(", ")}</span>
              </span>
              <span className="text-xs text-charcoal/60">
                {row.status} · {row.snapshot_records} captured · {when(row.created_at)}
                {row.failure ? <span className="mt-1 block text-red-700">{row.failure}</span> : null}
              </span>
            </li>
          ))}
        </ul>
      )}
      {open === "reset" ? (
        <ResetDialog
          tenantId={tenantId}
          tenantName={tenantName}
          onClose={() => setOpen(null)}
          onDone={() => {
            setOpen(null);
            load();
            onChanged();
          }}
        />
      ) : null}
      {open === "restore" ? (
        <RestoreDialog
          tenantId={tenantId}
          rows={restorable}
          onClose={() => setOpen(null)}
          onDone={() => {
            setOpen(null);
            load();
            onChanged();
          }}
        />
      ) : null}
    </section>
  );
}

function ResetDialog({
  tenantId,
  tenantName,
  onClose,
  onDone,
}: {
  tenantId: string;
  tenantName: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const [step, setStep] = useState<"scope" | "categories" | "preview" | "password" | "done">("scope");
  const [branches, setBranches] = useState<Branch[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [protectedNotes, setProtectedNotes] = useState<string[]>([]);
  const [scope, setScope] = useState<"store" | "tenant">("store");
  const [storeId, setStoreId] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [picked, setPicked] = useState<string[]>([]);
  const [ack, setAck] = useState(false);
  const [operation, setOperation] = useState<Operation | null>(null);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [key] = useState(() => crypto.randomUUID());

  useEffect(() => {
    void api.get<{ categories: Category[]; protected: string[] }>(`/tenants/${tenantId}/data-reset/catalog`).then((body) => {
      setCategories(body.categories);
      setProtectedNotes(body.protected);
    });
    void api.get<{ branches: Branch[] }>(`/tenants/${tenantId}/data-reset/branches`).then((body) => {
      setBranches(body.branches);
      setStoreId(body.branches[0]?.id ?? "");
    });
  }, [tenantId]);

  const selectedBranch = branches.find((row) => row.id === storeId);
  const count = picked.length;

  const requestPreview = (acknowledge: boolean) => {
    setBusy(true);
    setError(null);
    api
      .post<Operation>(`/tenants/${tenantId}/data-reset/preview`, {
        scope,
        store_id: scope === "store" ? storeId : null,
        categories: picked,
        idempotency_key: key,
        acknowledge_dependencies: acknowledge,
      })
      .then((body) => {
        setOperation(body);
        setStep("preview");
      })
      .catch((caught: unknown) => setError(errorText(caught, "Could not preview the reset.")))
      .finally(() => setBusy(false));
  };

  const authorize = () => {
    if (!operation) return;
    setBusy(true);
    setError(null);
    const secret = password;
    setPassword("");
    api
      .post(`/tenants/${tenantId}/data-reset/${operation.id}/authorize`, { password: secret })
      .then(() => api.post<Operation>(`/tenants/${tenantId}/data-reset/${operation.id}/execute`, {}))
      .then((body) => {
        setOperation(body);
        setStep("done");
      })
      .catch((caught: unknown) => setError(errorText(caught, "The reset was not run.")))
      .finally(() => setBusy(false));
  };

  const footer =
    step === "done" ? (
      <PrimaryButton onClick={onDone}>Close</PrimaryButton>
    ) : (
      <>
        <GhostButton onClick={onClose}>Cancel</GhostButton>
        {step === "scope" ? (
          <PrimaryButton
            disabled={!confirmed || (scope === "store" && !storeId) || (scope === "tenant" && branches.length === 0)}
            onClick={() => setStep("categories")}
          >
            Continue
          </PrimaryButton>
        ) : null}
        {step === "categories" ? (
          <PrimaryButton disabled={picked.length === 0 || busy} onClick={() => requestPreview(false)}>
            {busy ? "Please wait…" : "Review impact"}
          </PrimaryButton>
        ) : null}
        {step === "preview" ? (
          <PrimaryButton
            disabled={busy || (operation?.ready !== true && !ack)}
            onClick={() => {
              if (operation?.ready) setStep("password");
              else requestPreview(true);
            }}
          >
            {operation?.ready ? "Continue to password" : "Include required categories"}
          </PrimaryButton>
        ) : null}
        {step === "password" ? (
          <PrimaryButton disabled={busy || password.length === 0} onClick={authorize}>
            {busy ? "Please wait…" : "Reset data"}
          </PrimaryButton>
        ) : null}
      </>
    );

  return (
    <Modal title="Reset Data" subtitle={tenantName} onClose={onClose} footer={footer} wide>
      {step === "scope" ? (
        <div className="grid gap-3 text-sm">
          <p className="font-medium">What would you like to reset?</p>
          <label className="flex items-start gap-2">
            <input type="radio" name="reset-scope" checked={scope === "store"} onChange={() => { setScope("store"); setConfirmed(false); }} />
            <span>Reset selected store only.</span>
          </label>
          <label className="flex items-start gap-2">
            <input type="radio" name="reset-scope" checked={scope === "tenant"} onChange={() => { setScope("tenant"); setConfirmed(false); }} />
            <span>Reset all branches of this tenant.</span>
          </label>
          {scope === "store" ? (
            <label className="grid gap-1">
              Branch
              <select className="h-10 rounded-xl border border-line px-3" value={storeId} onChange={(event) => { setStoreId(event.target.value); setConfirmed(false); }}>
                {branches.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.name} ({row.code})
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <div className="rounded-xl bg-surface px-3 py-2">
              <p>Tenant: {tenantName}</p>
              <p className="font-mono text-xs">{tenantId}</p>
              <p>{branches.length} branches: {branches.map((row) => row.name).join(", ") || "none"}</p>
            </div>
          )}
          <label className="flex items-start gap-2">
            <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
            <span>I confirm this {scope === "store" ? `branch${selectedBranch ? ` (${selectedBranch.name})` : ""}` : "all-branch"} scope.</span>
          </label>
        </div>
      ) : null}
      {step === "categories" ? (
        <div className="grid gap-3 text-sm">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p>{count} selected</p>
            <span className="flex gap-2">
              <button type="button" className="font-semibold text-accent" onClick={() => setPicked(categories.map((row) => row.id))}>
                Select All
              </button>
              <button type="button" className="font-semibold text-charcoal/70" onClick={() => setPicked([])}>
                Clear All
              </button>
            </span>
          </div>
          {GROUPS.map((group) => {
            const rows = categories.filter((row) => row.group === group);
            if (rows.length === 0) return null;
            return (
              <fieldset key={group}>
                <legend className="text-[11px] font-semibold uppercase tracking-[0.14em] text-charcoal/50">{group}</legend>
                {rows.map((row) => (
                  <label key={row.id} className="mt-2 flex items-start gap-2">
                    <input
                      type="checkbox"
                      checked={picked.includes(row.id)}
                      onChange={(event) =>
                        setPicked(event.target.checked ? [...picked, row.id] : picked.filter((id) => id !== row.id))
                      }
                    />
                    <span>
                      <span className="font-medium">{row.label}</span>
                      <span className="ml-2 text-[10px] uppercase text-charcoal/45">{row.kind}</span>
                      {row.warning ? <span className="mt-1 block text-xs text-charcoal/60">{row.warning}</span> : null}
                    </span>
                  </label>
                ))}
              </fieldset>
            );
          })}
          <div className="rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-950">
            These stay protected: {protectedNotes.slice(0, 4).join(" ")}
          </div>
        </div>
      ) : null}
      {step === "preview" && operation ? (
        <div className="grid gap-3 text-sm">
          <p className="font-semibold">Reset Preview</p>
          <p>
            Tenant: {operation.preview.tenant_name} · Scope: {operation.scope === "tenant" ? "All branches" : "Selected store"} · Branches:{" "}
            {operation.preview.branches?.length ?? 0}
          </p>
          <p>Categories: {(operation.preview.categories ?? operation.categories).join(", ")}</p>
          <ul>
            {(operation.preview.counts ?? []).map((row) => (
              <li key={`${row.table}-${row.label}`}>
                {row.label}: {row.records.toLocaleString()}
              </li>
            ))}
          </ul>
          <p className="font-medium">Estimated records: {(operation.preview.total_records ?? 0).toLocaleString()}</p>
          {(operation.preview.skipped_shared ?? []).length > 0 ? (
            <p className="text-xs text-charcoal/60">
              Not included for this scope: {operation.preview.skipped_shared?.map((row) => row.label).join(", ")}.
            </p>
          ) : null}
          {(operation.preview.dependencies ?? []).length > 0 ? (
            <div className="rounded-xl bg-amber-50 px-3 py-2 text-amber-950">
              {(operation.preview.dependencies ?? []).map((row) => (
                <p key={row.category}>{row.reason}</p>
              ))}
              <label className="mt-2 flex items-start gap-2">
                <input type="checkbox" checked={ack} onChange={(event) => setAck(event.target.checked)} />
                <span>I understand these dependent categories will also be reset. They are not removed silently.</span>
              </label>
            </div>
          ) : null}
          <p>
            This operation will reset the selected data for the chosen store or tenant branches. A recovery snapshot will be created
            before execution. Continue only if you understand the selected scope and data categories.
          </p>
        </div>
      ) : null}
      {step === "password" ? (
        <div className="grid gap-3">
          <p className="text-sm font-semibold">Security verification</p>
          <p className="text-sm text-charcoal/70">Enter your Console administrator password to authorize this reset.</p>
          <Field label="Console password" type="password" autoComplete="off" value={password} onChange={(event) => setPassword(event.target.value)} required />
        </div>
      ) : null}
      {step === "done" && operation ? (
        <div className="grid gap-2 text-sm">
          <p className="font-semibold">Reset completed successfully.</p>
          <p>Tenant: {tenantName}</p>
          <p>Scope: {operation.scope === "tenant" ? "All branches" : "Selected store"}</p>
          <p>Categories: {operation.categories.join(", ")}</p>
          <p>Records affected: {operation.records_reset.toLocaleString()}</p>
          <p>Snapshot reference: {operation.snapshot_reference}</p>
          <p>Completed: {when(operation.completed_at)}</p>
          <p>Administrator: {operation.created_by}</p>
        </div>
      ) : null}
      <ErrorNote message={error} />
    </Modal>
  );
}

function RestoreDialog({
  tenantId,
  rows,
  onClose,
  onDone,
}: {
  tenantId: string;
  rows: Operation[];
  onClose: () => void;
  onDone: () => void;
}) {
  const [chosen, setChosen] = useState(rows[0]?.id ?? "");
  const [preview, setPreview] = useState<RestorePreview | null>(null);
  const [password, setPassword] = useState("");
  const [step, setStep] = useState<"list" | "preview" | "password" | "done">("list");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Operation | null>(null);
  const selected = useMemo(() => rows.find((row) => row.id === chosen) ?? null, [rows, chosen]);

  const loadPreview = () => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    api
      .post<RestorePreview>(`/tenants/${tenantId}/data-reset/${selected.id}/restore/preview`, {})
      .then((body) => {
        setPreview(body);
        setStep("preview");
      })
      .catch((caught: unknown) => setError(errorText(caught, "Could not preview the restore.")))
      .finally(() => setBusy(false));
  };

  const apply = () => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    const secret = password;
    setPassword("");
    api
      .post(`/tenants/${tenantId}/data-reset/${selected.id}/restore/authorize`, { password: secret })
      .then(() => api.post<Operation>(`/tenants/${tenantId}/data-reset/${selected.id}/restore`, {}))
      .then((body) => {
        setResult(body);
        setStep("done");
      })
      .catch((caught: unknown) => setError(errorText(caught, "The restore was not applied.")))
      .finally(() => setBusy(false));
  };

  return (
    <Modal
      title="Restore Data"
      subtitle="Recover a previous reset snapshot"
      onClose={onClose}
      wide
      footer={
        step === "done" ? (
          <PrimaryButton onClick={onDone}>Close</PrimaryButton>
        ) : (
          <>
            <GhostButton onClick={onClose}>Cancel</GhostButton>
            {step === "list" ? (
              <PrimaryButton disabled={!selected || busy} onClick={loadPreview}>
                Review restore
              </PrimaryButton>
            ) : null}
            {step === "preview" ? (
              <PrimaryButton onClick={() => setStep("password")}>Continue to password</PrimaryButton>
            ) : null}
            {step === "password" ? (
              <PrimaryButton disabled={busy || password.length === 0} onClick={apply}>
                {busy ? "Please wait…" : "Restore data"}
              </PrimaryButton>
            ) : null}
          </>
        )
      }
    >
      {rows.length === 0 ? <p className="text-sm text-charcoal/60">No recovery snapshots are available.</p> : null}
      {step === "list" ? (
        <ul className="grid gap-2 text-sm">
          {rows.map((row) => (
            <li key={row.id}>
              <label className="flex items-start gap-2 rounded-xl border border-line px-3 py-2">
                <input type="radio" name="snapshot" checked={chosen === row.id} onChange={() => setChosen(row.id)} />
                <span>
                  <span className="font-medium">{when(row.completed_at ?? row.created_at)}</span>
                  <span className="block text-xs text-charcoal/60">
                    {row.scope === "tenant" ? "All branches" : "Selected store"} · {row.categories.join(", ")} · {row.snapshot_records} records · {row.created_by} · {row.status}
                    {row.expires_at ? ` · expires ${when(row.expires_at)}` : ""}
                  </span>
                </span>
              </label>
            </li>
          ))}
        </ul>
      ) : null}
      {step === "preview" && preview ? (
        <div className="grid gap-2 text-sm">
          <p>Records to restore: {preview.records_to_restore.toLocaleString()}</p>
          <p>Categories: {preview.categories.join(", ")}</p>
          <p>Conflicts: {preview.conflict_count}. Existing records are left unchanged. Newer rows are not overwritten.</p>
          {preview.conflicts.slice(0, 8).map((row) => (
            <p key={`${row.table}-${row.id}`} className="text-xs text-charcoal/60">
              {row.table} {row.id.slice(0, 8)} · {row.resolution}
            </p>
          ))}
        </div>
      ) : null}
      {step === "password" ? (
        <div className="grid gap-3">
          <p className="text-sm">Enter your Console administrator password to authorize this restore.</p>
          <Field label="Console password" type="password" autoComplete="off" value={password} onChange={(event) => setPassword(event.target.value)} required />
        </div>
      ) : null}
      {step === "done" && result ? (
        <p className="text-sm">
          Restore finished. {result.records_restored.toLocaleString()} records restored. {(result.conflicts ?? []).length} conflicts were left unchanged.
        </p>
      ) : null}
      <ErrorNote message={error} />
    </Modal>
  );
}
