import {
  BOOK_KIND_LABELS,
  formatMoney,
  type BankAccount,
  type BankLineStatus,
  type BankStatement,
  type BankStatementLine,
  type MatchCandidate,
  type ReconciliationSummary,
  type StatementImport,
} from "@ai-pos/shared-types";
import { FileUp, Landmark, Plus, Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { ErrorNote, FilterSelect, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { Toast } from "../../components/ui/Toast";
import { apiGet, apiPost, apiUpload } from "../../lib/api";
import { useCurrency } from "../../lib/currency";
import { errorMessage } from "../users/api";

type Tab = BankLineStatus | "OUTSTANDING" | "IMPORTS";

const shortDate = (value: string) =>
  new Date(`${value.slice(0, 10)}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

export function BankPage() {
  const { currency } = useCurrency();
  const [accounts, setAccounts] = useState<BankAccount[] | null>(null);
  const [accountId, setAccountId] = useState("");
  const [tab, setTab] = useState<Tab>("UNMATCHED");
  const [summary, setSummary] = useState<ReconciliationSummary | null>(null);
  const [lines, setLines] = useState<BankStatementLine[]>([]);
  const [statements, setStatements] = useState<BankStatement[]>([]);
  const [matching, setMatching] = useState<BankStatementLine | null>(null);
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  const money = (cents: number) => formatMoney(cents, currency);

  const loadAccounts = useCallback(async () => {
    try {
      const rows = await apiGet<BankAccount[]>("/api/v1/bank/accounts");
      setAccounts(rows);
      setAccountId((current) => current || rows.find((row) => row.is_active)?.id || rows[0]?.id || "");
    } catch (caught) {
      setError(errorMessage(caught, "Could not load bank accounts."));
    }
  }, []);

  const load = useCallback(async () => {
    if (!accountId) return;
    try {
      const base = `/api/v1/bank/accounts/${accountId}`;
      const [nextSummary, nextLines, nextStatements] = await Promise.all([
        apiGet<ReconciliationSummary>(`${base}/summary`),
        tab === "UNMATCHED" || tab === "MATCHED" || tab === "IGNORED"
          ? apiGet<BankStatementLine[]>(`${base}/lines?status=${tab}&limit=500`)
          : Promise.resolve([]),
        tab === "IMPORTS" ? apiGet<BankStatement[]>(`${base}/statements`) : Promise.resolve([]),
      ]);
      setSummary(nextSummary);
      setLines(nextLines);
      setStatements(nextStatements);
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load the reconciliation."));
    }
  }, [accountId, tab]);

  useEffect(() => {
    void loadAccounts();
  }, [loadAccounts]);
  useEffect(() => {
    void load();
  }, [load]);

  const refresh = (message: string) => {
    setToast(message);
    setMatching(null);
    void load();
    void loadAccounts();
  };

  const upload = async (file: File) => {
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const result = await apiUpload<StatementImport>(`/api/v1/bank/accounts/${accountId}/statements`, form);
      const { lines_imported: imported, lines_skipped: skipped } = result.statement;
      refresh(
        `${imported} line${imported === 1 ? "" : "s"} imported${skipped ? `, ${skipped} already in` : ""}; ${result.auto_matched} matched automatically.`,
      );
    } catch (caught) {
      setError(errorMessage(caught, "Could not import the statement."));
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const autoMatch = async () => {
    setBusy(true);
    try {
      const result = await apiPost<{ matched: number }>(`/api/v1/bank/accounts/${accountId}/auto-match`, {});
      refresh(result.matched ? `${result.matched} more line${result.matched === 1 ? "" : "s"} matched.` : "Nothing new to match automatically.");
    } catch (caught) {
      setError(errorMessage(caught, "Auto-match failed."));
    } finally {
      setBusy(false);
    }
  };

  const unmatch = async (line: BankStatementLine) => {
    try {
      await apiPost<BankStatementLine>(`/api/v1/bank/lines/${line.id}/unmatch`, {});
      refresh(line.fee_cents ? "Line unmatched; its card fee expense was voided." : "Line moved back to To match.");
    } catch (caught) {
      setError(errorMessage(caught, "Could not unmatch the line."));
    }
  };

  const account = accounts?.find((row) => row.id === accountId);

  if (accounts && accounts.length === 0) {
    return (
      <section className="rounded-card border border-line bg-white p-10 text-center">
        <Landmark size={32} aria-hidden="true" className="mx-auto text-charcoal/30" />
        <h2 className="mt-4 text-xl font-semibold">Reconcile your bank accounts</h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-charcoal/60">
          Add the account, import its statement (CSV or MT940) and card settlements, transfers, cheques, supplier payments and payroll are matched for you.
        </p>
        <PrimaryButton className="mt-6" onClick={() => setAdding(true)}>
          <Plus size={16} aria-hidden="true" className="-ml-1 mr-1.5" /> Add bank account
        </PrimaryButton>
        <ErrorNote message={error} />
        {adding ? <AccountModal onClose={() => setAdding(false)} onSaved={(row) => { setAdding(false); setAccountId(row.id); void loadAccounts(); }} /> : null}
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-4">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">Statement balance</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">
            {summary?.statement_balance_cents != null ? money(summary.statement_balance_cents) : "—"}
          </p>
          <p className="mt-2 text-xs text-white/50">
            {summary?.period_to ? `As of ${shortDate(summary.period_to)}` : "Import a statement to see it"}
          </p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">To match</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{summary ? summary.unmatched : "—"}</p>
          <p className="mt-2 text-xs text-white/80">
            {summary ? `${money(summary.unmatched_in_cents)} in · ${money(summary.unmatched_out_cents)} out` : "Statement lines without a book entry"}
          </p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Matched</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">
            {summary ? `${summary.matched}/${summary.lines - summary.ignored}` : "—"}
          </p>
          <p className="mt-2 text-xs text-charcoal/50">{summary?.ignored ? `${summary.ignored} set aside` : "Statement lines tied to the books"}</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Card fees kept by the bank</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{summary ? money(summary.fees_cents) : "—"}</p>
          <p className="mt-2 text-xs text-charcoal/50">Booked as bank-fee expenses on match</p>
        </article>
      </div>

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <h2 className="text-xl font-semibold">Bank reconciliation</h2>
              <p className="text-sm text-charcoal/60">
                {account ? `${account.bank}${account.iban ? ` · ${account.iban}` : ""}` : "Statement lines against what the books say went through the bank."}
              </p>
            </div>
            {accounts && accounts.length > 1 ? (
              <FilterSelect
                label="Account"
                value={accountId}
                options={accounts.map((row) => ({ value: row.id, label: row.name, hint: row.unmatched_count ? `${row.unmatched_count} to match` : undefined }))}
                onChange={setAccountId}
              />
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            <GhostButton onClick={() => setAdding(true)}>
              <Plus size={15} aria-hidden="true" className="-ml-1 mr-1.5" /> Add account
            </GhostButton>
            <GhostButton disabled={busy || !accountId} onClick={() => void autoMatch()}>
              <Sparkles size={15} aria-hidden="true" className="-ml-1 mr-1.5" /> Auto-match
            </GhostButton>
            <PrimaryButton disabled={busy || !accountId} onClick={() => fileInput.current?.click()}>
              <FileUp size={16} aria-hidden="true" className="-ml-1 mr-1.5" /> {busy ? "Working…" : "Import statement"}
            </PrimaryButton>
            <input
              ref={fileInput}
              type="file"
              accept=".csv,.txt,.sta,.mt940,.940"
              className="hidden"
              aria-label="Statement file"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void upload(file);
              }}
            />
          </div>
        </div>
        <div className="mb-4">
          <SegmentedControl
            label="View"
            value={tab}
            options={[
              { value: "UNMATCHED", label: `To match${summary?.unmatched ? ` (${summary.unmatched})` : ""}` },
              { value: "MATCHED", label: "Matched" },
              { value: "IGNORED", label: "Set aside" },
              { value: "OUTSTANDING", label: `Not on statement${summary?.outstanding.length ? ` (${summary.outstanding.length})` : ""}` },
              { value: "IMPORTS", label: "Imports" },
            ]}
            onChange={setTab}
          />
        </div>
        <ErrorNote message={error} />

        {tab === "UNMATCHED" || tab === "MATCHED" || tab === "IGNORED" ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-charcoal/50">
                <tr>
                  <th className="pb-3 font-medium">Date</th>
                  <th className="pb-3 font-medium">Bank description</th>
                  <th className="pb-3 text-right font-medium">Money in</th>
                  <th className="pb-3 text-right font-medium">Money out</th>
                  <th className="pb-3 pl-6 font-medium">{tab === "MATCHED" ? "Matched to" : tab === "IGNORED" ? "Reason" : ""}</th>
                  <th className="pb-3 text-right font-medium" />
                </tr>
              </thead>
              <tbody>
                {lines.map((line) => (
                  <tr key={line.id} className="border-t border-line align-top">
                    <td className="py-3 tabular-nums">{shortDate(line.booked_on)}</td>
                    <td className="py-3">
                      <span className="block font-medium">{line.description || "—"}</span>
                      {line.reference ? <span className="block font-mono text-xs text-charcoal/50">{line.reference}</span> : null}
                    </td>
                    <td className="py-3 text-right font-semibold tabular-nums">{line.amount_cents > 0 ? money(line.amount_cents) : ""}</td>
                    <td className="py-3 text-right tabular-nums">{line.amount_cents < 0 ? money(-line.amount_cents) : ""}</td>
                    <td className="py-3 pl-6 text-xs">
                      {line.status === "MATCHED" ? (
                        <>
                          <span className="block font-medium text-charcoal">{line.matched_label}</span>
                          <span className="block text-charcoal/50">
                            {line.auto_matched ? "Auto-matched" : "Matched by hand"}
                            {line.fee_cents ? ` · fee ${money(line.fee_cents)}` : ""}
                            {line.match_note ? ` · ${line.match_note}` : ""}
                          </span>
                        </>
                      ) : line.status === "IGNORED" ? (
                        <span className="text-charcoal/60">{line.match_note}</span>
                      ) : null}
                    </td>
                    <td className="py-3 text-right">
                      {line.status === "UNMATCHED" ? (
                        <button
                          type="button"
                          onClick={() => setMatching(line)}
                          className="rounded-full bg-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-accent-hover"
                        >
                          Match
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => void unmatch(line)}
                          className="rounded-full border border-line px-3 py-1.5 text-xs font-semibold hover:border-accent hover:text-accent"
                        >
                          {line.status === "IGNORED" ? "Restore" : "Unmatch"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {lines.length === 0 ? (
              <p className="py-8 text-sm text-charcoal/60">
                {tab === "UNMATCHED" ? (summary?.lines ? "Every statement line is reconciled." : "Import a statement to start.") : "Nothing here yet."}
              </p>
            ) : null}
          </div>
        ) : null}

        {tab === "OUTSTANDING" ? (
          <div className="overflow-x-auto">
            <p className="mb-3 text-sm text-charcoal/60">
              Book entries inside the statement period that no bank line covers yet: settlements still in transit, uncleared cheques, or entries recorded twice.
            </p>
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-charcoal/50">
                <tr>
                  <th className="pb-3 font-medium">Date</th>
                  <th className="pb-3 font-medium">Entry</th>
                  <th className="pb-3 font-medium">Type</th>
                  <th className="pb-3 text-right font-medium">Expected in</th>
                  <th className="pb-3 text-right font-medium">Expected out</th>
                </tr>
              </thead>
              <tbody>
                {summary?.outstanding.map((item) => (
                  <tr key={item.key} className="border-t border-line">
                    <td className="py-3 tabular-nums">{shortDate(item.booked_on)}</td>
                    <td className="py-3">
                      <span className="block font-medium">{item.label}</span>
                      {item.reference ? <span className="block font-mono text-xs text-charcoal/50">{item.reference}</span> : null}
                    </td>
                    <td className="py-3 text-charcoal/70">{BOOK_KIND_LABELS[item.kind]}</td>
                    <td className="py-3 text-right tabular-nums">{item.amount_cents > 0 ? money(item.amount_cents) : ""}</td>
                    <td className="py-3 text-right tabular-nums">{item.amount_cents < 0 ? money(-item.amount_cents) : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {summary && summary.outstanding.length === 0 ? <p className="py-8 text-sm text-charcoal/60">Every book entry in the period is on the statement.</p> : null}
          </div>
        ) : null}

        {tab === "IMPORTS" ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[700px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-charcoal/50">
                <tr>
                  <th className="pb-3 font-medium">File</th>
                  <th className="pb-3 font-medium">Period</th>
                  <th className="pb-3 text-right font-medium">Lines</th>
                  <th className="pb-3 pl-6 font-medium">Imported</th>
                </tr>
              </thead>
              <tbody>
                {statements.map((row) => (
                  <tr key={row.id} className="border-t border-line">
                    <td className="py-3">
                      <span className="block font-medium">{row.file_name}</span>
                      <span className="block text-xs text-charcoal/50">{row.file_format}</span>
                    </td>
                    <td className="py-3 tabular-nums">
                      {row.period_from && row.period_to ? `${shortDate(row.period_from)} – ${shortDate(row.period_to)}` : "—"}
                    </td>
                    <td className="py-3 text-right tabular-nums">
                      {row.lines_imported}
                      {row.lines_skipped ? <span className="block text-xs text-charcoal/50">{row.lines_skipped} duplicates skipped</span> : null}
                    </td>
                    <td className="py-3 pl-6 text-xs text-charcoal/60">
                      {new Date(row.imported_at).toLocaleString()}
                      {row.imported_by_name ? ` · ${row.imported_by_name}` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {statements.length === 0 ? <p className="py-8 text-sm text-charcoal/60">No statements imported yet.</p> : null}
          </div>
        ) : null}
      </div>

      {matching ? <MatchModal line={matching} onClose={() => setMatching(null)} onDone={refresh} /> : null}
      {adding ? (
        <AccountModal
          onClose={() => setAdding(false)}
          onSaved={(row) => {
            setAdding(false);
            setAccountId(row.id);
            refresh(`${row.name} added.`);
          }}
        />
      ) : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}

function AccountModal({ onClose, onSaved }: { onClose: () => void; onSaved: (account: BankAccount) => void }) {
  const [name, setName] = useState("Operating account");
  const [bank, setBank] = useState("");
  const [iban, setIban] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    if (name.trim().length < 2 || bank.trim().length < 2) return setError("Enter the account name and the bank.");
    setBusy(true);
    try {
      onSaved(await apiPost<BankAccount>("/api/v1/bank/accounts", { name: name.trim(), bank: bank.trim(), iban: iban.trim() || null, is_active: true }));
    } catch (caught) {
      setError(errorMessage(caught, "Could not add the account."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      title="Add a bank account"
      subtitle="Card settlements, transfers and supplier payments are matched against this account's statements."
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : "Add account"}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        <TextField label="Account name" value={name} maxLength={80} onChange={(event) => setName(event.target.value)} />
        <TextField label="Bank" placeholder="Emirates NBD" value={bank} maxLength={80} onChange={(event) => setBank(event.target.value)} />
        <TextField label="IBAN (optional)" placeholder="AE07 0331 2345 6789 0123 456" value={iban} maxLength={40} onChange={(event) => setIban(event.target.value)} />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}

function MatchModal({ line, onClose, onDone }: { line: BankStatementLine; onClose: () => void; onDone: (message: string) => void }) {
  const { currency } = useCurrency();
  const [candidates, setCandidates] = useState<MatchCandidate[] | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const money = (cents: number) => formatMoney(Math.abs(cents), currency);

  useEffect(() => {
    apiGet<MatchCandidate[]>(`/api/v1/bank/lines/${line.id}/candidates`)
      .then(setCandidates)
      .catch((caught: unknown) => setError(errorMessage(caught, "Could not load suggestions.")));
  }, [line.id]);

  const match = async (candidate: MatchCandidate) => {
    setBusy(true);
    try {
      await apiPost(`/api/v1/bank/lines/${line.id}/match`, { key: candidate.key, note: note.trim() });
      onDone(candidate.fee_cents ? `Matched; ${money(candidate.fee_cents)} card fee booked as an expense.` : `Matched to ${candidate.label}.`);
    } catch (caught) {
      setError(errorMessage(caught, "Could not match the line."));
      setBusy(false);
    }
  };

  const bookCharge = async () => {
    setBusy(true);
    try {
      await apiPost(`/api/v1/bank/lines/${line.id}/book-charge`, {});
      onDone(`${money(line.amount_cents)} booked as a bank charge expense.`);
    } catch (caught) {
      setError(errorMessage(caught, "Could not book the charge."));
      setBusy(false);
    }
  };

  const ignore = async () => {
    if (note.trim().length < 2) return setError("Say why this line is set aside, e.g. owner's capital or inter-account transfer.");
    setBusy(true);
    try {
      await apiPost(`/api/v1/bank/lines/${line.id}/ignore`, { note: note.trim() });
      onDone("Line set aside.");
    } catch (caught) {
      setError(errorMessage(caught, "Could not set the line aside."));
      setBusy(false);
    }
  };

  return (
    <Modal
      title={`${line.amount_cents > 0 ? "Money in" : "Money out"}: ${money(line.amount_cents)}`}
      subtitle={`${shortDate(line.booked_on)} · ${line.description || line.reference || "No description"}`}
      width="lg"
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Close</GhostButton>
          <GhostButton disabled={busy} onClick={() => void ignore()}>
            Set aside
          </GhostButton>
          {line.amount_cents < 0 ? (
            <PrimaryButton disabled={busy} onClick={() => void bookCharge()}>
              Book as bank charge
            </PrimaryButton>
          ) : null}
        </>
      }
    >
      <div className="space-y-4">
        {candidates === null ? <p className="text-sm text-charcoal/60">Looking for book entries…</p> : null}
        {candidates && candidates.length === 0 ? (
          <p className="rounded-2xl bg-surface px-4 py-3 text-sm text-charcoal/70">
            No book entry of this amount near this date. Record the payment, expense or receipt first
            {line.amount_cents < 0 ? ", book it as a bank charge" : ""}, or set the line aside with a reason.
          </p>
        ) : null}
        {candidates && candidates.length > 0 ? (
          <ul className="divide-y divide-line rounded-2xl border border-line">
            {candidates.map((candidate) => (
              <li key={candidate.key} className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{candidate.label}</p>
                  <p className="text-xs text-charcoal/50">
                    {BOOK_KIND_LABELS[candidate.kind]} · {shortDate(candidate.booked_on)}
                    {candidate.store_code ? ` · ${candidate.store_code}` : ""}
                    {candidate.reference ? ` · ${candidate.reference}` : ""}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <div className="text-right">
                    <p className="text-sm font-semibold tabular-nums">{money(candidate.amount_cents)}</p>
                    {candidate.fee_cents ? <p className="text-xs text-accent tabular-nums">fee {money(candidate.fee_cents)}</p> : null}
                  </div>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void match(candidate)}
                    className="rounded-full bg-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-accent-hover disabled:opacity-50"
                  >
                    Match
                  </button>
                </div>
              </li>
            ))}
          </ul>
        ) : null}
        <TextField label="Note (needed to set aside)" value={note} maxLength={255} onChange={(event) => setNote(event.target.value)} />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
