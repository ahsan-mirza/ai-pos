import {
  formatMoney,
  type BillStatus,
  type PayablesSummary,
  type SupplierBalance,
  type SupplierBill,
  type SupplierPayment,
  type SupplierPaymentMethod,
  type SupplierStatement,
  type TaxCategory,
  type UnbilledReceipt,
} from "@ai-pos/shared-types";
import { Banknote, FileInput, Plus, Trash2, UserPlus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { PhoneField, Select, emailError, phoneError, requiredError } from "@ai-pos/ui";
import { ErrorNote, FilterSelect, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { Toast } from "../../components/ui/Toast";
import { apiGet, apiPost, apiPut } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCurrency } from "../../lib/currency";
import { toCents } from "../customers/api";
import { storeOptions, useStores } from "../inventory/shared";
import { fieldErrors } from "../inventory/formErrors";
import { errorMessage } from "../users/api";

type Tab = "suppliers" | "bills" | "payments" | "receipts";
type BillFilter = "UNPAID" | "PAID" | "all";

const today = () => new Date().toISOString().slice(0, 10);
const shortDate = (value: string) =>
  new Date(`${value.slice(0, 10)}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

const methodLabels: Record<SupplierPaymentMethod, string> = {
  cash: "Cash",
  transfer: "Bank transfer",
  card: "Card",
  cheque: "Cheque",
};

function BillChip({ status, overdue }: { status: BillStatus; overdue: number }) {
  if (overdue > 0) return <span className="rounded-full bg-accent px-2.5 py-0.5 text-[11px] font-semibold text-white">{overdue}d overdue</span>;
  const tone =
    status === "PAID"
      ? "bg-surface text-charcoal ring-1 ring-line"
      : status === "VOID"
        ? "bg-white text-charcoal/40 ring-1 ring-line"
        : status === "PARTIAL"
          ? "bg-charcoal text-white"
          : "bg-white text-charcoal ring-1 ring-charcoal/20";
  const label = { OPEN: "Unpaid", PARTIAL: "Part paid", PAID: "Paid", VOID: "Void" }[status];
  return <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${tone}`}>{label}</span>;
}

