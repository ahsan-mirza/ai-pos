import {
  GL_ACCOUNT_TYPE_LABELS,
  JOURNAL_LABELS,
  formatMoney,
  type AccountLedger,
  type AccountingSettings,
  type BalanceSheet,
  type CorporateTaxEstimate,
  type FinancialStatementSection,
  type GlAccountRow,
  type GlAccountType,
  type IncomeStatement,
  type JournalEntry,
  type PostResult,
  type TrialBalance,
} from "@ai-pos/shared-types";
import { BookOpen, Lock, Plus, RefreshCw, Trash2, Undo2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, FilterSelect, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { Toast } from "../../components/ui/Toast";
import { apiGet, apiPost, apiPut } from "../../lib/api";
import { useCurrency } from "../../lib/currency";
import { toCents } from "../customers/api";
import { errorMessage } from "../users/api";

type Tab = "pnl" | "balance" | "trial" | "journals" | "accounts" | "close";

const today = () => new Date().toISOString().slice(0, 10);
const monthStart = () => `${today().slice(0, 8)}01`;
const shortDate = (value: string) =>
  new Date(`${value.slice(0, 10)}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

export function AccountingPage() {
  const { currency } = useCurrency();
  const money = useCallback((cents: number) => formatMoney(cents, currency), [currency]);
  const [tab, setTab] = useState<Tab>("pnl");
  const [from, setFrom] = useState(monthStart());
  const [to, setTo] = useState(today());
  const [settings, setSettings] = useState<AccountingSettings | null>(null);
  const [sheet, setSheet] = useState<BalanceSheet | null>(null);
  const [ledgerFor, setLedgerFor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);

  const loadOverview = useCallback(async () => {
    try {
      const [nextSettings, nextSheet] = await Promise.all([
        apiGet<AccountingSettings>("/api/v1/accounting/settings"),
        apiGet<BalanceSheet>("/api/v1/accounting/balance-sheet"),
      ]);
      setSettings(nextSettings);
      setSheet(nextSheet);
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load the ledger."));
    }
  }, []);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  const notify = (message: string) => {
    setToast(message);
    void loadOverview();
  };

  const periodPicker = (
    <div className="flex flex-wrap items-end gap-2">
      <TextField label="From" type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
      <TextField label="To" type="date" value={to} onChange={(event) => setTo(event.target.value)} />
    </div>
  );

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-4">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">Total assets</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{sheet ? money(sheet.total_assets_cents) : "—"}</p>
          <p className="mt-2 text-xs text-white/50">{sheet ? (sheet.balanced ? "The books balance" : "The books do not balance") : "Balance sheet today"}</p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">Liabilities</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{sheet ? money(sheet.total_liabilities_cents) : "—"}</p>
          <p className="mt-2 text-xs text-white/80">Suppliers, VAT, deposits, store credit</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Equity</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{sheet ? money(sheet.total_equity_cents) : "—"}</p>
          <p className="mt-2 text-xs text-charcoal/50">Capital, retained and current earnings</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Books locked until</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{settings?.locked_until ? shortDate(settings.locked_until) : "Open"}</p>
          <p className="mt-2 text-xs text-charcoal/50">
            Financial year starts in {settings ? MONTHS[settings.fiscal_year_start_month - 1] : "…"}
          </p>
        </article>
      </div>

      {sheet && sheet.checks.some((check) => check.difference_cents !== 0) ? (
        <div className="rounded-card border border-accent/40 bg-accent/5 p-4 text-sm">
          <p className="font-semibold text-accent">The ledger and a sub-ledger disagree</p>
          <ul className="mt-1 space-y-0.5 text-charcoal/70">
            {sheet.checks
              .filter((check) => check.difference_cents !== 0)
              .map((check) => (
                <li key={check.key}>
                  {check.label}: books {money(check.books_cents)}, sub-ledger {money(check.subledger_cents)} (difference {money(check.difference_cents)})
                </li>
              ))}
          </ul>
          <p className="mt-1 text-xs text-charcoal/50">
            Usual causes: opening stock or customer balances never journaled, or manual customer adjustments. Post a manual journal to align them.
          </p>
        </div>
      ) : null}

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">General ledger</h2>
            <p className="text-sm text-charcoal/60">Every sale, bill, payment, expense and stock movement posts here automatically every 15 minutes.</p>
          </div>
          <SegmentedControl
            label="View"
            value={tab}
            options={[
              { value: "pnl", label: "Profit & loss" },
              { value: "balance", label: "Balance sheet" },
              { value: "trial", label: "Trial balance" },
              { value: "journals", label: "Journals" },
              { value: "accounts", label: "Accounts" },
              { value: "close", label: "Close & tax" },
            ]}
            onChange={setTab}
          />
        </div>
        <ErrorNote message={error} />
        {tab === "pnl" ? <IncomeView from={from} to={to} picker={periodPicker} money={money} onOpen={setLedgerFor} /> : null}
        {tab === "balance" ? <BalanceView money={money} onOpen={setLedgerFor} /> : null}
        {tab === "trial" ? <TrialView from={from} to={to} picker={periodPicker} money={money} onOpen={setLedgerFor} /> : null}
        {tab === "journals" ? <JournalsView money={money} onChanged={notify} /> : null}
        {tab === "accounts" ? <AccountsView money={money} onOpen={setLedgerFor} onChanged={notify} /> : null}
        {tab === "close" && settings ? <CloseView settings={settings} money={money} onChanged={notify} /> : null}
      </div>

      {ledgerFor ? <LedgerModal accountId={ledgerFor} from={from} to={to} money={money} onClose={() => setLedgerFor(null)} /> : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}

type Money = (cents: number) => string;

function Sections({ sections, money, onOpen }: { sections: FinancialStatementSection[]; money: Money; onOpen: (id: string) => void }) {
  return (
    <div className="space-y-5">
      {sections.map((section) => (
        <div key={section.key}>
          <div className="flex items-baseline justify-between border-b border-line pb-2">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-charcoal/60">{section.title}</h3>
            <span className="text-sm font-semibold tabular-nums">{money(section.total_cents)}</span>
          </div>
          {section.rows.length === 0 ? <p className="py-2 text-sm text-charcoal/40">Nothing posted.</p> : null}
          <table className="w-full text-sm">
            <tbody>
              {section.rows.map((row) => (
                <tr
                  key={`${row.code}-${row.name}`}
                  onClick={() => row.account_id && onOpen(row.account_id)}
                  className={`border-b border-line/60 ${row.account_id ? "cursor-pointer hover:bg-surface/60" : ""}`}
                >
                  <td className="w-20 py-2 font-mono text-xs text-charcoal/50">{row.code}</td>
                  <td className="py-2">{row.name}</td>
                  <td className="py-2 text-right tabular-nums">{money(row.amount_cents)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}

function IncomeView({ from, to, picker, money, onOpen }: { from: string; to: string; picker: React.ReactNode; money: Money; onOpen: (id: string) => void }) {
  const [statement, setStatement] = useState<IncomeStatement | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    apiGet<IncomeStatement>(`/api/v1/accounting/income-statement?from=${from}&to=${to}`)
      .then((value) => {
        setStatement(value);
        setError(null);
      })
      .catch((caught: unknown) => setError(errorMessage(caught, "Could not load the statement.")));
  }, [from, to]);
  return (
    <div className="space-y-5">
      {picker}
      <ErrorNote message={error} />
      {statement ? (
        <>
          <div className="grid gap-3 md:grid-cols-3">
            {[
              ["Gross profit", statement.gross_profit_cents],
              ["Operating profit", statement.operating_profit_cents],
              ["Net profit", statement.net_profit_cents],
            ].map(([label, value]) => (
              <div key={label as string} className="rounded-2xl bg-surface px-4 py-3">
                <p className="text-xs text-charcoal/60">{label}</p>
                <p className={`text-lg font-semibold tabular-nums ${(value as number) < 0 ? "text-accent" : ""}`}>{money(value as number)}</p>
              </div>
            ))}
          </div>
          <Sections sections={statement.sections} money={money} onOpen={onOpen} />
        </>
      ) : null}
    </div>
  );
}

function BalanceView({ money, onOpen }: { money: Money; onOpen: (id: string) => void }) {
  const [asOf, setAsOf] = useState(today());
  const [sheet, setSheet] = useState<BalanceSheet | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    apiGet<BalanceSheet>(`/api/v1/accounting/balance-sheet?as_of=${asOf}`)
      .then((value) => {
        setSheet(value);
        setError(null);
      })
      .catch((caught: unknown) => setError(errorMessage(caught, "Could not load the balance sheet.")));
  }, [asOf]);
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <TextField label="As of" type="date" value={asOf} onChange={(event) => setAsOf(event.target.value)} />
        {sheet ? (
          <p className={`rounded-full px-3 py-1 text-xs font-semibold ${sheet.balanced ? "bg-surface" : "bg-accent text-white"}`}>
            Assets {money(sheet.total_assets_cents)} = liabilities {money(sheet.total_liabilities_cents)} + equity {money(sheet.total_equity_cents)}
          </p>
        ) : null}
      </div>
      <ErrorNote message={error} />
      {sheet ? <Sections sections={sheet.sections} money={money} onOpen={onOpen} /> : null}
      {sheet && sheet.checks.length ? (
        <div className="rounded-2xl border border-line p-4">
          <h3 className="mb-2 text-sm font-semibold">Sub-ledger checks</h3>
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-2 text-left font-medium">Check</th>
                <th className="pb-2 text-right font-medium">Books</th>
                <th className="pb-2 text-right font-medium">Sub-ledger</th>
                <th className="pb-2 text-right font-medium">Difference</th>
              </tr>
            </thead>
            <tbody>
              {sheet.checks.map((check) => (
                <tr key={check.key} className="border-t border-line">
                  <td className="py-2">{check.label}</td>
                  <td className="py-2 text-right tabular-nums">{money(check.books_cents)}</td>
                  <td className="py-2 text-right tabular-nums">{money(check.subledger_cents)}</td>
                  <td className={`py-2 text-right font-semibold tabular-nums ${check.difference_cents ? "text-accent" : "text-charcoal/40"}`}>
                    {money(check.difference_cents)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

function TrialView({ from, to, picker, money, onOpen }: { from: string; to: string; picker: React.ReactNode; money: Money; onOpen: (id: string) => void }) {
  const [trial, setTrial] = useState<TrialBalance | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    apiGet<TrialBalance>(`/api/v1/accounting/trial-balance?from=${from}&to=${to}`)
      .then((value) => {
        setTrial(value);
        setError(null);
      })
      .catch((caught: unknown) => setError(errorMessage(caught, "Could not load the trial balance.")));
  }, [from, to]);
  const signed = (cents: number) => (cents === 0 ? "—" : cents > 0 ? `${money(cents)} Dr` : `${money(-cents)} Cr`);
  return (
    <div className="space-y-4">
      {picker}
      <ErrorNote message={error} />
      {trial ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-3 font-medium">Account</th>
                <th className="pb-3 text-right font-medium">Opening</th>
                <th className="pb-3 text-right font-medium">Debits</th>
                <th className="pb-3 text-right font-medium">Credits</th>
                <th className="pb-3 text-right font-medium">Closing</th>
              </tr>
            </thead>
            <tbody>
              {trial.rows.map((row) => (
                <tr key={row.account_id} onClick={() => onOpen(row.account_id)} className="cursor-pointer border-t border-line hover:bg-surface/60">
                  <td className="py-2.5">
                    <span className="mr-2 font-mono text-xs text-charcoal/50">{row.code}</span>
                    {row.name}
                  </td>
                  <td className="py-2.5 text-right tabular-nums text-charcoal/60">{signed(row.opening_cents)}</td>
                  <td className="py-2.5 text-right tabular-nums">{row.debit_cents ? money(row.debit_cents) : ""}</td>
                  <td className="py-2.5 text-right tabular-nums">{row.credit_cents ? money(row.credit_cents) : ""}</td>
                  <td className="py-2.5 text-right font-semibold tabular-nums">{signed(row.closing_cents)}</td>
                </tr>
              ))}
              <tr className="border-t-2 border-charcoal/20 font-semibold">
                <td className="py-3">Totals for the period</td>
                <td />
                <td className="py-3 text-right tabular-nums">{money(trial.total_debit_cents)}</td>
                <td className="py-3 text-right tabular-nums">{money(trial.total_credit_cents)}</td>
                <td className={`py-3 text-right text-xs ${trial.total_debit_cents === trial.total_credit_cents ? "text-charcoal/50" : "text-accent"}`}>
                  {trial.total_debit_cents === trial.total_credit_cents ? "Balanced" : "Out of balance"}
                </td>
              </tr>
            </tbody>
          </table>
          {trial.rows.length === 0 ? <p className="py-8 text-sm text-charcoal/60">Nothing posted in this period.</p> : null}
        </div>
      ) : null}
    </div>
  );
}

function JournalsView({ money, onChanged }: { money: Money; onChanged: (message: string) => void }) {
  const [journal, setJournal] = useState("all");
  const [query, setQuery] = useState("");
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const params = new URLSearchParams({ limit: "100" });
    if (journal !== "all") params.set("journal", journal);
    if (query.trim()) params.set("q", query.trim());
    try {
      setEntries(await apiGet<JournalEntry[]>(`/api/v1/accounting/journals?${params.toString()}`));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load journals."));
    }
  }, [journal, query]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 250);
    return () => window.clearTimeout(timer);
  }, [load]);

  const reverse = async (entry: JournalEntry) => {
    try {
      await apiPost(`/api/v1/accounting/journals/${entry.id}/reverse`, {});
      onChanged(`JV ${entry.number} reversed.`);
      void load();
    } catch (caught) {
      setError(errorMessage(caught, "Could not reverse the entry."));
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap items-end gap-2">
          <FilterSelect
            label="Journal"
            value={journal}
            options={[{ value: "all", label: "All journals" }, ...Object.entries(JOURNAL_LABELS).map(([value, label]) => ({ value, label }))]}
            onChange={setJournal}
          />
          <TextField label="Search" placeholder="Reference or memo" value={query} onChange={(event) => setQuery(event.target.value)} />
        </div>
        <PrimaryButton onClick={() => setCreating(true)}>
          <Plus size={16} aria-hidden="true" className="-ml-1 mr-1.5" /> Manual journal
        </PrimaryButton>
      </div>
      <ErrorNote message={error} />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[820px] text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-charcoal/50">
            <tr>
              <th className="pb-3 font-medium">JV</th>
              <th className="pb-3 font-medium">Date</th>
              <th className="pb-3 font-medium">Journal</th>
              <th className="pb-3 font-medium">Reference</th>
              <th className="pb-3 text-right font-medium">Amount</th>
              <th className="pb-3 text-right font-medium" />
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <JournalRow
                key={entry.id}
                entry={entry}
                money={money}
                open={open === entry.id}
                onToggle={() => setOpen(open === entry.id ? null : entry.id)}
                onReverse={() => void reverse(entry)}
              />
            ))}
          </tbody>
        </table>
        {entries.length === 0 ? <p className="py-8 text-sm text-charcoal/60">No journal entries match.</p> : null}
      </div>
      {creating ? (
        <ManualJournalModal
          onClose={() => setCreating(false)}
          onSaved={(entry) => {
            setCreating(false);
            onChanged(`JV ${entry.number} posted: ${money(entry.total_cents)}.`);
            void load();
          }}
        />
      ) : null}
    </div>
  );
}

function JournalRow({
  entry,
  money,
  open,
  onToggle,
  onReverse,
}: {
  entry: JournalEntry;
  money: Money;
  open: boolean;
  onToggle: () => void;
  onReverse: () => void;
}) {
  return (
    <>
      <tr onClick={onToggle} className={`cursor-pointer border-t border-line hover:bg-surface/60 ${entry.is_active ? "" : "text-charcoal/40"}`}>
        <td className="py-2.5 font-mono text-xs">{entry.number}</td>
        <td className="py-2.5 tabular-nums">
          {shortDate(entry.entry_date)}
          {entry.original_date ? <span className="block text-[11px] text-accent">late, for {shortDate(entry.original_date)}</span> : null}
        </td>
        <td className="py-2.5">{JOURNAL_LABELS[entry.journal] ?? entry.journal}</td>
        <td className="py-2.5">
          <span className="block font-medium">{entry.reference || "—"}</span>
          {entry.memo ? <span className="block text-xs text-charcoal/50">{entry.memo}</span> : null}
        </td>
        <td className="py-2.5 text-right font-semibold tabular-nums">{money(entry.total_cents)}</td>
        <td className="py-2.5 text-right">
          {entry.reversible ? (
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                onReverse();
              }}
              className="inline-flex items-center gap-1 rounded-full border border-line px-3 py-1 text-xs font-semibold hover:border-accent hover:text-accent"
            >
              <Undo2 size={12} aria-hidden="true" /> Reverse
            </button>
          ) : !entry.is_active ? (
            <span className="text-xs">Reversed</span>
          ) : null}
        </td>
      </tr>
      {open ? (
        <tr className="bg-surface/40">
          <td />
          <td colSpan={5} className="pb-3">
            <table className="w-full text-xs">
              <tbody>
                {entry.lines.map((line, index) => (
                  <tr key={index}>
                    <td className={`py-1 ${line.credit_cents ? "pl-6" : ""}`}>
                      <span className="mr-2 font-mono text-charcoal/50">{line.account_code}</span>
                      {line.account_name}
                      {line.memo ? <span className="text-charcoal/50"> · {line.memo}</span> : null}
                    </td>
                    <td className="w-32 py-1 text-right tabular-nums">{line.debit_cents ? money(line.debit_cents) : ""}</td>
                    <td className="w-32 py-1 text-right tabular-nums">{line.credit_cents ? money(line.credit_cents) : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {entry.created_by_name ? <p className="mt-1 text-[11px] text-charcoal/50">By {entry.created_by_name}</p> : null}
          </td>
        </tr>
      ) : null}
    </>
  );
}

interface DraftLine {
  accountId: string;
  debit: string;
  credit: string;
  memo: string;
}

function ManualJournalModal({ onClose, onSaved }: { onClose: () => void; onSaved: (entry: JournalEntry) => void }) {
  const { currency } = useCurrency();
  const [accounts, setAccounts] = useState<GlAccountRow[]>([]);
  const [date, setDate] = useState(today());
  const [reference, setReference] = useState("");
  const [memo, setMemo] = useState("");
  const [lines, setLines] = useState<DraftLine[]>([
    { accountId: "", debit: "", credit: "", memo: "" },
    { accountId: "", debit: "", credit: "", memo: "" },
  ]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<GlAccountRow[]>("/api/v1/accounting/accounts")
      .then((rows) => setAccounts(rows.filter((row) => row.is_active)))
      .catch((caught: unknown) => setError(errorMessage(caught, "Could not load accounts.")));
  }, []);

  const debits = lines.reduce((sum, line) => sum + (toCents(line.debit) ?? 0), 0);
  const credits = lines.reduce((sum, line) => sum + (toCents(line.credit) ?? 0), 0);
  const patch = (index: number, change: Partial<DraftLine>) => setLines(lines.map((line, at) => (at === index ? { ...line, ...change } : line)));

  const save = async () => {
    if (memo.trim().length < 3) return setError("Describe the entry.");
    const parsed = lines
      .filter((line) => line.accountId || line.debit || line.credit)
      .map((line) => ({ account_id: line.accountId, debit_cents: toCents(line.debit) ?? 0, credit_cents: toCents(line.credit) ?? 0, memo: line.memo.trim() }));
    if (parsed.length < 2 || parsed.some((line) => !line.account_id || (line.debit_cents > 0) === (line.credit_cents > 0))) {
      return setError("Each line needs an account and either a debit or a credit.");
    }
    if (debits !== credits) return setError("Debits and credits must be equal.");
    setBusy(true);
    try {
      onSaved(await apiPost<JournalEntry>("/api/v1/accounting/journals", { entry_date: date, reference: reference.trim(), memo: memo.trim(), lines: parsed }));
    } catch (caught) {
      setError(errorMessage(caught, "Could not post the journal."));
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Manual journal"
      subtitle="Opening balances, accruals, depreciation, corrections. Debits must equal credits."
      width="lg"
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy || debits === 0 || debits !== credits} onClick={() => void save()}>
            {busy ? "Posting…" : `Post ${formatMoney(debits, currency)}`}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid gap-4 md:grid-cols-3">
          <TextField label="Date" type="date" value={date} onChange={(event) => setDate(event.target.value)} />
          <TextField label="Reference (optional)" value={reference} maxLength={80} onChange={(event) => setReference(event.target.value)} />
          <TextField label="Description" value={memo} maxLength={255} onChange={(event) => setMemo(event.target.value)} />
        </div>
        <div className="space-y-2">
          {lines.map((line, index) => (
            <div key={index} className="grid grid-cols-[1fr_7rem_7rem_9rem_2rem] items-center gap-2">
              <select
                aria-label="Account"
                value={line.accountId}
                onChange={(event) => patch(index, { accountId: event.target.value })}
                className="rounded-xl bg-surface px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
              >
                <option value="">Choose account…</option>
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.code} · {account.name}
                  </option>
                ))}
              </select>
              <input
                aria-label="Debit"
                inputMode="decimal"
                placeholder="Debit"
                value={line.debit}
                onChange={(event) => patch(index, { debit: event.target.value, credit: event.target.value ? "" : line.credit })}
                className="rounded-xl bg-surface px-3 py-2.5 text-right text-sm tabular-nums focus:outline-none focus:ring-2 focus:ring-accent/40"
              />
              <input
                aria-label="Credit"
                inputMode="decimal"
                placeholder="Credit"
                value={line.credit}
                onChange={(event) => patch(index, { credit: event.target.value, debit: event.target.value ? "" : line.debit })}
                className="rounded-xl bg-surface px-3 py-2.5 text-right text-sm tabular-nums focus:outline-none focus:ring-2 focus:ring-accent/40"
              />
              <input
                aria-label="Line note"
                placeholder="Note"
                value={line.memo}
                onChange={(event) => patch(index, { memo: event.target.value })}
                className="rounded-xl bg-surface px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
              />
              <button
                type="button"
                aria-label="Remove line"
                disabled={lines.length <= 2}
                onClick={() => setLines(lines.filter((_, at) => at !== index))}
                className="rounded-full p-1.5 text-charcoal/40 hover:text-accent disabled:opacity-30"
              >
                <Trash2 size={14} aria-hidden="true" />
              </button>
            </div>
          ))}
          <button type="button" onClick={() => setLines([...lines, { accountId: "", debit: "", credit: "", memo: "" }])} className="text-xs font-semibold text-accent">
            + Add line
          </button>
        </div>
        <p className={`rounded-2xl px-4 py-3 text-sm tabular-nums ${debits === credits ? "bg-surface" : "bg-accent/10 text-accent"}`}>
          Debits {formatMoney(debits, currency)} · Credits {formatMoney(credits, currency)}
          {debits !== credits ? ` · out by ${formatMoney(Math.abs(debits - credits), currency)}` : ""}
        </p>
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}

function AccountsView({ money, onOpen, onChanged }: { money: Money; onOpen: (id: string) => void; onChanged: (message: string) => void }) {
  const [accounts, setAccounts] = useState<GlAccountRow[]>([]);
  const [editing, setEditing] = useState<GlAccountRow | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      setAccounts(await apiGet<GlAccountRow[]>("/api/v1/accounting/accounts"));
    } catch (caught) {
      setError(errorMessage(caught, "Could not load accounts."));
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <PrimaryButton onClick={() => setEditing("new")}>
          <Plus size={16} aria-hidden="true" className="-ml-1 mr-1.5" /> Add account
        </PrimaryButton>
      </div>
      <ErrorNote message={error} />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-charcoal/50">
            <tr>
              <th className="pb-3 font-medium">Code</th>
              <th className="pb-3 font-medium">Account</th>
              <th className="pb-3 font-medium">Type</th>
              <th className="pb-3 text-right font-medium">Balance</th>
              <th className="pb-3 text-right font-medium" />
            </tr>
          </thead>
          <tbody>
            {accounts.map((account) => (
              <tr key={account.id} className={`border-t border-line ${account.is_active ? "" : "text-charcoal/40"}`}>
                <td className="py-2.5 font-mono text-xs">{account.code}</td>
                <td className="py-2.5">
                  {account.name}
                  {account.is_system ? <span className="ml-2 rounded-full bg-surface px-2 py-0.5 text-[10px] font-semibold text-charcoal/60">System</span> : null}
                </td>
                <td className="py-2.5 text-charcoal/70">{GL_ACCOUNT_TYPE_LABELS[account.type]}</td>
                <td className="py-2.5 text-right tabular-nums">{money(account.balance_cents)}</td>
                <td className="py-2.5 text-right">
                  <div className="flex justify-end gap-1">
                    <button type="button" onClick={() => onOpen(account.id)} className="rounded-full border border-line px-3 py-1 text-xs font-semibold hover:border-accent hover:text-accent">
                      <BookOpen size={12} aria-hidden="true" className="mr-1 inline" /> Ledger
                    </button>
                    <button type="button" onClick={() => setEditing(account)} className="rounded-full border border-line px-3 py-1 text-xs font-semibold hover:border-accent hover:text-accent">
                      Edit
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editing ? (
        <AccountModal
          account={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={(row) => {
            setEditing(null);
            onChanged(`${row.code} ${row.name} saved.`);
            void load();
          }}
        />
      ) : null}
    </div>
  );
}

function AccountModal({ account, onClose, onSaved }: { account: GlAccountRow | null; onClose: () => void; onSaved: (row: GlAccountRow) => void }) {
  const [code, setCode] = useState(account?.code ?? "");
  const [name, setName] = useState(account?.name ?? "");
  const [type, setType] = useState<GlAccountType>(account?.type ?? "EXPENSE");
  const [active, setActive] = useState(account?.is_active ?? true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    if (!code.trim() || name.trim().length < 2) return setError("Enter a code and a name.");
    setBusy(true);
    try {
      const body = { code: code.trim(), name: name.trim(), type, is_active: active };
      onSaved(account ? await apiPut<GlAccountRow>(`/api/v1/accounting/accounts/${account.id}`, body) : await apiPost<GlAccountRow>("/api/v1/accounting/accounts", body));
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the account."));
      setBusy(false);
    }
  };
  return (
    <Modal
      title={account ? `Edit ${account.code}` : "Add an account"}
      subtitle={account?.is_system ? "A system account: documents post to it automatically, so only its name can change." : "Use it in manual journals."}
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : "Save account"}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        <div className="grid gap-4 md:grid-cols-[8rem_1fr]">
          <TextField label="Code" value={code} maxLength={16} disabled={account?.is_system} onChange={(event) => setCode(event.target.value)} />
          <TextField label="Name" value={name} maxLength={120} onChange={(event) => setName(event.target.value)} />
        </div>
        {account?.is_system ? null : (
          <>
            <FilterSelect
              label="Type"
              value={type}
              options={(Object.keys(GL_ACCOUNT_TYPE_LABELS) as GlAccountType[]).map((value) => ({ value, label: GL_ACCOUNT_TYPE_LABELS[value] }))}
              onChange={setType}
            />
            {account ? (
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} /> Active
              </label>
            ) : null}
          </>
        )}
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}

function CloseView({ settings, money, onChanged }: { settings: AccountingSettings; money: Money; onChanged: (message: string) => void }) {
  const [startMonth, setStartMonth] = useState(String(settings.fiscal_year_start_month));
  const [lockDate, setLockDate] = useState(settings.locked_until ?? "");
  const [postFrom, setPostFrom] = useState(`${today().slice(0, 4)}-01-01`);
  const [postResult, setPostResult] = useState<PostResult | null>(null);
  const thisYear = Number(today().slice(0, 4));
  const [yearEnd, setYearEnd] = useState(`${thisYear - 1}-12-31`);
  const [taxYear, setTaxYear] = useState(String(thisYear - 1));
  const [addBacks, setAddBacks] = useState("");
  const [deductions, setDeductions] = useState("");
  const [estimate, setEstimate] = useState<CorporateTaxEstimate | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (action: () => Promise<string>) => {
    setBusy(true);
    setError(null);
    try {
      onChanged(await action());
    } catch (caught) {
      setError(errorMessage(caught, "That did not work."));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    const params = new URLSearchParams({ year: taxYear, add_backs_cents: String(toCents(addBacks) ?? 0), deductions_cents: String(toCents(deductions) ?? 0) });
    apiGet<CorporateTaxEstimate>(`/api/v1/accounting/corporate-tax?${params.toString()}`)
      .then(setEstimate)
      .catch((caught: unknown) => setError(errorMessage(caught, "Could not estimate corporate tax.")));
  }, [taxYear, addBacks, deductions, settings]);

  const card = "rounded-2xl border border-line p-5";
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <ErrorNote message={error} />
      <div className={card}>
        <h3 className="font-semibold">Financial year and period lock</h3>
        <p className="mb-4 text-sm text-charcoal/60">Locked days take no new entries; late documents post into the first open day.</p>
        <div className="flex flex-wrap items-end gap-2">
          <FilterSelect label="Year starts in" value={startMonth} options={MONTHS.map((label, index) => ({ value: String(index + 1), label }))} onChange={setStartMonth} />
          <GhostButton disabled={busy} onClick={() => void run(async () => {
            await apiPut("/api/v1/accounting/settings", { fiscal_year_start_month: Number(startMonth), locked_until: settings.locked_until });
            return "Financial year saved.";
          })}>
            Save
          </GhostButton>
        </div>
        <div className="mt-4 flex flex-wrap items-end gap-2">
          <TextField label="Lock up to and including" type="date" value={lockDate} onChange={(event) => setLockDate(event.target.value)} />
          <PrimaryButton disabled={busy || !lockDate} onClick={() => void run(async () => {
            await apiPost("/api/v1/accounting/lock", { locked_until: lockDate });
            return `Books locked up to ${shortDate(lockDate)}.`;
          })}>
            <Lock size={14} aria-hidden="true" className="-ml-1 mr-1.5" /> Lock
          </PrimaryButton>
          {settings.locked_until ? (
            <GhostButton disabled={busy} onClick={() => void run(async () => {
              await apiPost("/api/v1/accounting/lock", { locked_until: null });
              setLockDate("");
              return "Books unlocked.";
            })}>
              Unlock
            </GhostButton>
          ) : null}
        </div>
      </div>

      <div className={card}>
        <h3 className="font-semibold">Post documents</h3>
        <p className="mb-4 text-sm text-charcoal/60">Posting runs every 15 minutes for the last 45 days. Post older history once here; it is safe to repeat.</p>
        <div className="flex flex-wrap items-end gap-2">
          <TextField label="From" type="date" value={postFrom} onChange={(event) => setPostFrom(event.target.value)} />
          <PrimaryButton disabled={busy} onClick={() => void run(async () => {
            const result = await apiPost<PostResult>("/api/v1/accounting/post", { from: postFrom, to: today() });
            setPostResult(result);
            return `${result.posted} posted, ${result.reversed} reversed, ${result.unchanged} already up to date.`;
          })}>
            <RefreshCw size={14} aria-hidden="true" className="-ml-1 mr-1.5" /> Post now
          </PrimaryButton>
        </div>
        {postResult?.unbalanced.length ? (
          <p className="mt-3 text-xs text-accent">{postResult.unbalanced.length} document(s) did not balance and were skipped: {postResult.unbalanced.slice(0, 5).join(", ")}</p>
        ) : null}
      </div>

      <div className={card}>
        <h3 className="font-semibold">Close a year</h3>
        <p className="mb-4 text-sm text-charcoal/60">Moves the year's income and expenses into retained earnings and locks the year.</p>
        <div className="flex flex-wrap items-end gap-2">
          <TextField label="Last day of the year" type="date" value={yearEnd} onChange={(event) => setYearEnd(event.target.value)} />
          <PrimaryButton disabled={busy} onClick={() => void run(async () => {
            const entry = await apiPost<JournalEntry | null>("/api/v1/accounting/close-year", { year_end: yearEnd });
            return entry ? `Year closed with JV ${entry.number}; books locked to ${shortDate(yearEnd)}.` : `Nothing to close; books locked to ${shortDate(yearEnd)}.`;
          })}>
            Close year
          </PrimaryButton>
        </div>
      </div>

      <div className={card}>
        <h3 className="font-semibold">UAE corporate tax estimate</h3>
        <div className="mb-4 mt-3 grid gap-2 md:grid-cols-3">
          <FilterSelect
            label="Financial year"
            value={taxYear}
            options={[thisYear, thisYear - 1, thisYear - 2].map((year) => ({ value: String(year), label: `FY ${year}` }))}
            onChange={setTaxYear}
          />
          <TextField label="Add-backs" inputMode="decimal" placeholder="0.00" value={addBacks} onChange={(event) => setAddBacks(event.target.value)} />
          <TextField label="Exempt income" inputMode="decimal" placeholder="0.00" value={deductions} onChange={(event) => setDeductions(event.target.value)} />
        </div>
        {estimate ? (
          <>
            <table className="w-full text-sm">
              <tbody>
                {[
                  ["Revenue", estimate.revenue_cents],
                  ["Profit before tax", estimate.profit_before_tax_cents],
                  ["Taxable income", estimate.taxable_income_cents],
                  ["0% band", estimate.threshold_cents],
                ].map(([label, value]) => (
                  <tr key={label as string} className="border-t border-line">
                    <td className="py-1.5 text-charcoal/70">{label}</td>
                    <td className="py-1.5 text-right tabular-nums">{money(value as number)}</td>
                  </tr>
                ))}
                <tr className="border-t-2 border-charcoal/20 font-semibold">
                  <td className="py-2">Corporate tax at {estimate.rate_bps / 100}%</td>
                  <td className="py-2 text-right tabular-nums">{money(estimate.tax_cents)}</td>
                </tr>
                <tr>
                  <td className="py-1 text-xs text-charcoal/50">Provision already posted</td>
                  <td className="py-1 text-right text-xs tabular-nums text-charcoal/50">{money(estimate.provision_posted_cents)}</td>
                </tr>
              </tbody>
            </table>
            {estimate.small_business_relief_eligible ? (
              <p className="mt-2 rounded-xl bg-surface px-3 py-2 text-xs">Eligible for small business relief: revenue is within AED 3m.</p>
            ) : null}
            <ul className="mt-2 list-disc space-y-0.5 pl-4 text-[11px] text-charcoal/50">
              {estimate.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
            {estimate.tax_cents > estimate.provision_posted_cents ? (
              <PrimaryButton
                className="mt-3"
                disabled={busy}
                onClick={() => void run(async () => {
                  const amount = estimate.tax_cents - estimate.provision_posted_cents;
                  await apiPost("/api/v1/accounting/corporate-tax/provision", { fiscal_year: estimate.fiscal_year, amount_cents: amount });
                  setTaxYear(String(estimate.fiscal_year));
                  return `Corporate tax provision of ${money(amount)} posted.`;
                })}
              >
                Post provision of {money(estimate.tax_cents - estimate.provision_posted_cents)}
              </PrimaryButton>
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  );
}

function LedgerModal({ accountId, from, to, money, onClose }: { accountId: string; from: string; to: string; money: Money; onClose: () => void }) {
  const [start, setStart] = useState(from);
  const [end, setEnd] = useState(to);
  const [ledger, setLedger] = useState<AccountLedger | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    apiGet<AccountLedger>(`/api/v1/accounting/accounts/${accountId}/ledger?from=${start}&to=${end}`)
      .then(setLedger)
      .catch((caught: unknown) => setError(errorMessage(caught, "Could not load the ledger.")));
  }, [accountId, start, end]);
  return (
    <Modal
      title={ledger ? `${ledger.account.code} · ${ledger.account.name}` : "Account ledger"}
      subtitle={ledger ? `Opening ${money(ledger.opening_cents)} · closing ${money(ledger.closing_cents)}` : undefined}
      width="lg"
      onClose={onClose}
      footer={<GhostButton onClick={onClose}>Close</GhostButton>}
    >
      <div className="mb-3 flex gap-2">
        <TextField label="From" type="date" value={start} onChange={(event) => setStart(event.target.value)} />
        <TextField label="To" type="date" value={end} onChange={(event) => setEnd(event.target.value)} />
      </div>
      <ErrorNote message={error} />
      {ledger ? (
        <div className="max-h-[50vh] overflow-y-auto">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-white uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-2 font-medium">Date</th>
                <th className="pb-2 font-medium">Entry</th>
                <th className="pb-2 text-right font-medium">Debit</th>
                <th className="pb-2 text-right font-medium">Credit</th>
                <th className="pb-2 text-right font-medium">Balance</th>
              </tr>
            </thead>
            <tbody>
              {ledger.rows.map((row, index) => (
                <tr key={`${row.entry_id}-${index}`} className="border-t border-line">
                  <td className="py-1.5 tabular-nums">{shortDate(row.entry_date)}</td>
                  <td className="py-1.5">
                    <span className="font-mono text-charcoal/50">JV {row.number}</span> {JOURNAL_LABELS[row.journal] ?? row.journal} · {row.reference}
                    {row.memo ? <span className="block text-charcoal/50">{row.memo}</span> : null}
                  </td>
                  <td className="py-1.5 text-right tabular-nums">{row.debit_cents ? money(row.debit_cents) : ""}</td>
                  <td className="py-1.5 text-right tabular-nums">{row.credit_cents ? money(row.credit_cents) : ""}</td>
                  <td className="py-1.5 text-right font-semibold tabular-nums">{money(row.balance_cents)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {ledger.rows.length === 0 ? <p className="py-6 text-center text-sm text-charcoal/60">No postings in this period.</p> : null}
          {ledger.truncated ? <p className="py-2 text-xs text-charcoal/50">Showing the first 1,000 lines; narrow the dates to see the rest.</p> : null}
        </div>
      ) : null}
    </Modal>
  );
}
