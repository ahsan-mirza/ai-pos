import {
  EXPENSE_CATEGORY_LABELS,
  formatMoney,
  type Expense,
  type ExpenseCategory,
  type ExpenseList,
  type ExpensePaidFrom,
  type PettyCash,
  type TaxCategory,
} from "@ai-pos/shared-types";
import { actionHoverClass } from "@ai-pos/ui";
import { Plus, Wallet } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, FilterSelect, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { Toast } from "../../components/ui/Toast";
import { Toggle } from "../../components/ui/Toggle";
import { apiGet, apiPost } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCurrency } from "../../lib/currency";
import { toCents } from "../customers/api";
import { storeOptions, useStores } from "../inventory/shared";
import { errorMessage } from "../users/api";

const iso = (value: Date) => value.toISOString().slice(0, 10);
const monthStart = () => {
  const now = new Date();
  return iso(new Date(Date.UTC(now.getFullYear(), now.getMonth(), 1)));
};
const shortDate = (value: string) =>
  new Date(`${value.slice(0, 10)}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" });

const paidFromLabels: Record<ExpensePaidFrom, string> = { PETTY_CASH: "Petty cash", BANK: "Bank", CARD: "Card" };
const categories = Object.keys(EXPENSE_CATEGORY_LABELS) as ExpenseCategory[];

export function ExpensesPage() {
  const { user } = useAuth();
  const { currency } = useCurrency();
  const { stores } = useStores();
  const [storeId, setStoreId] = useState(user?.store_id ?? "");
  const [from, setFrom] = useState(monthStart());
  const [to, setTo] = useState(iso(new Date()));
  const [data, setData] = useState<ExpenseList | null>(null);
  const [petty, setPetty] = useState<PettyCash | null>(null);
  const [dialog, setDialog] = useState<"expense" | "topup" | "count" | null>(null);
  const [voiding, setVoiding] = useState<Expense | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  const money = (cents: number) => formatMoney(cents, currency);

  useEffect(() => {
    if (!storeId && stores.length) setStoreId(stores.find((store) => !store.is_warehouse)?.id ?? stores[0]!.id);
  }, [storeId, stores]);

  const load = useCallback(async () => {
    if (!storeId) return;
    try {
      const [list, float] = await Promise.all([
        apiGet<ExpenseList>(`/api/v1/expenses?from=${from}&to=${to}&store_id=${storeId}`),
        apiGet<PettyCash>(`/api/v1/expenses/petty-cash/${storeId}`),
      ]);
      setData(list);
      setPetty(float);
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load expenses."));
    }
  }, [from, to, storeId]);

  useEffect(() => {
    void load();
  }, [load]);

  const done = (message: string) => {
    setToast(message);
    setDialog(null);
    setVoiding(null);
    void load();
  };

  const biggest = Math.max(1, ...(data?.by_category ?? []).map((row) => row.total_cents));

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">Spent in the period</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{data ? money(data.total_cents) : "—"}</p>
          <p className="mt-2 text-xs text-white/50">{data?.items.filter((row) => row.status !== "VOID").length ?? 0} expenses, VAT included</p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">Recoverable VAT</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{data ? money(data.recoverable_tax_cents) : "—"}</p>
          <p className="mt-2 text-xs text-white/80">Backed by tax invoices; counted in VAT201 box 9</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <div className="flex items-start justify-between">
            <p className="text-sm text-charcoal/60">Petty cash{petty ? ` · ${petty.store_code}` : ""}</p>
            <Wallet size={18} aria-hidden="true" className="text-charcoal/40" />
          </div>
          <p className={`mt-4 text-3xl font-semibold tabular-nums ${petty && petty.balance_cents < 0 ? "text-accent" : ""}`}>
            {petty ? money(petty.balance_cents) : "—"}
          </p>
          <div className="mt-2 flex gap-3 text-xs font-semibold">
            <button type="button" onClick={() => setDialog("topup")} className="text-accent">
              Top up
            </button>
            <button type="button" onClick={() => setDialog("count")} className="text-charcoal/60 hover:text-charcoal">
              Count float
            </button>
          </div>
        </article>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="rounded-card border border-line bg-white p-6">
          <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-xl font-semibold">Expenses</h2>
              <p className="text-sm text-charcoal/60">Rent, utilities, fuel and petty spending, each with its VAT.</p>
            </div>
            <div className="flex flex-wrap items-end gap-3">
              {user?.store_id ? null : (
                <FilterSelect label="Branch" value={storeId} options={storeOptions(stores)} onChange={setStoreId} className="w-52" />
              )}
              <TextField label="From" type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
              <TextField label="To" type="date" value={to} onChange={(event) => setTo(event.target.value)} />
              <PrimaryButton onClick={() => setDialog("expense")}>
                <Plus size={16} aria-hidden="true" className="-ml-1 mr-1.5" /> Record expense
              </PrimaryButton>
            </div>
          </div>
          <ErrorNote message={error} />
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-charcoal/50">
                <tr>
                  <th className="pb-3 font-medium">Date</th>
                  <th className="pb-3 font-medium">Expense</th>
                  <th className="pb-3 font-medium">Paid from</th>
                  <th className="pb-3 text-right font-medium">VAT</th>
                  <th className="pb-3 text-right font-medium">Total</th>
                  <th className="w-20 pb-3" />
                </tr>
              </thead>
              <tbody>
                {(data?.items ?? []).map((row) => (
                  <tr key={row.id} className={`border-t border-line align-top ${row.status === "VOID" ? "opacity-50" : ""}`}>
                    <td className="py-3 tabular-nums">{shortDate(row.spent_on)}</td>
                    <td className="py-3">
                      <span className="block font-medium">{row.description}</span>
                      <span className="block text-xs text-charcoal/50">
                        {EXPENSE_CATEGORY_LABELS[row.category]}
                        {row.payee ? ` · ${row.payee}` : ""} · <span className="font-mono">{row.number}</span>
                        {row.status === "VOID" ? ` · void: ${row.void_reason}` : ""}
                      </span>
                    </td>
                    <td className="py-3 text-charcoal/70">{paidFromLabels[row.paid_from]}</td>
                    <td className="py-3 text-right tabular-nums">
                      {money(row.tax_cents)}
                      <span className={`block text-[11px] ${row.recoverable_tax_cents ? "text-charcoal/50" : "text-charcoal/40"}`}>
                        {row.tax_cents === 0 ? "" : row.recoverable_tax_cents ? "recoverable" : "no tax invoice"}
                      </span>
                    </td>
                    <td className="py-3 text-right font-semibold tabular-nums">{money(row.total_cents)}</td>
                    <td className="py-3 text-right">
                      {row.status === "RECORDED" ? (
                        <button type="button" onClick={() => setVoiding(row)} className={`rounded-full px-2.5 py-1 text-xs font-semibold text-charcoal/50 ${actionHoverClass("danger")}`}>
                          Void
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data && data.items.length === 0 ? <p className="py-8 text-sm text-charcoal/60">No expenses in this period.</p> : null}
          </div>
        </div>

        <div className="space-y-4">
          <article className="rounded-card border border-line bg-white p-6">
            <h3 className="font-semibold">By category</h3>
            <ul className="mt-4 space-y-3">
              {(data?.by_category ?? []).map((row) => (
                <li key={row.category}>
                  <div className="flex items-baseline justify-between text-sm">
                    <span>{EXPENSE_CATEGORY_LABELS[row.category]}</span>
                    <span className="font-semibold tabular-nums">{money(row.total_cents)}</span>
                  </div>
                  <div className="mt-1 h-1.5 rounded-full bg-surface">
                    <div className="h-1.5 rounded-full bg-accent" style={{ width: `${(row.total_cents / biggest) * 100}%` }} />
                  </div>
                </li>
              ))}
              {data && data.by_category.length === 0 ? <li className="text-sm text-charcoal/60">Nothing spent yet.</li> : null}
            </ul>
          </article>
          <article className="rounded-card bg-charcoal p-6 text-white">
            <h3 className="font-semibold">Petty cash book</h3>
            <ul className="mt-3 space-y-2">
              {(petty?.entries ?? []).slice(0, 8).map((entry) => (
                <li key={entry.id} className="flex items-start justify-between gap-3 text-sm">
                  <span className="min-w-0">
                    <span className="block truncate">{entry.note || entry.kind.toLowerCase()}</span>
                    <span className="block text-[11px] text-white/50">
                      {new Date(entry.created_at).toLocaleDateString(undefined, { day: "numeric", month: "short" })}
                      {entry.user_name ? ` · ${entry.user_name}` : ""}
                    </span>
                  </span>
                  <span className={`shrink-0 font-semibold tabular-nums ${entry.amount_cents > 0 ? "text-emerald-300" : ""}`}>
                    {entry.amount_cents > 0 ? "+" : ""}
                    {money(entry.amount_cents)}
                  </span>
                </li>
              ))}
              {petty && petty.entries.length === 0 ? <li className="text-sm text-white/60">Top up the float to pay small expenses in cash.</li> : null}
            </ul>
          </article>
        </div>
      </div>

      {dialog === "expense" && storeId ? (
        <ExpenseModal storeId={storeId} pettyCents={petty?.balance_cents ?? 0} onClose={() => setDialog(null)} onSaved={(row) => done(`${row.number} recorded: ${money(row.total_cents)}.`)} />
      ) : null}
      {(dialog === "topup" || dialog === "count") && storeId ? (
        <PettyCashModal mode={dialog} storeId={storeId} balance={petty?.balance_cents ?? 0} onClose={() => setDialog(null)} onSaved={done} />
      ) : null}
      {voiding ? <VoidModal expense={voiding} onClose={() => setVoiding(null)} onSaved={() => done(`${voiding.number} voided.`)} /> : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}

function ExpenseModal({
  storeId,
  pettyCents,
  onClose,
  onSaved,
}: {
  storeId: string;
  pettyCents: number;
  onClose: () => void;
  onSaved: (expense: Expense) => void;
}) {
  const { currency } = useCurrency();
  const [category, setCategory] = useState<ExpenseCategory>("UTILITIES");
  const [description, setDescription] = useState("");
  const [payee, setPayee] = useState("");
  const [trn, setTrn] = useState("");
  const [spentOn, setSpentOn] = useState(iso(new Date()));
  const [total, setTotal] = useState("");
  const [taxCategory, setTaxCategory] = useState<TaxCategory>("STANDARD");
  const [invoice, setInvoice] = useState(false);
  const [paidFrom, setPaidFrom] = useState<ExpensePaidFrom>(pettyCents > 0 ? "PETTY_CASH" : "BANK");
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cents = toCents(total);
  const vat = cents !== null && taxCategory === "STANDARD" ? Math.round((cents * 500) / 10500) : 0;

  const save = async () => {
    if (cents === null || cents < 1 || description.trim().length < 2) return setError("Describe the expense and enter the amount paid.");
    if (invoice && vat && !/^\d{15}$/.test(trn)) return setError("Enter the 15-digit TRN printed on the tax invoice.");
    setBusy(true);
    try {
      onSaved(
        await apiPost<Expense>("/api/v1/expenses", {
          store_id: storeId,
          category,
          description: description.trim(),
          payee: payee.trim(),
          payee_trn: trn || null,
          spent_on: spentOn,
          total_cents: cents,
          tax_category: taxCategory,
          has_tax_invoice: invoice,
          paid_from: paidFrom,
          reference: reference.trim(),
        }),
      );
    } catch (caught) {
      setError(errorMessage(caught, "Could not record the expense."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Record an expense"
      subtitle="Enter what was paid, VAT included. Keep the tax invoice to recover the VAT."
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : "Record expense"}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid gap-4 md:grid-cols-2">
          <FilterSelect
            label="Category"
            value={category}
            options={categories.map((value) => ({ value, label: EXPENSE_CATEGORY_LABELS[value] }))}
            onChange={setCategory}
          />
          <TextField label="Date" type="date" value={spentOn} onChange={(event) => setSpentOn(event.target.value)} />
        </div>
        <TextField label="What for" value={description} maxLength={200} placeholder="DEWA bill, October" onChange={(event) => setDescription(event.target.value)} />
        <div className="grid gap-4 md:grid-cols-2">
          <TextField label="Paid to (optional)" value={payee} maxLength={120} onChange={(event) => setPayee(event.target.value)} />
          <TextField label="Total paid" inputMode="decimal" value={total} className="tabular-nums" onChange={(event) => setTotal(event.target.value)} />
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <FilterSelect
            label="VAT on it"
            value={taxCategory}
            options={[
              { value: "STANDARD", label: "5% VAT included" },
              { value: "ZERO", label: "Zero-rated" },
              { value: "EXEMPT", label: "Exempt / no VAT" },
            ]}
            onChange={setTaxCategory}
          />
          <p className="self-end rounded-xl bg-surface px-4 py-3 text-sm tabular-nums">VAT {formatMoney(vat, currency)}</p>
        </div>
        {vat ? (
          <>
            <Toggle checked={invoice} onChange={setInvoice} label="I have a tax invoice" description="Only VAT on a valid tax invoice is recoverable." />
            {invoice ? (
              <TextField label="Supplier TRN" value={trn} maxLength={15} onChange={(event) => setTrn(event.target.value.replace(/\D/g, ""))} />
            ) : null}
          </>
        ) : null}
        <SegmentedControl
          label="Paid from"
          value={paidFrom}
          options={(Object.keys(paidFromLabels) as ExpensePaidFrom[]).map((value) => ({
            value,
            label: value === "PETTY_CASH" ? `Petty cash (${formatMoney(pettyCents, currency)})` : paidFromLabels[value],
          }))}
          onChange={setPaidFrom}
        />
        {paidFrom !== "PETTY_CASH" ? (
          <TextField label="Reference (optional)" value={reference} maxLength={64} onChange={(event) => setReference(event.target.value)} />
        ) : null}
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}

function PettyCashModal({
  mode,
  storeId,
  balance,
  onClose,
  onSaved,
}: {
  mode: "topup" | "count";
  storeId: string;
  balance: number;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const { currency } = useCurrency();
  const [amount, setAmount] = useState("");
  const [source, setSource] = useState<"till" | "bank">("bank");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    const cents = toCents(amount);
    if (cents === null || (mode === "topup" && cents < 1)) return setError("Enter an amount like 500.00.");
    if (mode === "count" && note.trim().length < 3) return setError("Say why the count differs.");
    setBusy(true);
    try {
      if (mode === "topup") {
        await apiPost<PettyCash>("/api/v1/expenses/petty-cash/top-up", { store_id: storeId, amount_cents: cents, source, note: note.trim() });
        onSaved(`Petty cash topped up by ${formatMoney(cents, currency)}.`);
      } else {
        await apiPost<PettyCash>("/api/v1/expenses/petty-cash/count", { store_id: storeId, counted_cents: cents, note: note.trim() });
        onSaved(`Petty cash set to the counted ${formatMoney(cents, currency)}.`);
      }
    } catch (caught) {
      setError(errorMessage(caught, "Could not update petty cash."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      title={mode === "topup" ? "Top up petty cash" : "Count petty cash"}
      subtitle={`The book says ${formatMoney(balance, currency)}.`}
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {mode === "topup" ? "Top up" : "Save count"}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        <TextField
          label={mode === "topup" ? "Amount added" : "Cash counted"}
          inputMode="decimal"
          value={amount}
          className="tabular-nums"
          onChange={(event) => setAmount(event.target.value)}
        />
        {mode === "topup" ? (
          <SegmentedControl
            label="Taken from"
            value={source}
            options={[
              { value: "bank", label: "Bank" },
              { value: "till", label: "Till" },
            ]}
            onChange={setSource}
          />
        ) : null}
        <TextField label={mode === "count" ? "Why it differs" : "Note (optional)"} value={note} maxLength={255} onChange={(event) => setNote(event.target.value)} />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}

function VoidModal({ expense, onClose, onSaved }: { expense: Expense; onClose: () => void; onSaved: () => void }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    if (reason.trim().length < 3) return setError("Give a reason.");
    try {
      await apiPost(`/api/v1/expenses/${expense.id}/void`, { reason: reason.trim() });
      onSaved();
    } catch (caught) {
      setError(errorMessage(caught, "Could not void the expense."));
    }
  };
  return (
    <Modal
      title={`Void ${expense.number}?`}
      subtitle={expense.paid_from === "PETTY_CASH" ? "The money goes back into petty cash." : "It drops out of the VAT return and the journal."}
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Back</GhostButton>
          <PrimaryButton onClick={() => void save()}>Void expense</PrimaryButton>
        </>
      }
    >
      <TextField label="Reason" value={reason} maxLength={255} onChange={(event) => setReason(event.target.value)} />
      <ErrorNote message={error} />
    </Modal>
  );
}
