import {
  formatMoney,
  Permission,
  type Expense,
  type ExpenseBill,
  type ExpenseCategoryOption,
  type ExpenseList,
  type ExpensePaidFrom,
  type ExpenseSupplier,
  type PettyCash,
  type TaxCategory,
} from "@ai-pos/shared-types";
import { ChevronDown, ImagePlus, Plus, Wallet } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { PageFrame } from "../../components/shell/RegisterShell";
import { ui } from "../../components/shell/tokens";
import type { CashierSession } from "../auth/session";
import { businessCurrency, businessTax } from "../checkout/currency";
import { Banner, Field, PrimaryButton, QuietButton, control } from "../inventory/ui";
import { terminal } from "../../config/terminal";
import { RetailRequestError, retailCall } from "../../lib/retailClient";
import { inTauri, listLocalExpenses, rememberPettyBalance, saveLocalExpense, type LocalExpenseRow } from "../../lib/tauri";
import { OFFLINE_NOTICE } from "../sync/connectivity";
import { localExpenseLabel } from "./localExpense";
import { prepareBill, type PreparedBill } from "./compressBill";
import {
  centsFromMoney,
  expenseFieldErrors,
  firstExpenseField,
  includedVatCents,
  rateBpsFor,
  type ExpenseField,
} from "./expenseForm";

const paidFromLabels: Record<ExpensePaidFrom, string> = { PETTY_CASH: "Petty cash", BANK: "Bank", CARD: "Card" };

