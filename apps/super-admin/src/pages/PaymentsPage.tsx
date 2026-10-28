import { DataTable, Select, type DataTableColumn } from "@ai-pos/ui";
import { useCallback, useEffect, useMemo, useState } from "react";
import { FilterSearch, FilterSlot, PageHeader } from "../components/PageHeader";
import { ErrorNote, GhostButton, PrimaryButton } from "../components/ui";
import { api, consoleBlob, errorText } from "../lib/api";
import { money, when } from "../lib/format";
import { useSession } from "../lib/session";

interface BankAccount {
  id: string;
  display_name: string;
  bank_name: string;
  holder_name: string;
  account_number: string;
  iban: string;
  swift: string;
  country: string;
  currency: string;
  instructions: string;
  active: boolean;
}

interface TransferRow {
  id: string;
  tenant_name: string;
  tenant_slug: string;
  plan_code: string;
  cycle_code: string;
  invoice_id: string;
  status: "pending_review" | "approved" | "rejected";
  amount_fils: number;
  invoice_total_fils: number;
  currency: string;
  transferred_on: string;
  bank_reference: string;
  created_at: string;
  decision_reason: string | null;
}

const emptyAccount = {
  display_name: "",
  bank_name: "",
  holder_name: "",
  account_number: "",
  iban: "",
  swift: "",
  country: "AE",
  currency: "AED",
  instructions: "",
  active: true,
};

function mask(value: string): string {
  const trimmed = value.trim();
  if (trimmed.length <= 4) return trimmed;
  return `•••• ${trimmed.slice(-4)}`;
}