export function PayablesPage() {
  const { currency } = useCurrency();
  const [tab, setTab] = useState<Tab>("suppliers");
  const [billFilter, setBillFilter] = useState<BillFilter>("UNPAID");
  const [summary, setSummary] = useState<PayablesSummary | null>(null);
  const [bills, setBills] = useState<SupplierBill[]>([]);
  const [payments, setPayments] = useState<SupplierPayment[]>([]);
  const [receipts, setReceipts] = useState<UnbilledReceipt[]>([]);
  const [statementFor, setStatementFor] = useState<string | null>(null);
  const [dialog, setDialog] = useState<"supplier" | "bill" | "pay" | null>(null);
  const [payFor, setPayFor] = useState<string | null>(null);
  const [billing, setBilling] = useState<UnbilledReceipt | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  const money = (cents: number) => formatMoney(cents, currency);

  const load = useCallback(async () => {
    try {
      const [nextSummary, nextBills, nextPayments, nextReceipts] = await Promise.all([
        apiGet<PayablesSummary>("/api/v1/payables/summary"),
        apiGet<SupplierBill[]>(`/api/v1/payables/bills${billFilter === "all" ? "" : `?status=${billFilter}`}`),
        apiGet<SupplierPayment[]>("/api/v1/payables/payments"),
        apiGet<UnbilledReceipt[]>("/api/v1/payables/receipts/unbilled"),
      ]);
      setSummary(nextSummary);
      setBills(nextBills);
      setPayments(nextPayments);
      setReceipts(nextReceipts);
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load payables."));
    }
  }, [billFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  const done = (message: string) => {
    setToast(message);
    setDialog(null);
    setBilling(null);
    void load();
  };

  const paymentAction = async (payment: SupplierPayment, action: "clear" | "void") => {
    try {
      await apiPost<SupplierPayment>(`/api/v1/payables/payments/${payment.id}/${action}`, action === "void" ? { note: "" } : {});
      done(action === "clear" ? `Cheque ${payment.cheque_number} marked cleared.` : "Payment voided; the bills it paid are open again.");
    } catch (caught) {
      setError(errorMessage(caught, "Could not update the payment."));
    }
  };

  const suppliers = summary?.suppliers ?? [];

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-4">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">Owed to suppliers</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{summary ? money(summary.outstanding_cents) : "—"}</p>
          <p className="mt-2 text-xs text-white/50">Unpaid bills across every supplier</p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">Overdue</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{summary ? money(summary.overdue_cents) : "—"}</p>
          <p className="mt-2 text-xs text-white/80">Past the supplier's credit terms</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Due in 7 days</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{summary ? money(summary.due_7d_cents) : "—"}</p>
          <p className="mt-2 text-xs text-charcoal/50">Plan this week's payments</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Cheques issued</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{summary ? money(summary.cheques_issued_cents) : "—"}</p>
          <p className="mt-2 text-xs text-charcoal/50">Written, not yet cleared by the bank</p>
        </article>
      </div>

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Accounts payable</h2>
            <p className="text-sm text-charcoal/60">Supplier bills, what is due when, and how each one was paid.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <GhostButton onClick={() => setDialog("supplier")}>
              <UserPlus size={15} aria-hidden="true" className="-ml-1 mr-1.5" /> Add supplier
            </GhostButton>
            <GhostButton onClick={() => setDialog("bill")}>
              <Plus size={15} aria-hidden="true" className="-ml-1 mr-1.5" /> Record bill
            </GhostButton>
            <PrimaryButton
              onClick={() => {
                setPayFor(null);
                setDialog("pay");
              }}
            >
              <Banknote size={16} aria-hidden="true" className="-ml-1 mr-1.5" /> Pay supplier
            </PrimaryButton>
          </div>
        </div>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <SegmentedControl
            label="View"
            value={tab}
            options={[
              { value: "suppliers", label: "Suppliers" },
              { value: "bills", label: "Bills" },
              { value: "payments", label: "Payments" },
              { value: "receipts", label: `To bill${receipts.length ? ` (${receipts.length})` : ""}` },
            ]}
            onChange={setTab}
          />
          {tab === "bills" ? (
            <SegmentedControl
              label="Bill status"
              value={billFilter}
              options={[
                { value: "UNPAID", label: "Unpaid" },
                { value: "PAID", label: "Paid" },
                { value: "all", label: "All" },
              ]}
              onChange={setBillFilter}
            />
          ) : null}
        </div>
        <ErrorNote message={error} />

        {tab === "suppliers" ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-charcoal/50">
                <tr>
                  <th className="pb-3 font-medium">Supplier</th>
                  <th className="pb-3 font-medium">Terms</th>
                  <th className="pb-3 text-right font-medium">Open bills</th>
                  <th className="pb-3 text-right font-medium">Outstanding</th>
                  <th className="pb-3 text-right font-medium">Overdue</th>
                  <th className="pb-3 text-right font-medium">Due in 7 days</th>
                  <th className="pb-3 text-right font-medium">Credit</th>
                </tr>
              </thead>
              <tbody>
                {suppliers.map((row) => (
                  <tr
                    key={row.supplier_id}
                    onClick={() => setStatementFor(row.supplier_id)}
                    className="cursor-pointer border-t border-line transition-colors hover:bg-surface/60"
                  >
                    <td className="py-3">
                      <span className="block font-medium">{row.name}</span>
                      <span className="block font-mono text-xs text-charcoal/50">
                        {row.code}
                        {row.trn ? ` · TRN ${row.trn}` : ""}
                      </span>
                    </td>
                    <td className="py-3 text-charcoal/70">{row.payment_terms_days ? `${row.payment_terms_days} days` : "On receipt"}</td>
                    <td className="py-3 text-right tabular-nums">{row.open_bills}</td>
                    <td className="py-3 text-right font-semibold tabular-nums">{money(row.outstanding_cents)}</td>
                    <td className={`py-3 text-right tabular-nums ${row.overdue_cents ? "font-semibold text-accent" : "text-charcoal/40"}`}>
                      {money(row.overdue_cents)}
                    </td>
                    <td className="py-3 text-right tabular-nums">{money(row.due_7d_cents)}</td>
                    <td className="py-3 text-right tabular-nums text-charcoal/60">{row.credit_cents ? money(row.credit_cents) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {summary && suppliers.length === 0 ? <p className="py-8 text-sm text-charcoal/60">Add a supplier to start recording bills.</p> : null}
          </div>
        ) : null}

        {tab === "bills" ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-charcoal/50">
                <tr>
                  <th className="pb-3 font-medium">Bill</th>
                  <th className="pb-3 font-medium">Supplier</th>
                  <th className="pb-3 font-medium">Dated</th>
                  <th className="pb-3 font-medium">Due</th>
                  <th className="pb-3 text-right font-medium">VAT</th>
                  <th className="pb-3 text-right font-medium">Total</th>
                  <th className="pb-3 text-right font-medium">Balance</th>
                  <th className="pb-3 pl-6 font-medium">Status</th>
                  <th className="w-10 pb-3" />
                </tr>
              </thead>
              <tbody>
                {bills.map((bill) => (
                  <tr key={bill.id} className="border-t border-line align-top">
                    <td className="py-3">
                      <span className="block font-mono text-xs font-semibold">{bill.number}</span>
                      <span className="block text-xs text-charcoal/50">
                        {bill.store_code}
                        {bill.goods_receipt_number ? ` · ${bill.goods_receipt_number}` : ""}
                      </span>
                    </td>
                    <td className="py-3">{bill.supplier_name}</td>
                    <td className="py-3 tabular-nums">{shortDate(bill.bill_date)}</td>
                    <td className={`py-3 tabular-nums ${bill.overdue_days ? "font-semibold text-accent" : ""}`}>{shortDate(bill.due_date)}</td>
                    <td className="py-3 text-right tabular-nums text-charcoal/60">{money(bill.tax_cents)}</td>
                    <td className="py-3 text-right tabular-nums">{money(bill.total_cents)}</td>
                    <td className="py-3 text-right font-semibold tabular-nums">{money(bill.balance_cents)}</td>
                    <td className="py-3 pl-6">
                      <BillChip status={bill.status} overdue={bill.overdue_days} />
                    </td>
                    <td className="py-3 text-right">
                      {bill.status === "OPEN" ? (
                        <button
                          type="button"
                          aria-label={`Void bill ${bill.number}`}
                          onClick={() =>
                            void apiPost<SupplierBill>(`/api/v1/payables/bills/${bill.id}/void`, {})
                              .then(() => done(`Bill ${bill.number} voided.`))
                              .catch((caught: unknown) => setError(errorMessage(caught, "Could not void the bill.")))
                          }
                          className="rounded-full p-1.5 text-charcoal/40 hover:bg-surface hover:text-accent"
                        >
                          <Trash2 size={14} aria-hidden="true" />
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {bills.length === 0 ? <p className="py-8 text-sm text-charcoal/60">No bills with this status.</p> : null}
          </div>
        ) : null}

        {tab === "payments" ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-charcoal/50">
                <tr>
                  <th className="pb-3 font-medium">Paid</th>
                  <th className="pb-3 font-medium">Supplier</th>
                  <th className="pb-3 font-medium">How</th>
                  <th className="pb-3 font-medium">Against</th>
                  <th className="pb-3 text-right font-medium">Amount</th>
                  <th className="pb-3 pl-6 font-medium">Status</th>
                  <th className="pb-3 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {payments.map((payment) => (
                  <tr key={payment.id} className={`border-t border-line align-top ${payment.status === "VOID" ? "opacity-50" : ""}`}>
                    <td className="py-3 tabular-nums">{shortDate(payment.paid_on)}</td>
                    <td className="py-3">{payment.supplier_name}</td>
                    <td className="py-3">
                      {methodLabels[payment.method]}
                      {payment.cheque_number ? (
                        <span className="block text-xs text-charcoal/50 tabular-nums">
                          #{payment.cheque_number} · {payment.cheque_bank} · {payment.cheque_date ? shortDate(payment.cheque_date) : ""}
                        </span>
                      ) : payment.reference ? (
                        <span className="block text-xs text-charcoal/50">{payment.reference}</span>
                      ) : null}
                    </td>
                    <td className="py-3 text-xs text-charcoal/60">
                      {payment.allocations.map((row) => `${row.bill_number} (${money(row.amount_cents)})`).join(", ") || "—"}
                      {payment.unallocated_cents ? <span className="block">{money(payment.unallocated_cents)} on account</span> : null}
                    </td>
                    <td className="py-3 text-right font-semibold tabular-nums">{money(payment.amount_cents)}</td>
                    <td className="py-3 pl-6">
                      <span
                        className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                          payment.status === "ISSUED" ? "bg-charcoal text-white" : "bg-surface text-charcoal ring-1 ring-line"
                        }`}
                      >
                        {{ POSTED: "Paid", ISSUED: "Cheque issued", CLEARED: "Cleared", VOID: "Void" }[payment.status]}
                      </span>
                    </td>
                    <td className="py-3">
                      <div className="flex justify-end gap-1">
                        {payment.status === "ISSUED" ? (
                          <button
                            type="button"
                            onClick={() => void paymentAction(payment, "clear")}
                            className="rounded-full bg-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-accent-hover"
                          >
                            Mark cleared
                          </button>
                        ) : null}
                        {payment.status === "ISSUED" || payment.status === "POSTED" ? (
                          <button
                            type="button"
                            onClick={() => void paymentAction(payment, "void")}
                            className="rounded-full border border-line px-3 py-1.5 text-xs font-semibold hover:border-accent hover:text-accent"
                          >
                            {payment.status === "ISSUED" ? "Cancel cheque" : "Void"}
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {payments.length === 0 ? <p className="py-8 text-sm text-charcoal/60">No supplier payments yet.</p> : null}
          </div>
        ) : null}

        {tab === "receipts" ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-charcoal/50">
                <tr>
                  <th className="pb-3 font-medium">Receipt</th>
                  <th className="pb-3 font-medium">Supplier</th>
                  <th className="pb-3 font-medium">Received</th>
                  <th className="pb-3 text-right font-medium">Units</th>
                  <th className="pb-3 text-right font-medium">At PO cost</th>
                  <th className="pb-3 text-right font-medium" />
                </tr>
              </thead>
              <tbody>
                {receipts.map((receipt) => (
                  <tr key={receipt.goods_receipt_id ?? receipt.purchase_batch_id} className="border-t border-line">
                    <td className="py-3">
                      <span className="block font-mono text-xs font-semibold">{receipt.number}</span>
                      <span className="block text-xs text-charcoal/50">
                        {receipt.purchase_batch_id ? "Imported batch" : "Purchase order"} {receipt.purchase_order_number} · {receipt.store_code}
                      </span>
                    </td>
                    <td className="py-3">{receipt.supplier_name}</td>
                    <td className="py-3 tabular-nums">{shortDate(receipt.received_on)}</td>
                    <td className="py-3 text-right tabular-nums">{receipt.units}</td>
                    <td className="py-3 text-right tabular-nums">{money(receipt.value_cents)}</td>
                    <td className="py-3 text-right">
                      <button
                        type="button"
                        onClick={() => setBilling(receipt)}
                        className="inline-flex items-center gap-1.5 rounded-full bg-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-accent-hover"
                      >
                        <FileInput size={13} aria-hidden="true" /> Enter supplier invoice
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {receipts.length === 0 ? <p className="py-8 text-sm text-charcoal/60">Every goods receipt and imported batch has its supplier invoice.</p> : null}
          </div>
        ) : null}
      </div>

      {statementFor ? (
        <StatementModal
          supplierId={statementFor}
          onClose={() => setStatementFor(null)}
          onPay={() => {
            setPayFor(statementFor);
            setStatementFor(null);
            setDialog("pay");
          }}
          onSaved={() => void load()}
        />
      ) : null}
      {dialog === "supplier" ? <SupplierModal onClose={() => setDialog(null)} onSaved={(name) => done(`${name} added.`)} /> : null}
      {dialog === "bill" ? (
        <BillModal suppliers={suppliers} onClose={() => setDialog(null)} onSaved={(bill) => done(`Bill ${bill.number} recorded: ${money(bill.total_cents)}.`)} />
      ) : null}
      {dialog === "pay" ? (
        <PayModal
          suppliers={suppliers}
          supplierId={payFor}
          onClose={() => setDialog(null)}
          onSaved={(payment) => done(`${money(payment.amount_cents)} paid to ${payment.supplier_name}.`)}
        />
      ) : null}
      {billing ? (
        <ReceiptBillModal
          receipt={billing}
          suppliers={suppliers}
          onClose={() => setBilling(null)}
          onSaved={(bill) => done(`Bill ${bill.number} recorded from ${billing.number}.`)}
        />
      ) : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}

function supplierOptions(suppliers: SupplierBalance[]) {
  return suppliers.map((row) => ({ value: row.supplier_id, label: row.name, hint: row.code }));
}

function SupplierModal({ onClose, onSaved }: { onClose: () => void; onSaved: (name: string) => void }) {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nameError, setNameError] = useState<string | undefined>();
  const [phoneErrorText, setPhoneErrorText] = useState<string | undefined>();
  const [emailErrorText, setEmailErrorText] = useState<string | undefined>();
  const save = async () => {
    const nextName = name.trim().length < 2 ? "Enter the supplier's name." : requiredError(name, "the supplier's name");
    const nextPhone = phoneError(phone);
    const nextEmail = emailError(email);
    setNameError(nextName);
    setPhoneErrorText(nextPhone);
    setEmailErrorText(nextEmail);
    if (nextName || nextPhone || nextEmail) {
      setError(null);
      return;
    }
    setBusy(true);
    try {
      await apiPost("/api/v1/payables/suppliers", { name: name.trim(), phone: phone.trim() || null, email: email.trim() || null });
      onSaved(name.trim());
    } catch (caught) {
      const fields = fieldErrors(caught);
      setNameError(fields.name);
      setPhoneErrorText(fields.phone);
      setEmailErrorText(fields.email);
      setError(fields.name || fields.phone || fields.email ? null : errorMessage(caught, "Could not add the supplier."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      title="Add a supplier"
      subtitle="Set their credit terms and TRN from the supplier's statement afterwards."
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : "Add supplier"}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        <TextField
          label="Name"
          required
          value={name}
          maxLength={120}
          error={nameError}
          onChange={(event) => {
            setName(event.target.value);
            setNameError(undefined);
          }}
        />
        <div className="grid gap-4 md:grid-cols-2">
          <PhoneField
            label="Phone"
            value={phone}
            error={phoneErrorText}
            onChange={(next) => {
              setPhone(next);
              setPhoneErrorText(undefined);
            }}
          />
          <TextField
            label="Email"
            type="email"
            value={email}
            error={emailErrorText}
            onChange={(event) => {
              setEmail(event.target.value);
              setEmailErrorText(undefined);
            }}
          />
        </div>
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}

interface DraftLine {
  description: string;
  quantity: string;
  cost: string;
  tax: TaxCategory;
}

function BillModal({
  suppliers,
  onClose,
  onSaved,
}: {
  suppliers: SupplierBalance[];
  onClose: () => void;
  onSaved: (bill: SupplierBill) => void;
}) {
  const { user } = useAuth();
  const { currency } = useCurrency();
  const { stores } = useStores();
  const [supplierId, setSupplierId] = useState(suppliers[0]?.supplier_id ?? "");
  const [storeId, setStoreId] = useState(user?.store_id ?? "");
  const [number, setNumber] = useState("");
  const [billDate, setBillDate] = useState(today());
  const [lines, setLines] = useState<DraftLine[]>([{ description: "", quantity: "1", cost: "", tax: "STANDARD" }]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!storeId && stores.length) setStoreId(stores.find((store) => !store.is_warehouse)?.id ?? stores[0]!.id);
  }, [storeId, stores]);

  const parsed = lines.map((line) => ({ ...line, qty: Number(line.quantity), cents: toCents(line.cost) }));
  const net = parsed.reduce((sum, line) => sum + (line.cents ?? 0) * (Number.isInteger(line.qty) ? line.qty : 0), 0);
  const vat = parsed.reduce(
    (sum, line) => sum + (line.tax === "STANDARD" ? Math.round(((line.cents ?? 0) * (Number.isInteger(line.qty) ? line.qty : 0) * 5) / 100) : 0),
    0,
  );

  const save = async () => {
    if (!supplierId || !storeId || !number.trim()) return setError("Choose the supplier and branch, and enter their invoice number.");
    if (parsed.some((line) => !line.description.trim() || !Number.isInteger(line.qty) || line.qty < 1 || line.cents === null)) {
      return setError("Every line needs a description, a whole quantity and a cost like 120.00.");
    }
    setBusy(true);
    try {
      onSaved(
        await apiPost<SupplierBill>("/api/v1/payables/bills", {
          supplier_id: supplierId,
          store_id: storeId,
          number: number.trim(),
          bill_date: billDate,
          lines: parsed.map((line) => ({
            description: line.description.trim(),
            quantity: line.qty,
            unit_cost_cents: line.cents,
            tax_category: line.tax,
          })),
        }),
      );
    } catch (caught) {
      setError(errorMessage(caught, "Could not record the bill."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Record a supplier bill"
      subtitle="For services and stock that did not come through a purchase order. Costs exclude VAT."
      width="lg"
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : `Record ${formatMoney(net + vat, currency)}`}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid gap-4 md:grid-cols-2">
          <FilterSelect label="Supplier" value={supplierId} options={supplierOptions(suppliers)} onChange={setSupplierId} />
          {user?.store_id ? null : <FilterSelect label="Branch" value={storeId} options={storeOptions(stores)} onChange={setStoreId} />}
          <TextField label="Supplier invoice number" value={number} maxLength={40} onChange={(event) => setNumber(event.target.value)} />
          <TextField label="Invoice date" type="date" value={billDate} onChange={(event) => setBillDate(event.target.value)} />
        </div>
        <div className="space-y-2">
          {lines.map((line, index) => (
            <div key={index} className="grid grid-cols-[1fr_5rem_7rem_8rem_2rem] items-center gap-2">
              <textarea
                aria-label="Description"
                rows={2}
                placeholder="What was billed"
                value={line.description}
                onChange={(event) => setLines(lines.map((row, at) => (at === index ? { ...row, description: event.target.value } : row)))}
                className="min-h-16 resize-y rounded-xl bg-surface px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
              />
              <input
                aria-label="Quantity"
                inputMode="numeric"
                value={line.quantity}
                onChange={(event) => setLines(lines.map((row, at) => (at === index ? { ...row, quantity: event.target.value } : row)))}
                className="rounded-xl bg-surface px-3 py-2.5 text-right text-sm tabular-nums focus:outline-none focus:ring-2 focus:ring-accent/40"
              />
              <input
                aria-label="Unit cost excluding VAT"
                inputMode="decimal"
                placeholder="0.00"
                value={line.cost}
                onChange={(event) => setLines(lines.map((row, at) => (at === index ? { ...row, cost: event.target.value } : row)))}
                className="rounded-xl bg-surface px-3 py-2.5 text-right text-sm tabular-nums focus:outline-none focus:ring-2 focus:ring-accent/40"
              />
              <Select
                aria-label="VAT"
                value={line.tax}
                onChange={(tax) => setLines(lines.map((row, at) => (at === index ? { ...row, tax: tax as TaxCategory } : row)))}
                options={[
                  { value: "STANDARD", label: "VAT 5%" },
                  { value: "ZERO", label: "Zero-rated" },
                  { value: "EXEMPT", label: "Exempt" },
                ]}
              />
              <button
                type="button"
                aria-label="Remove line"
                disabled={lines.length === 1}
                onClick={() => setLines(lines.filter((_, at) => at !== index))}
                className="rounded-full p-1.5 text-charcoal/40 hover:text-accent disabled:opacity-30"
              >
                <Trash2 size={14} aria-hidden="true" />
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() => setLines([...lines, { description: "", quantity: "1", cost: "", tax: "STANDARD" }])}
            className="text-xs font-semibold text-accent"
          >
            + Add line
          </button>
        </div>
        <p className="rounded-2xl bg-surface px-4 py-3 text-sm tabular-nums">
          Net {formatMoney(net, currency)} · VAT {formatMoney(vat, currency)} · <span className="font-semibold">Total {formatMoney(net + vat, currency)}</span>
        </p>
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}

function ReceiptBillModal({
  receipt,
  suppliers,
  onClose,
  onSaved,
}: {
  receipt: UnbilledReceipt;
  suppliers: SupplierBalance[];
  onClose: () => void;
  onSaved: (bill: SupplierBill) => void;
}) {
  const { currency } = useCurrency();
  const matched = receipt.supplier_id ?? suppliers.find((row) => row.name.toLowerCase() === receipt.supplier_name.toLowerCase())?.supplier_id ?? "";
  const [supplierId, setSupplierId] = useState(matched);
  const [number, setNumber] = useState("");
  const [billDate, setBillDate] = useState(today());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    if (!number.trim() || !supplierId) return setError("Choose the supplier and enter their invoice number.");
    setBusy(true);
    try {
      onSaved(
        await apiPost<SupplierBill>("/api/v1/payables/bills/from-receipt", {
          ...(receipt.purchase_batch_id ? { purchase_batch_id: receipt.purchase_batch_id } : { goods_receipt_id: receipt.goods_receipt_id }),
          number: number.trim(),
          bill_date: billDate,
          supplier_id: supplierId,
        }),
      );
    } catch (caught) {
      setError(errorMessage(caught, "Could not record the bill."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      title={`Supplier invoice for ${receipt.number}`}
      subtitle={`${receipt.units} units received at ${formatMoney(receipt.value_cents, currency)} before VAT; lines and VAT come from the ${receipt.purchase_batch_id ? "imported batch" : "purchase order"}.`}
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : "Record bill"}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        <FilterSelect label="Supplier" value={supplierId} options={supplierOptions(suppliers)} onChange={setSupplierId} />
        <div className="grid gap-4 md:grid-cols-2">
          <TextField label="Supplier invoice number" value={number} maxLength={40} onChange={(event) => setNumber(event.target.value)} />
          <TextField label="Invoice date" type="date" value={billDate} onChange={(event) => setBillDate(event.target.value)} />
        </div>
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}

function PayModal({
  suppliers,
  supplierId: initial,
  onClose,
  onSaved,
}: {
  suppliers: SupplierBalance[];
  supplierId: string | null;
  onClose: () => void;
  onSaved: (payment: SupplierPayment) => void;
}) {
  const { currency } = useCurrency();
  const [supplierId, setSupplierId] = useState(initial ?? suppliers.find((row) => row.outstanding_cents > 0)?.supplier_id ?? suppliers[0]?.supplier_id ?? "");
  const supplier = suppliers.find((row) => row.supplier_id === supplierId);
  const [amount, setAmount] = useState(supplier ? (supplier.outstanding_cents / 100).toFixed(2) : "");
  const [method, setMethod] = useState<SupplierPaymentMethod>("transfer");
  const [reference, setReference] = useState("");
  const [paidOn, setPaidOn] = useState(today());
  const [chequeNumber, setChequeNumber] = useState("");
  const [bank, setBank] = useState("");
  const [chequeDate, setChequeDate] = useState(today());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    const cents = toCents(amount);
    if (!supplierId || cents === null || cents < 1) return setError("Choose the supplier and enter the amount paid.");
    if (method === "cheque" && (!chequeNumber.trim() || !bank.trim())) return setError("Enter the cheque number and bank.");
    setBusy(true);
    try {
      onSaved(
        await apiPost<SupplierPayment>("/api/v1/payables/payments", {
          supplier_id: supplierId,
          amount_cents: cents,
          method,
          reference: reference.trim(),
          paid_on: paidOn,
          cheque: method === "cheque" ? { number: chequeNumber.trim(), bank: bank.trim(), cheque_date: chequeDate } : null,
        }),
      );
    } catch (caught) {
      setError(errorMessage(caught, "Could not record the payment."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Pay a supplier"
      subtitle="The payment settles the oldest due bills first; anything extra stays as credit with the supplier."
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : "Record payment"}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        <FilterSelect
          label="Supplier"
          value={supplierId}
          options={supplierOptions(suppliers)}
          onChange={(next) => {
            setSupplierId(next);
            const row = suppliers.find((item) => item.supplier_id === next);
            setAmount(row ? (row.outstanding_cents / 100).toFixed(2) : "");
          }}
        />
        {supplier ? (
          <p className="rounded-2xl bg-surface px-4 py-3 text-sm tabular-nums">
            Owed {formatMoney(supplier.outstanding_cents, currency)}
            {supplier.overdue_cents ? <span className="font-semibold text-accent"> · {formatMoney(supplier.overdue_cents, currency)} overdue</span> : null}
          </p>
        ) : null}
        <div className="grid gap-4 md:grid-cols-2">
          <TextField label="Amount" inputMode="decimal" value={amount} className="tabular-nums" onChange={(event) => setAmount(event.target.value)} />
          <TextField label="Paid on" type="date" value={paidOn} onChange={(event) => setPaidOn(event.target.value)} />
        </div>
        <SegmentedControl
          label="Method"
          value={method}
          options={(Object.keys(methodLabels) as SupplierPaymentMethod[]).map((value) => ({ value, label: methodLabels[value] }))}
          onChange={setMethod}
        />
        {method === "cheque" ? (
          <div className="grid gap-4 md:grid-cols-3">
            <TextField label="Cheque number" value={chequeNumber} maxLength={32} onChange={(event) => setChequeNumber(event.target.value)} />
            <TextField label="Bank" value={bank} maxLength={80} onChange={(event) => setBank(event.target.value)} />
            <TextField label="Date on cheque" type="date" value={chequeDate} onChange={(event) => setChequeDate(event.target.value)} />
          </div>
        ) : (
          <TextField label="Reference (optional)" value={reference} maxLength={64} onChange={(event) => setReference(event.target.value)} />
        )}
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}

function StatementModal({
  supplierId,
  onClose,
  onPay,
  onSaved,
}: {
  supplierId: string;
  onClose: () => void;
  onPay: () => void;
  onSaved: () => void;
}) {
  const { currency: businessCurrency } = useCurrency();
  const [statement, setStatement] = useState<SupplierStatement | null>(null);
  const [terms, setTerms] = useState("");
  const [trn, setTrn] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<SupplierStatement>(`/api/v1/payables/suppliers/${supplierId}/statement`)
      .then((next) => {
        setStatement(next);
        setTerms(String(next.supplier.payment_terms_days));
        setTrn(next.supplier.trn ?? "");
      })
      .catch((caught: unknown) => setError(errorMessage(caught, "Could not load the statement.")));
  }, [supplierId]);

  const saveTerms = async () => {
    try {
      await apiPut(`/api/v1/payables/suppliers/${supplierId}`, { payment_terms_days: Number(terms) || 0, trn: trn.trim() || null });
      setError(null);
      onSaved();
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the terms."));
    }
  };

  const money = (cents: number) => formatMoney(cents, statement?.currency ?? businessCurrency);
  const aging = statement?.aging;
  const buckets = aging
    ? [
        ["Not due", aging.current],
        ["1–30", aging.days_1_30],
        ["31–60", aging.days_31_60],
        ["61–90", aging.days_61_90],
        ["90+", aging.days_90_plus],
      ]
    : [];

  return (
    <Modal
      title={statement ? statement.supplier.name : "Supplier statement"}
      subtitle={statement ? `Owed ${money(statement.supplier.outstanding_cents)} across ${statement.supplier.open_bills} open bills` : undefined}
      width="lg"
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Close</GhostButton>
          <PrimaryButton onClick={onPay}>
            <Banknote size={16} aria-hidden="true" className="-ml-1 mr-1.5" /> Pay this supplier
          </PrimaryButton>
        </>
      }
    >
      {statement ? (
        <div className="space-y-5">
          <div className="grid grid-cols-5 gap-2">
            {buckets.map(([label, value], index) => (
              <div key={label as string} className={`rounded-2xl px-3 py-2.5 ${index > 0 && (value as number) > 0 ? "bg-accent/10" : "bg-surface"}`}>
                <p className="text-[11px] text-charcoal/60">{label}</p>
                <p className={`text-sm font-semibold tabular-nums ${index > 0 && (value as number) > 0 ? "text-accent" : ""}`}>{money(value as number)}</p>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap items-end gap-3 rounded-2xl border border-line p-3">
            <TextField label="Credit terms (days)" inputMode="numeric" value={terms} onChange={(event) => setTerms(event.target.value.replace(/\D/g, ""))} />
            <TextField label="Supplier TRN" value={trn} maxLength={15} onChange={(event) => setTrn(event.target.value.replace(/\D/g, ""))} />
            <GhostButton onClick={() => void saveTerms()}>Save terms</GhostButton>
          </div>
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-2 font-medium">Date</th>
                <th className="pb-2 font-medium">Reference</th>
                <th className="pb-2 text-right font-medium">Billed</th>
                <th className="pb-2 text-right font-medium">Paid</th>
                <th className="pb-2 text-right font-medium">Balance</th>
              </tr>
            </thead>
            <tbody>
              {statement.rows.map((row, index) => (
                <tr key={index} className="border-t border-line">
                  <td className="py-2 tabular-nums">{shortDate(row.on)}</td>
                  <td className="py-2">
                    <span className="block font-medium">{row.kind === "BILL" ? `Bill ${row.reference}` : `Payment ${row.reference}`}</span>
                    <span className="block text-xs text-charcoal/50">{row.note}</span>
                  </td>
                  <td className="py-2 text-right tabular-nums">{row.bill_cents ? money(row.bill_cents) : ""}</td>
                  <td className="py-2 text-right tabular-nums">{row.paid_cents ? money(row.paid_cents) : ""}</td>
                  <td className="py-2 text-right font-semibold tabular-nums">{money(row.balance_cents)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {statement.rows.length === 0 ? <p className="text-sm text-charcoal/60">No bills or payments yet.</p> : null}
        </div>
      ) : null}
      <ErrorNote message={error} />
    </Modal>
  );
}