function iso(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function monthStart(): string {
  const now = new Date();
  return iso(new Date(Date.UTC(now.getFullYear(), now.getMonth(), 1)));
}

function problem(caught: unknown, fallback: string): string {
  if (caught instanceof RetailRequestError && caught.offline) return OFFLINE_NOTICE;
  return caught instanceof Error ? caught.message : fallback;
}

function focusField(field: ExpenseField) {
  const node = document.getElementById(`expense-${field}`);
  node?.scrollIntoView({ block: "center" });
  if (node instanceof HTMLElement) node.focus();
}

function kilobytes(bytes: number): string {
  return `${Math.max(1, Math.ceil(bytes / 1024))} KB`;
}

function BillPicker({
  bill,
  invalid,
  onPick,
  onClear,
}: {
  bill: PreparedBill | null;
  invalid: boolean;
  onPick: (file: File) => void;
  onClear: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const take = (file: File | undefined) => {
    if (file) onPick(file);
    if (input.current) input.current.value = "";
  };
  return (
    <div>
      <input
        ref={input}
        className="sr-only"
        type="file"
        accept="image/jpeg,image/png,image/webp"
        onChange={(event) => take(event.target.files?.[0])}
      />
      {bill ? (
        <div className={`flex gap-3 rounded-2xl border bg-white p-3 dark:bg-zinc-900 ${invalid ? "border-red-400" : "border-zinc-200 dark:border-zinc-700"}`}>
          <img src={bill.previewUrl} alt="" className="h-28 w-24 shrink-0 rounded-xl bg-zinc-100 object-cover" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold">{bill.fileName}</p>
            <p className="mt-1 text-xs text-zinc-500">{kilobytes(bill.originalBytes)} compressed to {kilobytes(bill.compressedBytes)}</p>
            <div className="mt-3 flex gap-2">
              <button type="button" className="h-9 rounded-full bg-zinc-900 px-3 text-xs font-semibold text-white" onClick={() => input.current?.click()}>Replace</button>
              <button type="button" id="expense-bill" className="h-9 rounded-full px-3 text-xs font-semibold text-zinc-600 ring-1 ring-zinc-300" onClick={onClear}>Remove</button>
            </div>
          </div>
        </div>
      ) : (
        <button
          id="expense-bill"
          type="button"
          onClick={() => input.current?.click()}
          onDragOver={(event) => {
            event.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={(event) => {
            event.preventDefault();
            setOver(false);
            take(event.dataTransfer.files[0]);
          }}
          className={`flex w-full flex-col items-center gap-2 rounded-2xl border border-dashed px-4 py-7 text-center ${over ? "border-primary-500 bg-primary-50" : "border-zinc-300 bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900"} ${invalid ? "border-red-400" : ""}`}
        >
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-white text-zinc-700 shadow-sm ring-1 ring-zinc-200 dark:bg-zinc-800 dark:text-zinc-200 dark:ring-zinc-700">
            <ImagePlus size={20} aria-hidden="true" />
          </span>
          <span className="text-sm font-semibold">Drop the bill here, or browse</span>
          <span className="text-xs text-zinc-500">JPG, PNG or WebP</span>
        </button>
      )}
    </div>
  );
}

interface StoreRow {
  id: string;
  code: string;
  name: string;
  is_warehouse?: boolean;
}

function localAsExpense(row: LocalExpenseRow): Expense {
  const payload = row.payload;
  const text = (key: string) => (typeof payload[key] === "string" ? String(payload[key]) : "");
  return {
    id: row.id,
    number: localExpenseLabel(row.status),
    store_id: row.storeId,
    store_code: "",
    category: text("category") || "OTHER",
    category_id: text("category_id") || null,
    category_name: text("category") || "Expense",
    description: text("description") || row.detail,
    payee: text("payee"),
    payee_trn: text("payee_trn") || null,
    supplier_id: text("supplier_id") || null,
    supplier_name: "",
    supplier_code: "",
    spent_on: text("spent_on"),
    net_cents: row.totalCents,
    tax_cents: 0,
    recoverable_tax_cents: 0,
    total_cents: row.totalCents,
    currency: businessCurrency(),
    has_tax_invoice: payload.has_tax_invoice === true,
    has_bill: payload.bill != null,
    paid_from: row.paidFrom === "PETTY_CASH" || row.paidFrom === "CARD" ? row.paidFrom : "BANK",
    reference: text("reference"),
    status: "RECORDED",
    created_by_name: null,
    void_reason: row.status === "synced" ? "" : row.detail,
  };
}

export function ExpensesPage({ session }: { session: CashierSession }) {
  const online = session.mode === "online";
  const desktop = inTauri();
  const lockedStore = session.user.store_id || terminal()?.store_id || null;
  const [stores, setStores] = useState<StoreRow[]>([]);
  const [storeId, setStoreId] = useState(lockedStore ?? "");
  const [from, setFrom] = useState(monthStart);
  const [to, setTo] = useState(() => iso(new Date()));
  const [data, setData] = useState<ExpenseList | null>(null);
  const [petty, setPetty] = useState<PettyCash | null>(null);
  const [dialog, setDialog] = useState<"expense" | "topup" | "count" | null>(null);
  const [voiding, setVoiding] = useState<Expense | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [supplierFilter, setSupplierFilter] = useState("");
  const [supplierOptions, setSupplierOptions] = useState<ExpenseSupplier[]>([]);
  const [opened, setOpened] = useState<Expense | null>(null);

  useEffect(() => {
    if (!online) return;
    void retailCall<StoreRow[]>("GET", "/api/v1/stores?limit=200")
      .then((rows) => {
        setStores(rows);
        setStoreId((current) => current || lockedStore || rows.find((store) => !store.is_warehouse)?.id || rows[0]?.id || "");
      })
      .catch((caught: unknown) => setError(problem(caught, "Branches could not be loaded.")));
  }, [lockedStore, online]);

  const load = useCallback(async () => {
    if (storeId === "") return;
    const localRows = desktop ? await listLocalExpenses(storeId).catch(() => []) : [];
    const pending = localRows.filter((row) => row.status !== "synced").map(localAsExpense);
    if (!online) {
      setData(pending.length > 0 ? { items: pending, total_cents: pending.reduce((sum, row) => sum + row.total_cents, 0), recoverable_tax_cents: 0, by_category: [] } : null);
      setError(null);
      return;
    }
    try {
      const [list, float] = await Promise.all([
        retailCall<ExpenseList>(
          "GET",
          `/api/v1/expenses?from=${from}&to=${to}&store_id=${encodeURIComponent(storeId)}${supplierFilter ? `&supplier_id=${encodeURIComponent(supplierFilter)}` : ""}`,
        ),
        retailCall<PettyCash>("GET", `/api/v1/expenses/petty-cash/${storeId}`),
      ]);
      if (desktop) void rememberPettyBalance(storeId, float.balance_cents).catch(() => undefined);
      setData({ ...list, items: [...pending, ...list.items] });
      setPetty(float);
      setError(null);
    } catch (caught) {
      if (desktop && pending.length > 0) {
        setData({ items: pending, total_cents: pending.reduce((sum, row) => sum + row.total_cents, 0), recoverable_tax_cents: 0, by_category: [] });
      }
      setError(problem(caught, "Could not load expenses."));
    }
  }, [desktop, from, online, storeId, supplierFilter, to]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!online) return;
    void retailCall<ExpenseSupplier[]>("GET", "/api/v1/expenses/suppliers").then(setSupplierOptions).catch(() => setSupplierOptions([]));
  }, [online, notice]);

  const displayCurrency = data?.items.find((row) => row.currency)?.currency ?? businessCurrency();
  const show = (cents: number) => formatMoney(cents, displayCurrency);
  const live = data?.items.filter((row) => row.status !== "VOID") ?? [];
  const biggest = Math.max(1, ...(data?.by_category ?? []).map((row) => row.total_cents));
  const branch = stores.find((store) => store.id === storeId);

  const done = (message: string) => {
    setNotice(message);
    setDialog(null);
    setVoiding(null);
    void load();
  };

  return (
    <PageFrame
      title="Expenses"
      sync={online ? { tone: "live", label: "Live", title: "Expenses use the shared ledger." } : { tone: "offline", label: "Offline", title: OFFLINE_NOTICE }}
      drawer={null}
    >
      <div className="space-y-4 p-4">
        {!online && desktop ? <Banner tone="info">{OFFLINE_NOTICE} A saved expense stays Pending Sync or Pending Review until the server accepts it.</Banner> : null}
        {!online && !desktop ? <Banner tone="info">Expenses need a connection in the browser preview. The desktop register can keep a pending expense.</Banner> : null}
        {error ? <Banner tone="error">{error}</Banner> : null}
        {notice ? <Banner tone="ok">{notice}</Banner> : null}
        <div className="grid gap-4 md:grid-cols-3">
          <article className="rounded-2xl bg-zinc-900 p-6 text-white">
            <p className="text-sm text-white/60">Spent in the period</p>
            <p className="mt-4 text-3xl font-semibold tabular-nums">{data ? show(data.total_cents) : "—"}</p>
            <p className="mt-2 text-xs text-white/50">{live.length} expenses, VAT included · {from} to {to}</p>
          </article>
          <article className="rounded-2xl bg-primary-500 p-6 text-white">
            <p className="text-sm text-white/80">Recoverable VAT</p>
            <p className="mt-4 text-3xl font-semibold tabular-nums">{data ? show(data.recoverable_tax_cents) : "—"}</p>
            <p className="mt-2 text-xs text-white/80">Only VAT on a recorded tax invoice, using this business tax setup.</p>
          </article>
          <article className={`rounded-2xl border p-6 ${ui.panel} ${ui.border}`}>
            <div className="flex items-start justify-between">
              <p className={`text-sm ${ui.muted}`}>Petty cash{petty ? ` · ${petty.store_code}` : ""}</p>
              <Wallet size={18} aria-hidden="true" className="text-zinc-400" />
            </div>
            <p className={`mt-4 text-3xl font-semibold tabular-nums ${petty && petty.balance_cents < 0 ? "text-primary-600" : ""}`}>
              {petty ? show(petty.balance_cents) : "—"}
            </p>
            <p className={`mt-1 text-xs ${ui.muted}`}>{branch ? branch.name : "This branch"}</p>
            <div className="mt-2 flex gap-3 text-xs font-semibold">
              <button type="button" className="text-primary-600" disabled={!online} onClick={() => setDialog("topup")}>Top up</button>
              <button type="button" className={ui.muted} disabled={!online} onClick={() => setDialog("count")}>Count float</button>
            </div>
          </article>
        </div>

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
          <section className={`rounded-2xl border p-6 ${ui.panel} ${ui.border}`}>
            <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="text-xl font-semibold">Expenses</h2>
                <p className={`text-sm ${ui.muted}`}>Rent, utilities, fuel and petty spending, each with its VAT.</p>
              </div>
              <div className="flex flex-wrap items-end gap-3">
                {lockedStore ? null : (
                  <label className="text-sm">
                    <span className={`mb-1 block text-xs font-medium ${ui.muted}`}>Branch</span>
                    <select className={`${control} w-52`} value={storeId} onChange={(event) => setStoreId(event.target.value)}>
                      {stores.map((store) => <option key={store.id} value={store.id}>{store.name}</option>)}
                    </select>
                  </label>
                )}
                <label className="text-sm">
                  <span className={`mb-1 block text-xs font-medium ${ui.muted}`}>Supplier</span>
                  <select className={`${control} w-52`} value={supplierFilter} onChange={(event) => setSupplierFilter(event.target.value)}>
                    <option value="">All suppliers</option>
                    {supplierOptions.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
                  </select>
                </label>
                <label className="text-sm">
                  <span className={`mb-1 block text-xs font-medium ${ui.muted}`}>From</span>
                  <input className={`${control} w-44`} type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
                </label>
                <label className="text-sm">
                  <span className={`mb-1 block text-xs font-medium ${ui.muted}`}>To</span>
                  <input className={`${control} w-44`} type="date" value={to} onChange={(event) => setTo(event.target.value)} />
                </label>
                <button type="button" className="inline-flex h-12 items-center gap-2 rounded-xl bg-primary-500 px-4 text-sm font-bold text-white hover:bg-primary-600 disabled:cursor-not-allowed disabled:bg-zinc-200 disabled:text-zinc-500" disabled={(!online && !desktop) || storeId === ""} onClick={() => setDialog("expense")}>
                  <Plus size={16} aria-hidden="true" /> Record expense
                </button>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[40rem] text-left text-sm">
                <thead className={`text-xs uppercase tracking-wide ${ui.muted}`}>
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
                    <tr key={row.id} className={`border-t border-zinc-200 align-top dark:border-zinc-800 ${row.status === "VOID" ? "opacity-50" : ""}`}>
                      <td className="py-3 tabular-nums">{row.spent_on}</td>
                      <td className="py-3">
                        <button type="button" className="block text-left font-medium" onClick={() => setOpened(row)}>{row.description}</button>
                        <span className={`block text-xs ${ui.muted}`}>
                          {row.category_name || row.category}
                          {row.has_bill ? " · bill" : ""}
                          {row.supplier_name ? ` · ${row.supplier_name}` : ""}
                          {row.payee && row.payee !== row.supplier_name ? ` · ${row.payee}` : ""} · <span className="font-mono">{row.number}</span>
                          {row.created_by_name ? ` · ${row.created_by_name}` : ""}
                          {row.status === "VOID" ? ` · void: ${row.void_reason}` : ""}
                        </span>
                      </td>
                      <td className="py-3">{paidFromLabels[row.paid_from]}</td>
                      <td className="py-3 text-right tabular-nums">
                        {show(row.tax_cents)}
                        {row.tax_cents > 0 ? <span className={`block text-[11px] ${ui.muted}`}>{row.recoverable_tax_cents ? "recoverable" : "no tax invoice"}</span> : null}
                      </td>
                      <td className="py-3 text-right font-semibold tabular-nums">{show(row.total_cents)}</td>
                      <td className="py-3 text-right">
                        {row.status === "RECORDED" ? (
                          <button type="button" className="text-xs font-semibold text-zinc-500" onClick={() => setVoiding(row)}>Void</button>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {data && data.items.length === 0 ? <p className={`py-8 text-sm ${ui.muted}`}>No expenses in this period.</p> : null}
            </div>
          </section>

          <div className="space-y-4">
            <article className={`rounded-2xl border p-6 ${ui.panel} ${ui.border}`}>
              <h3 className="font-semibold">By category</h3>
              <ul className="mt-4 space-y-3">
                {(data?.by_category ?? []).map((row) => (
                  <li key={row.category}>
                    <div className="flex items-baseline justify-between text-sm">
                      <span>{row.category_name || row.category} <span className={ui.muted}>({row.count})</span></span>
                      <span className="font-semibold tabular-nums">{show(row.total_cents)}</span>
                    </div>
                    <div className="mt-1 h-1.5 rounded-full bg-zinc-100 dark:bg-zinc-800">
                      <div className="h-1.5 rounded-full bg-primary-500" style={{ width: `${(row.total_cents / biggest) * 100}%` }} />
                    </div>
                  </li>
                ))}
                {data && data.by_category.length === 0 ? <li className={`text-sm ${ui.muted}`}>Nothing spent yet.</li> : null}
              </ul>
            </article>
            <article className="rounded-2xl bg-zinc-900 p-6 text-white">
              <h3 className="font-semibold">Petty cash book</h3>
              <ul className="mt-3 space-y-2">
                {(petty?.entries ?? []).slice(0, 8).map((entry) => (
                  <li key={entry.id} className="flex items-start justify-between gap-3 text-sm">
                    <span className="min-w-0">
                      <span className="block truncate">{entry.note || entry.kind.toLowerCase()}</span>
                      <span className="block text-[11px] text-white/50">
                        {entry.created_at.slice(0, 16).replace("T", " ")}
                        {entry.user_name ? ` · ${entry.user_name}` : ""}
                        {entry.expense_number ? ` · ${entry.expense_number}` : ""}
                      </span>
                    </span>
                    <span className="shrink-0 text-right font-semibold tabular-nums">
                      <span className={entry.amount_cents > 0 ? "text-emerald-300" : ""}>{entry.amount_cents > 0 ? "+" : ""}{show(entry.amount_cents)}</span>
                      <span className="block text-[11px] font-normal text-white/50">{show(entry.balance_after)}</span>
                    </span>
                  </li>
                ))}
                {petty && petty.entries.length === 0 ? <li className="text-sm text-white/60">Top up the float to pay small expenses in cash.</li> : null}
              </ul>
            </article>
          </div>
        </div>
      </div>
      {dialog === "expense" && storeId ? (
        <ExpenseDialog
          storeId={storeId}
          currency={displayCurrency}
          pettyCents={petty?.balance_cents ?? 0}
          canAddSupplier={session.user.permissions.includes(Permission.PayablesManage) || session.user.permissions.includes(Permission.PortalInventoryManage)}
          onClose={() => setDialog(null)}
          offline={desktop && !online}
          onSaved={(row) => done(row.number === "Pending Sync" || row.number === "Pending Review" || row.number === "Failed" ? `${row.number}. ${row.void_reason || "Saved on this register. It is not on the accounting ledger yet."}` : `${row.number} recorded: ${show(row.total_cents)}. It is on the shared expense ledger.`)}
        />
      ) : null}
      {dialog === "topup" || dialog === "count" ? storeId ? (
        <PettyDialog mode={dialog} storeId={storeId} currency={displayCurrency} balance={petty?.balance_cents ?? 0} onClose={() => setDialog(null)} onSaved={done} />
      ) : null : null}
      {voiding ? <VoidDialog expense={voiding} onClose={() => setVoiding(null)} onSaved={() => done(`${voiding.number} voided.`)} /> : null}
      {opened ? <ExpenseDetail expense={opened} currency={displayCurrency} onClose={() => setOpened(null)} /> : null}
    </PageFrame>
  );
}

function ExpenseDialog({
  storeId,
  currency,
  pettyCents,
  canAddSupplier,
  offline,
  onClose,
  onSaved,
}: {
  storeId: string;
  currency: string;
  pettyCents: number;
  canAddSupplier: boolean;
  offline: boolean;
  onClose: () => void;
  onSaved: (expense: Expense) => void;
}) {
  const rate = businessTax().standard_rate_bps;
  const [categoryRows, setCategoryRows] = useState<ExpenseCategoryOption[]>([]);
  const [category, setCategory] = useState("");
  const [categoryQuery, setCategoryQuery] = useState("");
  const [categoryOpen, setCategoryOpen] = useState(false);
  const categoryAnchor = useRef<HTMLDivElement>(null);
  const [description, setDescription] = useState("");
  const [suppliers, setSuppliers] = useState<ExpenseSupplier[]>([]);
  const [supplierId, setSupplierId] = useState("");
  const [supplierQuery, setSupplierQuery] = useState("");
  const [supplierOpen, setSupplierOpen] = useState(false);
  const [payee, setPayee] = useState("");
  const [trn, setTrn] = useState("");
  const [spentOn, setSpentOn] = useState(iso(new Date()));
  const [total, setTotal] = useState("");
  const [taxCategory, setTaxCategory] = useState<TaxCategory>("STANDARD");
  const [invoice, setInvoice] = useState(false);
  const [paidFrom, setPaidFrom] = useState<ExpensePaidFrom | "">(pettyCents > 0 ? "PETTY_CASH" : "BANK");
  const [reference, setReference] = useState("");
  const [bill, setBill] = useState<PreparedBill | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fields, setFields] = useState<Partial<Record<ExpenseField, string>>>({});
  useEffect(() => {
    void retailCall<ExpenseSupplier[]>("GET", "/api/v1/expenses/suppliers")
      .then(setSuppliers)
      .catch(() => setSuppliers([]));
    void retailCall<ExpenseCategoryOption[]>("GET", "/api/v1/expenses/categories")
      .then((rows) => {
        setCategoryRows(rows);
        setCategory((current) => current || rows.find((row) => row.code === "UTILITIES")?.id || rows[0]?.id || "");
      })
      .catch(() => setCategoryRows([]));
  }, []);
  useEffect(() => {
    if (!categoryOpen) return;
    const close = (event: MouseEvent) => {
      if (!categoryAnchor.current?.contains(event.target as Node)) setCategoryOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [categoryOpen]);
  const selectedCategory = categoryRows.find((row) => row.id === category) ?? null;
  const categoryNeedle = categoryQuery.trim().toLowerCase();
  const categoryMatches = categoryRows.filter((row) => categoryNeedle === "" || row.name.toLowerCase().includes(categoryNeedle)).slice(0, 8);
  const selectedSupplier = suppliers.find((row) => row.id === supplierId) ?? null;
  const supplierNeedle = supplierQuery.trim().toLowerCase();
  const supplierMatches = suppliers
    .filter((row) => {
      if (supplierNeedle === "") return true;
      return [row.name, row.code, row.phone ?? "", row.trn ?? ""].some((part) => part.toLowerCase().includes(supplierNeedle));
    })
    .slice(0, 8);
  const chooseSupplier = (supplier: ExpenseSupplier) => {
    setSupplierId(supplier.id);
    setSupplierQuery("");
    setSupplierOpen(false);
    setPayee((current) => (current.trim() === "" || current === selectedSupplier?.name ? supplier.name : current));
    if (supplier.trn) {
      setTrn((current) => (current === "" || current === (selectedSupplier?.trn ?? "") ? supplier.trn ?? "" : current));
    }
  };
  const cents = centsFromMoney(total);
  const vat = cents !== null && cents > 0 ? includedVatCents(cents, rateBpsFor(taxCategory, rate)) : 0;
  const rateLabel = `${(rate / 100).toFixed(rate % 100 === 0 ? 0 : 2)}% VAT included`;
  const invalid = (field: ExpenseField) => (fields[field] ? "border-red-600" : "");

  const save = async () => {
    const next = expenseFieldErrors({
      category,
      spentOn,
      description,
      total,
      taxCategory,
      invoice,
      trn,
      paidFrom,
      standardRateBps: rate,
    });
    setFields(next);
    const first = firstExpenseField(next);
    if (first) {
      setError(next[first] ?? "Check the highlighted field.");
      focusField(first);
      return;
    }
    if (cents === null || paidFrom === "" || category === "") return;
    const body = {
        store_id: storeId,
        category_id: category,
        description: description.trim(),
        supplier_id: supplierId || null,
        payee: payee.trim(),
        payee_trn: trn || null,
        spent_on: spentOn,
        total_cents: cents,
        tax_category: taxCategory,
        has_tax_invoice: invoice,
        paid_from: paidFrom,
        reference: reference.trim(),
        bill: bill
          ? { file_name: bill.fileName, content_type: bill.contentType, data_base64: bill.dataBase64 }
          : null,
    };
    const keepLocal = async () => {
      const saved = await saveLocalExpense({
        storeId,
        payload: body,
        totalCents: cents,
        paidFrom,
        idempotencyKey: `exp-${crypto.randomUUID()}`,
      });
      return localAsExpense(saved);
    };
    setBusy(true);
    setError(null);
    try {
      if (inTauri() && offline) {
        onSaved(await keepLocal());
        return;
      }
      const row = await retailCall<Expense>("POST", "/api/v1/expenses", body);
      onSaved(row);
    } catch (caught) {
      if (inTauri() && caught instanceof RetailRequestError && caught.offline) {
        try {
          onSaved(await keepLocal());
          return;
        } catch (localError) {
          setError(localError instanceof Error ? localError.message : "The expense could not be saved on this register.");
          return;
        }
      }
      const message = problem(caught, "Could not record the expense.");
      setError(message);
      if (caught instanceof RetailRequestError && caught.code === "trn_required") {
        setFields({ trn: message });
        focusField("trn");
      } else if (caught instanceof RetailRequestError && (caught.code === "supplier_invalid" || caught.code === "supplier_inactive")) {
        setFields({ supplier: message });
        focusField("supplier");
      } else if (caught instanceof RetailRequestError && (caught.code === "category_invalid" || caught.code === "category_inactive")) {
        setFields({ category: message });
        focusField("category");
      } else if (caught instanceof RetailRequestError && (caught.code === "unsupported_file" || caught.code === "file_too_large" || caught.code === "image_unreadable" || caught.code === "empty_file")) {
        setFields({ bill: message });
        focusField("bill");
      } else if (caught instanceof RetailRequestError && caught.code === "petty_cash_short") {
        setFields({ paid_from: message });
        focusField("paid_from");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog title="Record an expense" subtitle="Enter what was paid, VAT included. Keep the tax invoice to recover the VAT." onClose={onClose}>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Category" required error={fields.category}>
          <div className="relative" ref={categoryAnchor}>
            <button
              id="expense-category"
              type="button"
              aria-expanded={categoryOpen}
              aria-haspopup="listbox"
              className={`${control} flex items-center justify-between text-left ${invalid("category")}`}
              onClick={() => {
                setCategoryOpen((open) => !open);
                setCategoryQuery("");
              }}
            >
              <span className={selectedCategory ? "" : "text-zinc-400"}>{selectedCategory?.name ?? "Select a category"}</span>
              <ChevronDown size={16} aria-hidden="true" className="text-zinc-400" />
            </button>
            {categoryOpen ? (
              <div className="absolute z-30 mt-1 w-full rounded-xl border border-zinc-200 bg-white p-2 shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
                <input
                  className={control}
                  autoFocus
                  placeholder="Search categories"
                  value={categoryQuery}
                  onChange={(event) => setCategoryQuery(event.target.value)}
                />
                <ul role="listbox" className="mt-2 max-h-48 overflow-y-auto">
                  {categoryMatches.map((row) => (
                    <li key={row.id}>
                      <button
                        type="button"
                        role="option"
                        aria-selected={row.id === category}
                        className={`block w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-zinc-50 dark:hover:bg-zinc-800 ${row.id === category ? "bg-primary-50 font-medium text-primary-700" : ""}`}
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => {
                          setCategory(row.id);
                          setCategoryQuery("");
                          setCategoryOpen(false);
                        }}
                      >
                        {row.name}
                      </button>
                    </li>
                  ))}
                </ul>
                {categoryQuery.trim() !== "" && categoryMatches.length === 0 ? (
                  <button
                    type="button"
                    className="mt-1 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-semibold text-primary-600 hover:bg-primary-50"
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => {
                      const name = categoryQuery.trim();
                      void retailCall<ExpenseCategoryOption>("POST", "/api/v1/expenses/categories", { name }).then((created) => {
                        setCategoryRows((rows) => (rows.some((row) => row.id === created.id) ? rows : [...rows, created]));
                        setCategory(created.id);
                        setCategoryQuery("");
                        setCategoryOpen(false);
                        setFields((current) => ({ ...current, category: undefined }));
                      }).catch((caught: unknown) => {
                        const message = problem(caught, "Could not add the category.");
                        setFields({ category: message });
                        focusField("category");
                      });
                    }}
                  >
                    <Plus size={16} aria-hidden="true" /> Add Expense Type “{categoryQuery.trim()}”
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
        </Field>
        <Field label="Date" required error={fields.spent_on}>
          <input id="expense-spent_on" className={`${control} ${invalid("spent_on")}`} type="date" value={spentOn} onChange={(event) => setSpentOn(event.target.value)} />
        </Field>
      </div>
      <Field label="What for" required error={fields.description}>
        <input id="expense-description" className={`${control} ${invalid("description")}`} maxLength={200} placeholder="DEWA bill, October" value={description} onChange={(event) => setDescription(event.target.value)} />
      </Field>
      <Field label="Supplier" error={fields.supplier} hint={selectedSupplier ? `${selectedSupplier.code}${selectedSupplier.phone ? ` · ${selectedSupplier.phone}` : ""}${selectedSupplier.trn ? ` · TRN ${selectedSupplier.trn}` : ""}` : "Optional. Paid to stays a separate note."}>
        <div className="relative">
          <input
            id="expense-supplier"
            className={`${control} ${invalid("supplier")}`}
            role="combobox"
            aria-expanded={supplierOpen}
            aria-controls="expense-supplier-list"
            placeholder={selectedSupplier ? selectedSupplier.name : "Search name, number, phone, or TRN"}
            value={supplierOpen ? supplierQuery : selectedSupplier?.name ?? supplierQuery}
            onFocus={() => setSupplierOpen(true)}
            onBlur={() => window.setTimeout(() => setSupplierOpen(false), 150)}
            onChange={(event) => {
              setSupplierQuery(event.target.value);
              setSupplierOpen(true);
            }}
          />
          {selectedSupplier && !supplierOpen ? (
            <button type="button" className="absolute right-3 top-1/2 -translate-y-1/2 text-xs font-semibold text-zinc-500" onClick={() => { setSupplierId(""); setSupplierQuery(""); }}>
              Clear
            </button>
          ) : null}
          {supplierOpen ? (
            <ul id="expense-supplier-list" role="listbox" className="absolute z-10 mt-1 max-h-48 w-full overflow-y-auto rounded-xl border border-zinc-200 bg-white shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
              <li>
                <button type="button" className="block w-full px-3 py-2 text-left text-sm text-zinc-500" onClick={() => { setSupplierId(""); setSupplierQuery(""); setSupplierOpen(false); }}>
                  No supplier
                </button>
              </li>
              {supplierMatches.map((row) => (
                <li key={row.id}>
                  <button type="button" role="option" aria-selected={row.id === supplierId} className="block w-full px-3 py-2 text-left text-sm hover:bg-zinc-50 dark:hover:bg-zinc-800" onClick={() => chooseSupplier(row)}>
                    <span className="font-medium">{row.name}</span>
                    <span className="text-zinc-500"> · {row.code}{row.phone ? ` · ${row.phone}` : ""}{row.trn ? ` · ${row.trn}` : ""}</span>
                  </button>
                </li>
              ))}
              {supplierMatches.length === 0 && canAddSupplier ? (
                <li>
                  <button
                    type="button"
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-semibold text-primary-600"
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => {
                      const name = supplierQuery.trim();
                      if (name.length < 2) {
                        setFields({ supplier: "Enter a supplier name." });
                        return;
                      }
                      void retailCall<{ id: string; name: string; code: string; phone: string | null; is_active: boolean }>("POST", "/api/v1/expenses/suppliers", { name }).then((created) => {
                        const row: ExpenseSupplier = { id: created.id, name: created.name, code: created.code, phone: created.phone, trn: null, is_active: created.is_active };
                        setSuppliers((rows) => (rows.some((item) => item.id === row.id) ? rows : [...rows, row]));
                        chooseSupplier(row);
                        setSupplierOpen(false);
                        setFields((current) => ({ ...current, supplier: undefined }));
                      }).catch((caught: unknown) => setError(problem(caught, "Could not add the supplier.")));
                    }}
                  >
                    <Plus size={16} aria-hidden="true" /> {supplierNeedle.length >= 2 ? `Add supplier “${supplierQuery.trim()}”` : "Add supplier"}
                  </button>
                </li>
              ) : null}
              {supplierMatches.length === 0 && !canAddSupplier ? <li className="px-3 py-2 text-sm text-zinc-500">No matching supplier.</li> : null}
            </ul>
          ) : null}
        </div>
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Paid to (optional)">
          <input className={control} maxLength={120} value={payee} onChange={(event) => setPayee(event.target.value)} />
        </Field>
        <Field label="Total paid" required error={fields.total}>
          <input id="expense-total" className={`${control} tabular-nums ${invalid("total")}`} inputMode="decimal" value={total} onChange={(event) => setTotal(event.target.value)} />
        </Field>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="VAT on it">
          <select className={control} value={taxCategory} onChange={(event) => setTaxCategory(event.target.value as TaxCategory)}>
            <option value="STANDARD">{rateLabel}</option>
            <option value="ZERO">Zero-rated</option>
            <option value="EXEMPT">Exempt / no VAT</option>
          </select>
        </Field>
        <p className="self-end rounded-xl bg-zinc-50 px-4 py-3 text-sm tabular-nums dark:bg-zinc-900">VAT {formatMoney(vat, currency)}{businessTax().enforced && invoice && vat > 0 ? " · recoverable" : ""}</p>
      </div>
      {vat > 0 ? (
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1 h-5 w-5" checked={invoice} onChange={(event) => setInvoice(event.target.checked)} />
          <span>I have a tax invoice. Only VAT on a valid tax invoice is recoverable.</span>
        </label>
      ) : null}
      {vat > 0 && invoice ? (
        <Field label="Supplier TRN" required error={fields.trn}>
          <input id="expense-trn" className={`${control} ${invalid("trn")}`} inputMode="numeric" maxLength={15} value={trn} onChange={(event) => setTrn(event.target.value.replace(/\D/g, ""))} />
        </Field>
      ) : null}
      <fieldset>
        <legend className="mb-2 text-sm font-medium">Paid from</legend>
        {fields.paid_from ? <p role="alert" className="mb-2 text-xs font-medium text-red-700">{fields.paid_from}</p> : null}
        <div id="expense-paid_from" className="flex flex-wrap gap-2" tabIndex={-1}>
          {(Object.keys(paidFromLabels) as ExpensePaidFrom[]).map((value) => (
            <button key={value} type="button" aria-pressed={paidFrom === value} className={`h-11 rounded-full px-4 text-sm font-semibold ${paidFrom === value ? "bg-zinc-900 text-white" : "ring-1 ring-zinc-300"}`} onClick={() => setPaidFrom(value)}>
              {value === "PETTY_CASH" ? `Petty cash (${formatMoney(pettyCents, currency)})` : paidFromLabels[value]}
            </button>
          ))}
        </div>
      </fieldset>
      {paidFrom !== "PETTY_CASH" ? (
        <Field label="Reference (optional)">
          <input className={control} maxLength={64} value={reference} onChange={(event) => setReference(event.target.value)} />
        </Field>
      ) : null}
      <Field label="Attach bill / tax invoice" error={fields.bill}>
        <BillPicker
          bill={bill}
          invalid={Boolean(fields.bill)}
          onPick={(file) => {
            void prepareBill(file).then((prepared) => {
              if (bill?.previewUrl) URL.revokeObjectURL(bill.previewUrl);
              setBill(prepared);
              setFields((current) => ({ ...current, bill: undefined }));
            }).catch((caught: unknown) => {
              const message = caught instanceof Error ? caught.message : "The bill image could not be processed. Try another image.";
              setFields({ bill: message });
              focusField("bill");
            });
          }}
          onClear={() => {
            if (bill) URL.revokeObjectURL(bill.previewUrl);
            setBill(null);
          }}
        />
      </Field>
      {error ? <Banner tone="error">{error}</Banner> : null}
      <div className="flex justify-end gap-2">
        <QuietButton onClick={onClose}>Cancel</QuietButton>
        <PrimaryButton disabled={busy} onClick={() => void save()}>{busy ? "Saving…" : "Record expense"}</PrimaryButton>
      </div>
    </Dialog>
  );
}

function PettyDialog({
  mode,
  storeId,
  currency,
  balance,
  onClose,
  onSaved,
}: {
  mode: "topup" | "count";
  storeId: string;
  currency: string;
  balance: number;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const [amount, setAmount] = useState("");
  const [source, setSource] = useState<"till" | "bank">("bank");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const counted = centsFromMoney(amount);
  const difference = counted === null ? null : counted - balance;
  const save = async () => {
    if (counted === null || (mode === "topup" && counted < 1)) {
      setError(mode === "topup" ? "Enter an expense amount greater than zero." : "Enter the cash you counted.");
      focusField("total");
      return;
    }
    if (mode === "count" && note.trim().length < 3) {
      setError("Say why the count differs.");
      focusField("note");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (mode === "topup") {
        await retailCall("POST", "/api/v1/expenses/petty-cash/top-up", { store_id: storeId, amount_cents: counted, source, note: note.trim() });
        onSaved(`Petty cash topped up by ${formatMoney(counted, currency)}.`);
      } else {
        await retailCall("POST", "/api/v1/expenses/petty-cash/count", { store_id: storeId, counted_cents: counted, note: note.trim() });
        onSaved(`Petty cash set to the counted ${formatMoney(counted, currency)}.`);
      }
    } catch (caught) {
      setError(problem(caught, "Could not update petty cash."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog title={mode === "topup" ? "Top up petty cash" : "Count petty cash"} subtitle={`The book says ${formatMoney(balance, currency)}.`} onClose={onClose}>
      <Field label={mode === "topup" ? "Amount added" : "Cash counted"} required error={error && counted === null ? error : undefined}>
        <input id="expense-total" className={`${control} tabular-nums`} inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} />
      </Field>
      {mode === "count" && difference !== null ? (
        <p className="text-sm">Expected {formatMoney(balance, currency)}. Difference {formatMoney(difference, currency)}. Saving posts that difference on the petty cash book.</p>
      ) : null}
      {mode === "topup" ? (
        <fieldset>
          <legend className="mb-2 text-sm font-medium">Taken from</legend>
          <div className="flex gap-2">
            {(["bank", "till"] as const).map((value) => (
              <button key={value} type="button" aria-pressed={source === value} className={`h-11 rounded-full px-4 text-sm font-semibold ${source === value ? "bg-zinc-900 text-white" : "ring-1 ring-zinc-300"}`} onClick={() => setSource(value)}>
                {value === "bank" ? "Bank" : "Till"}
              </button>
            ))}
          </div>
        </fieldset>
      ) : null}
      <Field label={mode === "count" ? "Why it differs" : "Note (optional)"} required={mode === "count"} error={mode === "count" && error && note.trim().length < 3 ? error : undefined}>
        <input id="expense-note" className={control} maxLength={255} value={note} onChange={(event) => setNote(event.target.value)} />
      </Field>
      {error && counted !== null && (mode !== "count" || note.trim().length >= 3) ? <Banner tone="error">{error}</Banner> : null}
      <div className="flex justify-end gap-2">
        <QuietButton onClick={onClose}>Cancel</QuietButton>
        <PrimaryButton disabled={busy} onClick={() => void save()}>{mode === "topup" ? "Top up" : "Save count"}</PrimaryButton>
      </div>
    </Dialog>
  );
}

function VoidDialog({ expense, onClose, onSaved }: { expense: Expense; onClose: () => void; onSaved: () => void }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    if (reason.trim().length < 3) {
      setError("Give a reason.");
      focusField("note");
      return;
    }
    try {
      await retailCall("POST", `/api/v1/expenses/${expense.id}/void`, { reason: reason.trim() });
      onSaved();
    } catch (caught) {
      setError(problem(caught, "Could not void the expense."));
    }
  };
  return (
    <Dialog title={`Void ${expense.number}?`} subtitle={expense.paid_from === "PETTY_CASH" ? "The money goes back into petty cash." : "It drops out of the VAT return."} onClose={onClose}>
      <Field label="Reason" required error={error ?? undefined}>
        <input id="expense-note" className={control} maxLength={255} value={reason} onChange={(event) => setReason(event.target.value)} />
      </Field>
      <div className="flex justify-end gap-2">
        <QuietButton onClick={onClose}>Back</QuietButton>
        <PrimaryButton onClick={() => void save()}>Void expense</PrimaryButton>
      </div>
    </Dialog>
  );
}

function ExpenseDetail({ expense, currency, onClose }: { expense: Expense; currency: string; onClose: () => void }) {
  const [billImage, setBillImage] = useState<string | null>(null);
  const [billError, setBillError] = useState<string | null>(null);
  useEffect(() => {
    if (!expense.has_bill) return;
    void retailCall<ExpenseBill>("GET", `/api/v1/expenses/${expense.id}/bill`)
      .then((row) => setBillImage(`data:${row.content_type};base64,${row.data_base64}`))
      .catch((caught: unknown) => setBillError(problem(caught, "The bill could not be opened.")));
  }, [expense.has_bill, expense.id]);
  return (
    <Dialog title={expense.number} subtitle={`${expense.spent_on} · ${expense.category_name || expense.category}`} onClose={onClose}>
      <p className="text-sm">{expense.description}</p>
      <p className="text-sm text-zinc-500">
        {expense.supplier_name || "No supplier"}
        {expense.payee && expense.payee !== expense.supplier_name ? ` · Paid to ${expense.payee}` : ""}
        {" · "}
        {paidFromLabels[expense.paid_from]}
        {" · "}
        {formatMoney(expense.total_cents, currency)}
        {" · VAT "}
        {formatMoney(expense.tax_cents, currency)}
      </p>
      {billError ? <Banner tone="error">{billError}</Banner> : null}
      {billImage ? <img src={billImage} alt="Bill" className="max-h-80 w-full rounded-xl object-contain" /> : null}
      <div className="flex justify-end"><QuietButton onClick={onClose}>Close</QuietButton></div>
    </Dialog>
  );
}

function Dialog({ title, subtitle, onClose, children }: { title: string; subtitle: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-[#1A191D]/60 p-4" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-label={title} className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-3xl bg-white shadow-xl dark:bg-zinc-950">
        <div className="border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
          <h2 className="text-xl font-semibold">{title}</h2>
          <p className="mt-1 text-sm text-zinc-500">{subtitle}</p>
        </div>
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">{children}</div>
      </div>
    </div>
  );
}
