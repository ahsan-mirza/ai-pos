import {
  CHEQUE_STATUS_LABELS,
  formatMoney,
  type Cheque,
  type ChequeAction,
  type ChequeList,
  type ChequeStatus,
} from "@ai-pos/shared-types";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorNote, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { Toast } from "../../components/ui/Toast";
import { apiGet, apiPost } from "../../lib/api";
import { useCurrency } from "../../lib/currency";
import { message, toCents } from "../customers/api";

type Filter = ChequeStatus | "all";

const filters = [
  { value: "RECEIVED", label: "In hand" },
  { value: "DEPOSITED", label: "Deposited" },
  { value: "BOUNCED", label: "Bounced" },
  { value: "CLEARED", label: "Cleared" },
  { value: "all", label: "All" },
] as const;

const actionLabels: Record<ChequeAction, string> = {
  deposit: "Mark deposited",
  clear: "Mark cleared",
  bounce: "Record bounce",
  cancel: "Return to customer",
};

const today = () => new Date().toISOString().slice(0, 10);

function daysUntil(value: string): number {
  return Math.round((new Date(`${value}T00:00:00`).getTime() - new Date(`${today()}T00:00:00`).getTime()) / 86_400_000);
}

function StatusChip({ status }: { status: ChequeStatus }) {
  const tone =
    status === "BOUNCED"
      ? "bg-accent text-white"
      : status === "CLEARED"
        ? "bg-surface text-charcoal ring-1 ring-line"
        : status === "DEPOSITED"
          ? "bg-charcoal text-white"
          : "bg-white text-charcoal ring-1 ring-charcoal/20";
  return <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${tone}`}>{CHEQUE_STATUS_LABELS[status]}</span>;
}

export function ChequesPage() {
  const { currency } = useCurrency();
  const [filter, setFilter] = useState<Filter>("RECEIVED");
  const [data, setData] = useState<ChequeList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<{ cheque: Cheque; action: ChequeAction } | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);

  const load = useCallback(async () => {
    try {
      setData(await apiGet<ChequeList>(`/api/v1/cheques${filter === "all" ? "" : `?status=${filter}`}`));
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load cheques."));
    }
  }, [filter]);

  useEffect(() => {
    void load();
  }, [load]);

  const stats = data?.stats;
  const money = (cents: number) => formatMoney(cents, currency);

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-4">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">Cheques in hand</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{stats ? money(stats.in_hand_cents) : "—"}</p>
          <p className="mt-2 text-xs text-white/50">{stats?.in_hand_count ?? 0} not yet banked</p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">Due this week</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{stats ? money(stats.due_this_week_cents) : "—"}</p>
          <p className="mt-2 text-xs text-white/80">{stats?.due_this_week_count ?? 0} ready to deposit within 7 days</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Exposure</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{stats ? money(stats.exposure_cents) : "—"}</p>
          <p className="mt-2 text-xs text-charcoal/50">Credited to accounts, not yet cleared</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Bounced</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{stats ? money(stats.bounced_cents) : "—"}</p>
          <p className="mt-2 text-xs text-charcoal/50">{stats?.bounced_count ?? 0} reversed on the account</p>
        </article>
      </div>

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Cheques & PDCs</h2>
            <p className="text-sm text-charcoal/60">Post-dated cheques can be deposited from the date written on them.</p>
          </div>
          <SegmentedControl label="Status" value={filter} options={filters} onChange={setFilter} />
        </div>
        <ErrorNote message={error} />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-3 font-medium">Cheque</th>
                <th className="pb-3 font-medium">Customer</th>
                <th className="pb-3 font-medium">Dated</th>
                <th className="pb-3 text-right font-medium">Amount</th>
                <th className="pb-3 pl-6 font-medium">Status</th>
                <th className="pb-3 font-medium">From</th>
                <th className="pb-3 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {(data?.cheques ?? []).map((cheque) => {
                const days = daysUntil(cheque.cheque_date);
                const actions: ChequeAction[] =
                  cheque.status === "RECEIVED"
                    ? days <= 0
                      ? ["deposit", "bounce", "cancel"]
                      : ["cancel"]
                    : cheque.status === "DEPOSITED"
                      ? ["clear", "bounce"]
                      : [];
                return (
                  <tr key={cheque.id} className="border-t border-line align-top">
                    <td className="py-3">
                      <span className="block font-mono text-xs font-semibold">{cheque.cheque_number}</span>
                      <span className="block text-xs text-charcoal/50">{cheque.bank}</span>
                    </td>
                    <td className="py-3">
                      {cheque.customer_id ? (
                        <Link to={`/customers/${cheque.customer_id}`} className="font-medium hover:text-accent">
                          {cheque.customer_name}
                        </Link>
                      ) : (
                        <span className="text-charcoal/60">Walk-in</span>
                      )}
                    </td>
                    <td className={`py-3 tabular-nums ${cheque.status === "RECEIVED" && days <= 0 ? "font-semibold text-accent" : ""}`}>
                      {new Date(`${cheque.cheque_date}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}
                      {cheque.status === "RECEIVED" ? (
                        <span className="block text-xs font-normal text-charcoal/50">
                          {days > 0 ? `in ${days} day${days === 1 ? "" : "s"}` : days === 0 ? "today" : `${-days} days ago`}
                        </span>
                      ) : null}
                    </td>
                    <td className="py-3 text-right font-semibold tabular-nums">
                      {formatMoney(cheque.amount_cents, cheque.currency)}
                      {cheque.bounce_fee_cents ? (
                        <span className="block text-xs font-normal text-accent">+{formatMoney(cheque.bounce_fee_cents, cheque.currency)} fee</span>
                      ) : null}
                    </td>
                    <td className="py-3 pl-6">
                      <StatusChip status={cheque.status} />
                      {cheque.events.length > 1 ? (
                        <span className="mt-1 block text-[11px] text-charcoal/50">
                          {cheque.events[cheque.events.length - 1]?.user_name ?? ""}
                          {cheque.events[cheque.events.length - 1]?.note ? ` · ${cheque.events[cheque.events.length - 1]?.note}` : ""}
                        </span>
                      ) : null}
                    </td>
                    <td className="py-3 text-xs text-charcoal/60">
                      {cheque.source === "SALE" ? `Sale ${cheque.sale_reference ?? ""}` : "Account payment"}
                      <span className="block">{cheque.received_by_name ?? ""}</span>
                    </td>
                    <td className="py-3">
                      <div className="flex flex-wrap justify-end gap-1">
                        {actions.map((action) => (
                          <button
                            key={action}
                            type="button"
                            onClick={() => setPending({ cheque, action })}
                            className={`rounded-full px-3 py-1.5 text-xs font-semibold ${
                              action === "deposit" || action === "clear"
                                ? "bg-accent text-white hover:bg-accent-hover"
                                : "border border-line hover:border-accent hover:text-accent"
                            }`}
                          >
                            {actionLabels[action]}
                          </button>
                        ))}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {data !== null && data.cheques.length === 0 ? (
            <p className="py-8 text-sm text-charcoal/60">No cheques with this status.</p>
          ) : null}
        </div>
      </div>
      {pending ? (
        <ChequeActionModal
          cheque={pending.cheque}
          action={pending.action}
          onClose={() => setPending(null)}
          onDone={(updated) => {
            setPending(null);
            setToast(`Cheque ${updated.cheque_number} is now ${CHEQUE_STATUS_LABELS[updated.status].toLowerCase()}.`);
            void load();
          }}
        />
      ) : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}

