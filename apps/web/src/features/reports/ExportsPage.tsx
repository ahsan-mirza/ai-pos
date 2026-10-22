import { Permission } from "@ai-pos/shared-types";
import { FileCode2, FileSpreadsheet, Gift, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, PrimaryButton, TextField } from "../../components/ui/Field";
import { Toast } from "../../components/ui/Toast";
import { Toggle } from "../../components/ui/Toggle";
import { apiBlob, apiGet, apiPut } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { errorMessage } from "../users/api";

interface LoyaltyTier {
  name: string;
  min_spend_cents: number;
  multiplier_pct: number;
}

interface LoyaltyRules {
  enabled: boolean;
  earn_per_unit: number;
  redeem_cents: number;
  min_redeem: number;
  expiry_months: number;
  tiers: LoyaltyTier[];
}

interface GlAccount {
  key: string;
  use: string;
  code: string;
  name: string;
  default_code: string;
  default_name: string;
}

const iso = (value: Date) => value.toISOString().slice(0, 10);

function AccountMapping({ canEdit, onSaved }: { canEdit: boolean; onSaved: () => void }) {
  const [accounts, setAccounts] = useState<GlAccount[] | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void apiGet<GlAccount[]>("/api/v1/exports/accounts")
      .then(setAccounts)
      .catch(() => setAccounts(null));
  }, []);

  if (accounts === null) return null;
  const customised = accounts.filter((row) => row.code !== row.default_code || row.name !== row.default_name).length;
  const edit = (key: string, field: "code" | "name", value: string) =>
    setAccounts(accounts.map((row) => (row.key === key ? { ...row, [field]: value } : row)));

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      setAccounts(
        await apiPut<GlAccount[]>("/api/v1/exports/accounts", {
          accounts: Object.fromEntries(accounts.map((row) => [row.key, { code: row.code.trim(), name: row.name.trim() }])),
        }),
      );
      onSaved();
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the account codes."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-card border border-line bg-white p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">Chart of accounts</h2>
          <p className="text-sm text-charcoal/60">
            Match the journal to your accounting system's codes.{" "}
            {customised ? `${customised} account${customised === 1 ? "" : "s"} customised.` : "Using the built-in codes."}
          </p>
        </div>
        <button type="button" onClick={() => setOpen(!open)} className="text-sm font-semibold text-accent">
          {open ? "Hide accounts" : "Show accounts"}
        </button>
      </div>
      {open ? (
        <>
          <div className="mt-5 overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-charcoal/50">
                <tr>
                  <th className="pb-3 font-medium">Used for</th>
                  <th className="w-36 pb-3 font-medium">Code</th>
                  <th className="pb-3 font-medium">Account name</th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((row) => {
                  const changed = row.code !== row.default_code || row.name !== row.default_name;
                  return (
                    <tr key={row.key} className="border-t border-line">
                      <td className="py-2 pr-4">
                        <span className="block">{row.use}</span>
                        {changed ? (
                          <span className="block text-xs text-charcoal/50 tabular-nums">
                            Default {row.default_code} · {row.default_name}
                          </span>
                        ) : null}
                      </td>
                      <td className="py-2 pr-2">
                        <input
                          aria-label={`${row.use} account code`}
                          value={row.code}
                          maxLength={20}
                          disabled={!canEdit}
                          onChange={(event) => edit(row.key, "code", event.target.value)}
                          className={`w-full rounded-xl px-3 py-2 font-mono text-sm tabular-nums focus:outline-none focus:ring-2 focus:ring-accent/40 ${
                            changed ? "bg-accent/5 ring-1 ring-accent/30" : "bg-surface"
                          }`}
                        />
                      </td>
                      <td className="py-2">
                        <input
                          aria-label={`${row.use} account name`}
                          value={row.name}
                          maxLength={80}
                          disabled={!canEdit}
                          onChange={(event) => edit(row.key, "name", event.target.value)}
                          className="w-full rounded-xl bg-surface px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <ErrorNote message={error} />
          {canEdit ? (
            <div className="mt-4 flex justify-end">
              <PrimaryButton disabled={busy} onClick={() => void save()}>
                {busy ? "Saving…" : "Save account codes"}
              </PrimaryButton>
            </div>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function monthStart(): string {
  const now = new Date();
  return iso(new Date(Date.UTC(now.getFullYear(), now.getMonth(), 1)));
}

export function ExportsPage() {
  const { can } = useAuth();
  const [from, setFrom] = useState(monthStart());
  const [to, setTo] = useState(iso(new Date()));
  const [rules, setRules] = useState<LoyaltyRules | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  const manageLoyalty = can(Permission.SettingsManage);

  useEffect(() => {
    void apiGet<LoyaltyRules>("/api/v1/loyalty/settings")
      .then(setRules)
      .catch(() => setRules(null));
  }, []);

  const download = async (path: string, name: string) => {
    try {
      const blob = await apiBlob(`${path}?from=${from}&to=${to}`);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = name;
      link.click();
      URL.revokeObjectURL(url);
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not build the export."));
    }
  };

  const saveRules = async () => {
    if (!rules) return;
    try {
      setRules(await apiPut<LoyaltyRules>("/api/v1/loyalty/settings", rules));
      setToast("Loyalty programme saved. Registers apply it on their next sale.");
    } catch (caught) {
      setError(errorMessage(caught, "Could not save the loyalty programme."));
    }
  };

  return (
    <section className="space-y-4">
      <ErrorNote message={error} />
      <div className="rounded-card border border-line bg-white p-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold">Accounting exports</h2>
            <p className="text-sm text-charcoal/60">Hand these to your accountant or import them into your ledger and e-invoicing provider.</p>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <TextField label="From" type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
            <TextField label="To" type="date" value={to} onChange={(event) => setTo(event.target.value)} />
          </div>
        </div>
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <article className="rounded-2xl bg-charcoal p-6 text-white">
            <FileSpreadsheet size={22} aria-hidden="true" className="text-accent" />
            <h3 className="mt-3 text-lg font-semibold">General ledger journal</h3>
            <p className="mt-1 text-sm text-white/60">
              Balanced debits and credits for sales, VAT, cost of goods, returns and account receipts, one line per account.
            </p>
            <button
              type="button"
              onClick={() => void download("/api/v1/exports/gl.csv", `journal-${from}-${to}.csv`)}
              className="mt-5 h-11 rounded-full bg-accent px-5 text-sm font-semibold"
            >
              Download CSV
            </button>
          </article>
          <article className="rounded-2xl border border-line p-6">
            <FileCode2 size={22} aria-hidden="true" className="text-accent" />
            <h3 className="mt-3 text-lg font-semibold">PINT AE e-invoices</h3>
            <p className="mt-1 text-sm text-charcoal/60">
              One UBL 2.1 XML per tax invoice in the PINT AE profile, zipped, for your accredited e-invoicing provider.
            </p>
            <button
              type="button"
              onClick={() => void download("/api/v1/exports/einvoices.zip", `pint-ae-${from}-${to}.zip`)}
              className="mt-5 h-11 rounded-full bg-charcoal px-5 text-sm font-semibold text-white"
            >
              Download ZIP
            </button>
          </article>
        </div>
      </div>

      <AccountMapping canEdit={manageLoyalty} onSaved={() => setToast("Account codes saved; the next journal export uses them.")} />

      {rules ? (
        <div className="rounded-card border border-line bg-white p-6">
          <div className="flex items-start gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-charcoal text-white">
              <Gift size={18} aria-hidden="true" />
            </span>
            <div className="min-w-0 flex-1">
              <h2 className="text-xl font-semibold">Loyalty programme</h2>
              <p className="text-sm text-charcoal/60">
                Customers earn on what they pay (not on credit or points) and spend points at the register.
              </p>
            </div>
          </div>
          <div className="mt-5 grid gap-4 md:grid-cols-4">
            <Toggle
              label="Programme on"
              checked={rules.enabled}
              onChange={(enabled) => setRules({ ...rules, enabled })}
              disabled={!manageLoyalty}
            />
            <TextField
              label="Points per currency unit"
              type="number"
              min={0}
              value={rules.earn_per_unit}
              disabled={!manageLoyalty}
              onChange={(event) => setRules({ ...rules, earn_per_unit: Number(event.target.value) || 0 })}
            />
            <TextField
              label="Point value (minor units)"
              type="number"
              min={1}
              value={rules.redeem_cents}
              disabled={!manageLoyalty}
              onChange={(event) => setRules({ ...rules, redeem_cents: Math.max(1, Number(event.target.value) || 1) })}
            />
            <TextField
              label="Minimum to redeem"
              type="number"
              min={1}
              value={rules.min_redeem}
              disabled={!manageLoyalty}
              onChange={(event) => setRules({ ...rules, min_redeem: Math.max(1, Number(event.target.value) || 1) })}
            />
          </div>
          <p className="mt-3 text-xs text-charcoal/60 tabular-nums">
            A 100.00 purchase earns {rules.earn_per_unit * 100} points, worth {((rules.earn_per_unit * 100 * rules.redeem_cents) / 100).toFixed(2)}{" "}
            back.
          </p>

          <div className="mt-6 grid gap-4 md:grid-cols-[minmax(0,14rem)_1fr]">
            <TextField
              label="Points expire after (months)"
              type="number"
              min={0}
              max={120}
              value={rules.expiry_months}
              disabled={!manageLoyalty}
              hint={rules.expiry_months > 0 ? "Oldest points lapse first; customers are shown what expires within 30 days." : "0 keeps points forever."}
              onChange={(event) => setRules({ ...rules, expiry_months: Math.min(120, Math.max(0, Number(event.target.value) || 0)) })}
            />
            <div>
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">Tiers</span>
                {manageLoyalty && rules.tiers.length < 6 ? (
                  <button
                    type="button"
                    onClick={() => {
                      const last = rules.tiers[rules.tiers.length - 1];
                      setRules({
                        ...rules,
                        tiers: [
                          ...rules.tiers,
                          {
                            name: ["Silver", "Gold", "Platinum", "Diamond", "Elite", "Icon"][rules.tiers.length] ?? "Tier",
                            min_spend_cents: (last?.min_spend_cents ?? 0) + 500_000,
                            multiplier_pct: (last?.multiplier_pct ?? 100) + 25,
                          },
                        ],
                      });
                    }}
                    className="text-xs font-semibold text-accent"
                  >
                    + Add tier
                  </button>
                ) : null}
              </div>
              {rules.tiers.length === 0 ? (
                <p className="mt-1.5 rounded-xl bg-surface px-4 py-3 text-xs text-charcoal/60">
                  Everyone earns the base rate. Add tiers to reward customers who spend more over 12 months.
                </p>
              ) : (
                <div className="mt-1.5 space-y-2">
                  {rules.tiers.map((tier, index) => (
                    <div key={index} className="grid grid-cols-[1fr_9rem_7rem_2rem] items-center gap-2">
                      <input
                        aria-label="Tier name"
                        value={tier.name}
                        maxLength={40}
                        disabled={!manageLoyalty}
                        onChange={(event) =>
                          setRules({ ...rules, tiers: rules.tiers.map((row, at) => (at === index ? { ...row, name: event.target.value } : row)) })
                        }
                        className="rounded-xl bg-surface px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
                      />
                      <label className="flex items-center gap-1.5 rounded-xl bg-surface px-3 py-2 text-xs text-charcoal/60">
                        from
                        <input
                          aria-label={`${tier.name} 12-month spend`}
                          inputMode="decimal"
                          value={tier.min_spend_cents / 100}
                          disabled={!manageLoyalty}
                          onChange={(event) =>
                            setRules({
                              ...rules,
                              tiers: rules.tiers.map((row, at) =>
                                at === index ? { ...row, min_spend_cents: Math.round((Number(event.target.value) || 0) * 100) } : row,
                              ),
                            })
                          }
                          className="w-full bg-transparent text-right text-sm font-semibold tabular-nums text-charcoal focus:outline-none"
                        />
                      </label>
                      <label className="flex items-center gap-1 rounded-xl bg-surface px-3 py-2 text-xs text-charcoal/60">
                        <input
                          aria-label={`${tier.name} earn rate percent`}
                          inputMode="numeric"
                          value={tier.multiplier_pct}
                          disabled={!manageLoyalty}
                          onChange={(event) =>
                            setRules({
                              ...rules,
                              tiers: rules.tiers.map((row, at) =>
                                at === index ? { ...row, multiplier_pct: Number(event.target.value) || 100 } : row,
                              ),
                            })
                          }
                          className="w-full bg-transparent text-right text-sm font-semibold tabular-nums text-charcoal focus:outline-none"
                        />
                        %
                      </label>
                      {manageLoyalty ? (
                        <button
                          type="button"
                          aria-label={`Remove ${tier.name}`}
                          onClick={() => setRules({ ...rules, tiers: rules.tiers.filter((_, at) => at !== index) })}
                          className="flex h-8 w-8 items-center justify-center rounded-full text-charcoal/50 hover:bg-surface hover:text-accent"
                        >
                          <Trash2 size={14} aria-hidden="true" />
                        </button>
                      ) : null}
                    </div>
                  ))}
                  <p className="text-xs text-charcoal/50">Spend is what the customer paid in the last 12 months, less refunds. 150% earns one and a half times the points.</p>
                </div>
              )}
            </div>
          </div>
          {manageLoyalty ? (
            <div className="mt-4 flex justify-end">
              <PrimaryButton onClick={() => void saveRules()}>Save programme</PrimaryButton>
            </div>
          ) : null}
        </div>
      ) : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}
