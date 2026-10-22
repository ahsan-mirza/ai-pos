import {
  Capability,
  PAYMENT_PROVIDER_LABELS,
  PAYMENT_STATUS_LABELS,
  Permission,
  formatMoney,
  type CardTerminalProvider,
  type PaymentChannel,
  type PaymentIntentStatus,
  type PaymentList,
  type PaymentProvider,
  type PaymentRefund,
  type PaymentTerminal,
} from "@ai-pos/shared-types";
import { CheckCircle2, CircleAlert, CreditCard, RotateCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, FilterSelect, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { Toast } from "../../components/ui/Toast";
import { apiGet, apiPatch, apiPost } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCapability } from "../../lib/capabilities";
import { useCurrency } from "../../lib/currency";
import { useStoreScope } from "../../lib/storeScope";
import { message } from "../customers/api";

type Tab = "payments" | "refunds" | "terminals";
type ChannelFilter = PaymentChannel | "all";
type StatusFilter = PaymentIntentStatus | "all";

const CHANNEL_LABELS: Record<PaymentChannel, string> = { QR: "QR", CARD: "Card terminal", BNPL: "Pay later" };

function when(value: string): string {
  return new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function StatusChip({ status }: { status: string }) {
  const tone =
    status === "PAID" || status === "SUCCEEDED"
      ? "bg-charcoal text-white"
      : status === "DECLINED" || status === "FAILED"
        ? "bg-accent text-white"
        : "bg-white text-charcoal ring-1 ring-charcoal/20";
  const label = PAYMENT_STATUS_LABELS[status as PaymentIntentStatus] ?? status.charAt(0) + status.slice(1).toLowerCase();
  return <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${tone}`}>{label}</span>;
}

function ProviderCard({ provider }: { provider: PaymentProvider }) {
  return (
    <article className="rounded-card border border-line bg-white p-5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-charcoal/60">{provider.channel === "CARD" ? "Card terminals" : "Pay later"}</p>
        {provider.configured && !provider.simulated ? (
          <CheckCircle2 size={16} className="text-charcoal" aria-label="Connected" />
        ) : (
          <CircleAlert size={16} className="text-accent" aria-label="Simulated" />
        )}
      </div>
      <p className="mt-3 text-lg font-semibold">{provider.label}</p>
      <p className="mt-1 text-xs text-charcoal/50">
        {provider.simulated
          ? provider.missing.length > 0
            ? `Simulated until ${provider.missing.join(", ")} ${provider.missing.length > 1 ? "are" : "is"} set on the server.`
            : "Simulator: staff approve or decline at the till."
          : "Live credentials configured."}
      </p>
    </article>
  );
}

function TerminalModal({
  terminal,
  stores,
  onClose,
  onSaved,
}: {
  terminal: PaymentTerminal | null;
  stores: { id: string; name: string }[];
  onClose: () => void;
  onSaved: (row: PaymentTerminal) => void;
}) {
  const [storeId, setStoreId] = useState(terminal?.store_id ?? stores[0]?.id ?? "");
  const [provider, setProvider] = useState<CardTerminalProvider>(terminal?.provider ?? "simulator");
  const [terminalRef, setTerminalRef] = useState(terminal?.terminal_ref ?? "");
  const [label, setLabel] = useState(terminal?.label ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const row = terminal
        ? await apiPatch<PaymentTerminal>(`/api/v1/payments/terminals/${terminal.id}`, { label })
        : await apiPost<PaymentTerminal>("/api/v1/payments/terminals", {
            store_id: storeId,
            provider,
            terminal_ref: terminalRef.trim(),
            label: label.trim(),
          });
      onSaved(row);
    } catch (caught) {
      setError(message(caught, "Could not save the terminal."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={terminal ? "Edit card terminal" : "Add card terminal"}
      subtitle="Card amounts at this store are sent to the terminal and confirmed automatically."
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy || label.trim() === "" || (!terminal && (terminalRef.trim() === "" || storeId === ""))} onClick={() => void save()}>
            Save terminal
          </PrimaryButton>
        </>
      }
    >
      <div className="grid gap-4">
        {terminal ? null : (
          <>
            <SelectField label="Store" value={storeId} options={stores.map((store) => ({ value: store.id, label: store.name }))} onChange={setStoreId} />
            <SelectField
              label="Provider"
              value={provider}
              options={[
                { value: "simulator", label: "Simulator (demo and training)" },
                { value: "ngenius", label: "N-Genius (Network International)" },
                { value: "geidea", label: "Geidea" },
              ]}
              onChange={setProvider}
            />
            <TextField label="Terminal ID" value={terminalRef} maxLength={64} onChange={(event) => setTerminalRef(event.target.value)}
              placeholder="e.g. 10045021" hint="The terminal's ID from the provider's merchant portal." />
          </>
        )}
        <TextField label="Name at the till" value={label} maxLength={80} onChange={(event) => setLabel(event.target.value)} placeholder="Counter 1" />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}

export function PaymentsPage() {
  const { currency } = useCurrency();
  const { user } = useAuth();
  const { storeId, stores } = useStoreScope();
  const cardsOn = useCapability(Capability.CardTerminals);
  const canTerminals = user?.permissions.includes(Permission.DevicesManage) ?? false;
  const canRefund = user?.permissions.includes(Permission.PosRefund) ?? false;
  const [tab, setTab] = useState<Tab>("payments");
  const [channel, setChannel] = useState<ChannelFilter>("all");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [list, setList] = useState<PaymentList | null>(null);
  const [refunds, setRefunds] = useState<PaymentRefund[]>([]);
  const [terminals, setTerminals] = useState<PaymentTerminal[]>([]);
  const [providers, setProviders] = useState<PaymentProvider[]>([]);
  const [editing, setEditing] = useState<PaymentTerminal | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  const money = (cents: number) => formatMoney(cents, currency);

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams({ limit: "100" });
      if (channel !== "all") params.set("channel", channel);
      if (status !== "all") params.set("status", status);
      if (storeId) params.set("store_id", storeId);
      const [payments, refundRows] = await Promise.all([
        apiGet<PaymentList>(`/api/v1/payments/list?${params.toString()}`),
        apiGet<PaymentRefund[]>("/api/v1/payments/refunds"),
      ]);
      setList(payments);
      setRefunds(refundRows);
      if (canTerminals) {
        const [terminalRows, providerRows] = await Promise.all([
          apiGet<PaymentTerminal[]>("/api/v1/payments/terminals"),
          apiGet<PaymentProvider[]>("/api/v1/payments/providers"),
        ]);
        setTerminals(terminalRows);
        setProviders(providerRows);
      }
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load payments."));
    }
  }, [canTerminals, channel, status, storeId]);

  useEffect(() => {
    void load();
  }, [load]);

  const retry = async (refund: PaymentRefund) => {
    try {
      const result = await apiPost<PaymentRefund>(`/api/v1/payments/refunds/${refund.id}/retry`, {});
      setToast(result.status === "SUCCEEDED" ? "Refund sent to the provider." : `Still failing: ${result.error ?? "provider refused"}`);
      await load();
    } catch (caught) {
      setError(message(caught, "Could not retry the refund."));
    }
  };

  const check = async (terminal: PaymentTerminal) => {
    try {
      const result = await apiPost<{ ok: boolean; message: string }>(`/api/v1/payments/terminals/${terminal.id}/check`, {});
      setToast(result.message);
      await load();
    } catch (caught) {
      setError(message(caught, "Could not reach the terminal."));
    }
  };

  const toggle = async (terminal: PaymentTerminal) => {
    try {
      await apiPatch(`/api/v1/payments/terminals/${terminal.id}`, { is_active: !terminal.is_active });
      await load();
    } catch (caught) {
      setError(message(caught, "Could not update the terminal."));
    }
  };

  const failed = refunds.filter((row) => row.status === "FAILED");
  const storeName = (id: string) => stores.find((store) => store.id === id)?.name ?? "—";

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-4">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">Collected through providers</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{list ? money(list.paid_cents) : "—"}</p>
          <p className="mt-2 text-xs text-white/50">{list?.total ?? 0} payments in this view</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Refunded to customers</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{list ? money(list.refunded_cents) : "—"}</p>
          <p className="mt-2 text-xs text-charcoal/50">Back to the card or pay-later plan</p>
        </article>
        <article className={`rounded-card p-6 ${failed.length > 0 ? "bg-accent text-white" : "border border-line bg-white"}`}>
          <p className={`text-sm ${failed.length > 0 ? "text-white/80" : "text-charcoal/60"}`}>Refunds needing attention</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{failed.length}</p>
          <p className={`mt-2 text-xs ${failed.length > 0 ? "text-white/80" : "text-charcoal/50"}`}>Retried automatically for a while</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Card terminals</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{terminals.filter((row) => row.is_active).length}</p>
          <p className="mt-2 text-xs text-charcoal/50">{cardsOn ? "Active across your stores" : "Integrated card terminals are switched off"}</p>
        </article>
      </div>

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Card, QR and pay-later payments</h2>
            <p className="text-sm text-charcoal/60">Every payment a provider collected at the till, and every refund sent back through it.</p>
          </div>
          <SegmentedControl
            label="View"
            value={tab}
            options={[
              { value: "payments", label: "Payments" },
              { value: "refunds", label: `Refunds${failed.length ? ` (${failed.length})` : ""}` },
              ...(canTerminals ? [{ value: "terminals" as const, label: "Terminals" }] : []),
            ]}
            onChange={setTab}
          />
        </div>
        <ErrorNote message={error} />

        {tab === "payments" ? (
          <>
            <div className="mb-4 flex flex-wrap gap-3">
              <FilterSelect
                label="Method"
                value={channel}
                options={[
                  { value: "all", label: "All methods" },
                  { value: "CARD", label: "Card terminal" },
                  { value: "BNPL", label: "Pay later" },
                  { value: "QR", label: "QR" },
                ]}
                onChange={setChannel}
              />
              <FilterSelect
                label="Status"
                value={status}
                options={[
                  { value: "all", label: "Any status" },
                  ...(Object.keys(PAYMENT_STATUS_LABELS) as PaymentIntentStatus[]).map((value) => ({ value, label: PAYMENT_STATUS_LABELS[value] })),
                ]}
                onChange={setStatus}
              />
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[900px] text-left text-sm">
                <thead className="text-xs uppercase tracking-wide text-charcoal/50">
                  <tr>
                    <th className="pb-3 font-medium">When</th>
                    <th className="pb-3 font-medium">Method</th>
                    <th className="pb-3 font-medium">Store</th>
                    <th className="pb-3 font-medium">Sale</th>
                    <th className="pb-3 font-medium">Details</th>
                    <th className="pb-3 text-right font-medium">Amount</th>
                    <th className="pb-3 text-right font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {(list?.items ?? []).map((row) => (
                    <tr key={row.id}>
                      <td className="py-3 tabular-nums text-charcoal/70">{when(row.created_at)}</td>
                      <td className="py-3">
                        <span className="font-medium">{CHANNEL_LABELS[row.channel]}</span>
                        <span className="block text-xs text-charcoal/50">
                          {PAYMENT_PROVIDER_LABELS[row.provider] ?? row.provider}
                          {row.simulated ? " (simulated)" : ""}
                        </span>
                      </td>
                      <td className="py-3">{row.store_name}</td>
                      <td className="py-3 font-mono text-xs">{row.sale_number ?? "—"}</td>
                      <td className="py-3 text-xs text-charcoal/60">
                        {row.card_last4 ? `${row.card_brand ?? "Card"} •••• ${row.card_last4}` : row.reference}
                        {row.auth_code ? ` · auth ${row.auth_code}` : ""}
                        {row.failure_reason ? <span className="block text-accent">{row.failure_reason}</span> : null}
                      </td>
                      <td className="py-3 text-right tabular-nums">
                        {money(row.amount_cents)}
                        {row.refunded_cents > 0 ? <span className="block text-xs text-charcoal/50">−{money(row.refunded_cents)} refunded</span> : null}
                      </td>
                      <td className="py-3 text-right"><StatusChip status={row.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {list && list.items.length === 0 ? <p className="py-8 text-center text-sm text-charcoal/50">No payments match.</p> : null}
            </div>
          </>
        ) : null}

        {tab === "refunds" ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[800px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-charcoal/50">
                <tr>
                  <th className="pb-3 font-medium">When</th>
                  <th className="pb-3 font-medium">Provider</th>
                  <th className="pb-3 font-medium">Result</th>
                  <th className="pb-3 text-right font-medium">Amount</th>
                  <th className="pb-3 text-right font-medium">Status</th>
                  <th className="pb-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {refunds.map((row) => (
                  <tr key={row.id}>
                    <td className="py-3 tabular-nums text-charcoal/70">{when(row.created_at)}</td>
                    <td className="py-3">
                      {PAYMENT_PROVIDER_LABELS[row.provider] ?? row.provider}
                      <span className="block text-xs text-charcoal/50">{CHANNEL_LABELS[row.channel]}</span>
                    </td>
                    <td className="py-3 text-xs text-charcoal/60">
                      {row.error ?? row.provider_ref ?? "Queued"} · {row.attempts} attempt{row.attempts === 1 ? "" : "s"}
                    </td>
                    <td className="py-3 text-right tabular-nums">{money(row.amount_cents)}</td>
                    <td className="py-3 text-right"><StatusChip status={row.status} /></td>
                    <td className="py-3 text-right">
                      {row.status !== "SUCCEEDED" && canRefund ? (
                        <button type="button" onClick={() => void retry(row)} className="inline-flex items-center gap-1 text-xs font-semibold text-accent">
                          <RotateCw size={13} aria-hidden="true" /> Retry now
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {refunds.length === 0 ? <p className="py-8 text-center text-sm text-charcoal/50">No provider refunds yet.</p> : null}
          </div>
        ) : null}

        {tab === "terminals" && canTerminals ? (
          <div className="space-y-4">
            <div className="grid gap-4 md:grid-cols-3">
              {providers.map((provider) => (
                <ProviderCard key={`${provider.channel}-${provider.name}`} provider={provider} />
              ))}
            </div>
            <div className="flex items-center justify-between">
              <p className="text-sm text-charcoal/60">
                While a store has an active terminal, card sales there go through it; a manager can approve a manual entry when it is down.
              </p>
              <PrimaryButton disabled={!cardsOn || stores.length === 0} onClick={() => setEditing("new")}>
                <CreditCard size={15} className="mr-2" aria-hidden="true" /> Add terminal
              </PrimaryButton>
            </div>
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-charcoal/50">
                <tr>
                  <th className="pb-3 font-medium">Terminal</th>
                  <th className="pb-3 font-medium">Store</th>
                  <th className="pb-3 font-medium">Provider</th>
                  <th className="pb-3 font-medium">Last check</th>
                  <th className="pb-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {terminals.map((row) => (
                  <tr key={row.id} className={row.is_active ? "" : "opacity-50"}>
                    <td className="py-3">
                      <span className="font-medium">{row.label}</span>
                      <span className="block font-mono text-xs text-charcoal/50">{row.terminal_ref}</span>
                    </td>
                    <td className="py-3">{storeName(row.store_id)}</td>
                    <td className="py-3">{PAYMENT_PROVIDER_LABELS[row.provider] ?? row.provider}</td>
                    <td className="py-3 text-xs text-charcoal/60">
                      {row.last_checked_at ? `${row.last_check_ok ? "OK" : "Failed"} · ${when(row.last_checked_at)}` : "Never"}
                    </td>
                    <td className="space-x-3 py-3 text-right text-xs font-semibold">
                      <button type="button" onClick={() => void check(row)} className="text-accent">Test</button>
                      <button type="button" onClick={() => setEditing(row)} className="text-charcoal">Rename</button>
                      <button type="button" onClick={() => void toggle(row)} className="text-charcoal/60">{row.is_active ? "Deactivate" : "Activate"}</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {terminals.length === 0 ? <p className="py-6 text-center text-sm text-charcoal/50">No card terminals yet. Card sales are entered by hand.</p> : null}
          </div>
        ) : null}
      </div>

      {editing ? (
        <TerminalModal
          terminal={editing === "new" ? null : editing}
          stores={stores}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            setToast("Terminal saved.");
            void load();
          }}
        />
      ) : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}