function ChequeActionModal({
  cheque,
  action,
  onClose,
  onDone,
}: {
  cheque: Cheque;
  action: ChequeAction;
  onClose: () => void;
  onDone: (cheque: Cheque) => void;
}) {
  const [note, setNote] = useState("");
  const [fee, setFee] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reverses = action === "bounce" || action === "cancel";

  const save = async () => {
    const feeCents = fee.trim() === "" ? 0 : toCents(fee);
    if (feeCents === null) return setError("Enter a fee like 50.00, or leave it empty.");
    if (action === "bounce" && note.trim().length < 3) return setError("Give the bank's reason for the bounce.");
    setBusy(true);
    setError(null);
    try {
      onDone(await apiPost<Cheque>(`/api/v1/cheques/${cheque.id}/${action}`, { note: note.trim(), fee_cents: feeCents }));
    } catch (caught) {
      setError(message(caught, "Could not update the cheque."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={`${actionLabels[action]} · ${cheque.cheque_number}`}
      subtitle={`${cheque.bank} · ${formatMoney(cheque.amount_cents, cheque.currency)}${cheque.customer_name ? ` · ${cheque.customer_name}` : ""}`}
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : actionLabels[action]}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        {reverses ? (
          <p className="rounded-2xl bg-accent/10 px-4 py-3 text-sm text-accent">
            The payment is reversed: {formatMoney(cheque.amount_cents, cheque.currency)} goes back on the customer's account
            {action === "bounce" ? " and the account is put on credit hold" : ""}.
          </p>
        ) : null}
        <TextField
          label={action === "bounce" ? "Bank's reason" : "Note (optional)"}
          value={note}
          maxLength={255}
          onChange={(event) => setNote(event.target.value)}
        />
        {action === "bounce" && cheque.customer_id ? (
          <TextField
            label="Bounced cheque fee (optional)"
            inputMode="decimal"
            value={fee}
            className="tabular-nums"
            onChange={(event) => setFee(event.target.value)}
          />
        ) : null}
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