export function PaymentsPage() {
  const { operator } = useSession();
  const admin = operator?.role === "ADMIN";
  const [accounts, setAccounts] = useState<BankAccount[]>([]);
  const [grace, setGrace] = useState("5");
  const [draft, setDraft] = useState(emptyAccount);
  const [rows, setRows] = useState<TransferRow[]>([]);
  const [status, setStatus] = useState("pending_review");
  const [query, setQuery] = useState("");
  const [reason, setReason] = useState("");
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [decision, setDecision] = useState<"reject" | "reopen" | "revoke">("reject");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    const path = status === "" ? "/billing/transfers" : `/billing/transfers?status=${status}`;
    Promise.all([
      api.get<BankAccount[]>("/billing/bank-accounts"),
      api.get<{ grace_days: number }>("/billing/grace"),
      api.get<TransferRow[]>(path),
    ])
      .then(([foundAccounts, policy, foundTransfers]) => {
        setAccounts(foundAccounts);
        setGrace(String(policy.grace_days));
        setRows(foundTransfers);
        setError(null);
      })
      .catch((caught: unknown) => setError(errorText(caught, "Could not load payments.")))
      .finally(() => setLoading(false));
  }, [status]);

  useEffect(() => {
    load();
  }, [load]);

  const needle = query.trim().toLowerCase();
  const visible = useMemo(
    () =>
      rows.filter((row) => {
        if (needle === "") return true;
        return `${row.tenant_name} ${row.invoice_id} ${row.bank_reference}`.toLowerCase().includes(needle);
      }),
    [needle, rows],
  );

  const saveAccount = async () => {
    try {
      await api.post<BankAccount>("/billing/bank-accounts", draft);
      setDraft(emptyAccount);
      load();
    } catch (caught) {
      setError(errorText(caught, "Could not save the bank account."));
    }
  };

  const saveGrace = async () => {
    const days = Number(grace);
    if (!Number.isInteger(days) || days < 0 || days > 60) {
      setError("Grace period must be a whole number from 0 to 60.");
      return;
    }
    try {
      await api.put<{ grace_days: number }>("/billing/grace", { grace_days: days });
      load();
    } catch (caught) {
      setError(errorText(caught, "Could not save the grace period."));
    }
  };

  const approve = async (row: TransferRow) => {
    const summary = `Verify ${row.tenant_name} (${row.tenant_slug || "store"}), invoice ${row.invoice_id.slice(0, 8)}, ${money(row.invoice_total_fils, row.currency)}, plan ${row.plan_code || "package"} ${row.cycle_code}? This activates the subscription.`;
    if (!window.confirm(summary)) return;
    try {
      await api.post(`/billing/transfers/${row.id}/approve`, {});
      load();
    } catch (caught) {
      setError(errorText(caught, "Could not approve this receipt."));
    }
  };

  const reject = async () => {
    if (rejecting === null) return;
    const path =
      decision === "reopen" ? "reopen" : decision === "revoke" ? "revoke" : "reject";
    try {
      await api.post(`/billing/transfers/${rejecting}/${path}`, { reason });
      setRejecting(null);
      setReason("");
      load();
    } catch (caught) {
      setError(errorText(caught, "Could not save this decision."));
    }
  };

  const openReceipt = async (id: string) => {
    try {
      const blob = await consoleBlob(`/billing/transfers/${id}/receipt`);
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener,noreferrer");
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (caught) {
      setError(errorText(caught, "Could not open the receipt."));
    }
  };

  const columns: DataTableColumn<TransferRow>[] = [
    { id: "store", header: "Store", sortValue: (row) => row.tenant_name, cell: (row) => row.tenant_name },
    {
      id: "invoice",
      header: "Invoice",
      sortValue: (row) => row.invoice_id,
      cell: (row) => <span className="font-mono text-xs">{row.invoice_id.slice(0, 8)}</span>,
    },
    {
      id: "amount",
      header: "Submitted",
      align: "right",
      sortValue: (row) => row.amount_fils,
      cell: (row) => money(row.amount_fils, row.currency),
    },
    {
      id: "due",
      header: "Invoice total",
      align: "right",
      sortValue: (row) => row.invoice_total_fils,
      cell: (row) => money(row.invoice_total_fils, row.currency),
    },
    { id: "when", header: "Transfer date", sortValue: (row) => row.transferred_on, cell: (row) => row.transferred_on },
    { id: "ref", header: "Bank reference", sortValue: (row) => row.bank_reference, cell: (row) => row.bank_reference || "—" },
    { id: "submitted", header: "Submitted", sortValue: (row) => row.created_at, cell: (row) => when(row.created_at) },
    {
      id: "status",
      header: "Status",
      sortValue: (row) => row.status,
      cell: (row) => row.status.replace(/_/g, " "),
    },
    {
      id: "actions",
      header: "",
      cell: (row) => (
        <span className="flex flex-wrap gap-2">
          <GhostButton onClick={() => void openReceipt(row.id)}>Receipt</GhostButton>
          {admin && row.status === "pending_review" ? (
            <>
              <GhostButton onClick={() => void approve(row)}>Verify and activate</GhostButton>
              <GhostButton
                onClick={() => {
                  setDecision("reject");
                  setRejecting(row.id);
                  setReason("");
                }}
              >
                Reject
              </GhostButton>
            </>
          ) : null}
          {admin && row.status === "rejected" ? (
            <GhostButton
              onClick={() => {
                setDecision("reopen");
                setRejecting(row.id);
                setReason("");
              }}
            >
              Reopen
            </GhostButton>
          ) : null}
          {admin && row.status === "approved" ? (
            <GhostButton
              onClick={() => {
                setDecision("revoke");
                setRejecting(row.id);
                setReason("");
              }}
            >
              Revoke activation
            </GhostButton>
          ) : null}
        </span>
      ),
    },
  ];

  return (
    <section>
      <PageHeader
        title="Payments"
        description="A receipt is evidence, not a payment. Approve only after the credit appears on the bank statement. The paid-through date stays inclusive, and the grace period below is counted from the day after it."
      />
      <ErrorNote message={error} />

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <div className="rounded-3xl border border-line bg-white p-5">
          <h2 className="font-semibold">Bank accounts</h2>
          <ul className="mt-3 grid gap-2 text-sm">
            {accounts.map((account) => (
              <li key={account.id}>
                <span className="font-medium">{account.display_name}</span>
                <span className="text-charcoal/60">
                  {" "}
                  · {account.bank_name} · {mask(account.iban || account.account_number)} · {account.currency}
                  {account.active ? "" : " · inactive"}
                </span>
              </li>
            ))}
            {accounts.length === 0 ? <li className="text-charcoal/60">No account is published on invoices yet.</li> : null}
          </ul>
          {admin ? (
            <div className="mt-4 grid gap-2">
              {(
                [
                  ["display_name", "Display name"],
                  ["bank_name", "Bank name"],
                  ["holder_name", "Account holder"],
                  ["iban", "IBAN"],
                  ["account_number", "Account number"],
                  ["swift", "SWIFT"],
                  ["instructions", "Instructions shown on the invoice"],
                ] as const
              ).map(([key, label]) => (
                <label key={key} className="grid gap-1 text-xs text-charcoal/60">
                  {label}
                  <input
                    value={draft[key]}
                    onChange={(event) => setDraft({ ...draft, [key]: event.target.value })}
                    className="h-10 rounded-xl border border-line px-3 text-sm text-charcoal"
                  />
                </label>
              ))}
              <PrimaryButton onClick={() => void saveAccount()}>Publish account</PrimaryButton>
            </div>
          ) : null}
        </div>
        <div className="rounded-3xl border border-line bg-white p-5">
          <h2 className="font-semibold">Grace period</h2>
          <p className="mt-2 text-sm text-charcoal/60">
            After the paid-through date, these extra days stay usable. The next day, protected features stop. Billing and
            receipt upload stay available.
          </p>
          <label className="mt-4 grid max-w-xs gap-1 text-xs text-charcoal/60">
            Days
            <input
              value={grace}
              onChange={(event) => setGrace(event.target.value)}
              inputMode="numeric"
              className="h-10 rounded-xl border border-line px-3 text-sm text-charcoal"
            />
          </label>
          {admin ? (
            <PrimaryButton className="mt-3" onClick={() => void saveGrace()}>
              Save grace period
            </PrimaryButton>
          ) : null}
        </div>
      </div>

      <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <h2 className="text-lg font-semibold">Receipts</h2>
        <div className="flex w-full min-w-0 flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap sm:items-center">
          <FilterSearch
            label="Search receipts"
            value={query}
            onChange={setQuery}
            placeholder="Search store, invoice, or reference"
          />
          <FilterSlot>
            <Select
              aria-label="Receipt status"
              value={status}
              onChange={setStatus}
              options={[
                { value: "pending_review", label: "Pending review" },
                { value: "approved", label: "Approved" },
                { value: "rejected", label: "Rejected" },
                { value: "", label: "All" },
              ]}
            />
          </FilterSlot>
        </div>
      </div>
      <div className="mt-4">
        <DataTable
          aria-label="Transfer receipts"
          minWidth="980px"
          columns={columns}
          data={visible}
          getRowId={(row) => row.id}
          isLoading={loading}
          error={error}
          onRetry={load}
          pagination={{ mode: "client", resetKey: `${needle}:${status}` }}
          emptyState={{ title: "No receipts match", description: "Submitted transfers appear here for review." }}
        />
      </div>
      {rejecting ? (
        <div className="mt-4 max-w-lg rounded-3xl border border-line bg-white p-5">
          <h2 className="font-semibold">
            {decision === "reopen" ? "Reopen this review" : decision === "revoke" ? "Revoke this activation" : "Reject this receipt"}
          </h2>
          <p className="mt-1 text-sm text-charcoal/60">
            {decision === "reopen"
              ? "The receipt returns to the queue. The subscription is not activated."
              : decision === "revoke"
                ? "The payment record stays. Paid features stop until a later verification."
                : "The invoice stays unpaid. The store can send a corrected receipt."}
          </p>
          <textarea
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            className="mt-3 h-24 w-full rounded-xl border border-line px-3 py-2 text-sm"
            placeholder="What was missing on the bank statement?"
          />
          <div className="mt-3 flex gap-2">
            <PrimaryButton onClick={() => void reject()} disabled={reason.trim().length < 3}>
              {decision === "reopen" ? "Reopen review" : decision === "revoke" ? "Revoke activation" : "Reject receipt"}
            </PrimaryButton>
            <GhostButton onClick={() => setRejecting(null)}>Cancel</GhostButton>
          </div>
        </div>
      ) : null}
    </section>
  );
}
