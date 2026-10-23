import { Capability, PAYMENT_TERMS_LABELS, PRICE_TIER_LABELS, formatMoney, type Customer } from "@ai-pos/shared-types";
import { FileSpreadsheet, Plus, Send, SquarePen, Users } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useConfirm } from "../../components/ui/ConfirmDialog";
import { DataTable, type DataTableColumn } from "../../components/ui/DataTable";
import { ErrorNote, PrimaryButton, SearchField } from "../../components/ui/Field";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { Toast } from "../../components/ui/Toast";
import { useCapability } from "../../lib/capabilities";
import { useCurrency } from "../../lib/currency";
import { RiskGradeBadge } from "./CreditRiskCard";
import { CustomerFormModal } from "./CustomerFormModal";
import { customersApi, message } from "./api";

type TypeFilter = "all" | "WHOLESALE" | "RETAIL";

const typeOptions = [
  { value: "all", label: "All" },
  { value: "WHOLESALE", label: "Wholesale" },
  { value: "RETAIL", label: "Retail" },
] as const;

export function CustomersPage() {
  const { currency } = useCurrency();
  const creditModule = useCapability(Capability.B2bCredit);
  const [type, setType] = useState<TypeFilter>("all");
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [inactive, setInactive] = useState(false);
  const [customers, setCustomers] = useState<Customer[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Customer | "new" | null>(null);
  const [prefill, setPrefill] = useState("");
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  const confirm = useConfirm();

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query), 150);
    return () => window.clearTimeout(timer);
  }, [query]);

  const load = useCallback(async () => {
    try {
      setCustomers(
        await customersApi.list({
          q: debounced.trim() || null,
          customer_type: type === "all" ? null : type,
          include_inactive: inactive,
        }),
      );
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load customers."));
    }
  }, [debounced, type, inactive]);

  useEffect(() => {
    void load();
  }, [load]);

  const rows = customers ?? [];
  const stats = useMemo(() => {
    const wholesale = rows.filter((row) => row.customer_type === "WHOLESALE");
    const receivable = wholesale.reduce((sum, row) => sum + Math.max(0, row.current_balance_cents), 0);
    const limit = wholesale.reduce((sum, row) => sum + row.credit_limit_cents, 0);
    const overdue = rows.reduce((sum, row) => sum + row.overdue_cents, 0);
    return {
      receivable,
      overdue,
      overdueAccounts: rows.filter((row) => row.overdue_cents > 0).length,
      wholesale: wholesale.length,
      utilisation: limit > 0 ? Math.round((receivable / limit) * 100) : 0,
    };
  }, [rows]);

  const columns: DataTableColumn<Customer>[] = [
    {
      id: "customer",
      header: "Customer",
      cell: (row) => (
        <>
          <Link to={`/customers/${row.id}`} className="block font-medium hover:text-accent">
            {row.company_name ?? row.name}
          </Link>
          <span className="block text-xs text-charcoal/50">
            {[row.code, row.company_name ? row.name : null, row.phone].filter(Boolean).join(" · ")}
          </span>
        </>
      ),
    },
    {
      id: "tier",
      header: "Type · tier",
      cell: (row) => {
        const wholesale = row.customer_type === "WHOLESALE";
        return (
          <span
            className={`inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
              wholesale ? "bg-charcoal text-white" : "bg-surface text-charcoal/70 ring-1 ring-line"
            }`}
          >
            {wholesale ? PRICE_TIER_LABELS[row.price_tier] : "Retail"}
          </span>
        );
      },
    },
    {
      id: "terms",
      header: "Terms",
      cell: (row) => (row.customer_type === "WHOLESALE" ? PAYMENT_TERMS_LABELS[row.payment_terms] : "—"),
    },
    { id: "trn", header: "TRN", className: "font-mono text-xs", cell: (row) => row.trn_vat_number ?? "—" },
    {
      id: "limit",
      header: "Credit limit",
      align: "right",
      cell: (row) => (row.customer_type === "WHOLESALE" ? formatMoney(row.credit_limit_cents, currency) : "—"),
    },
    {
      id: "balance",
      header: "Balance",
      align: "right",
      className: "font-semibold",
      cell: (row) => formatMoney(row.current_balance_cents, currency),
    },
    {
      id: "available",
      header: "Available",
      align: "right",
      cell: (row) =>
        row.customer_type === "WHOLESALE" ? (
          <span className={row.available_credit_cents < 0 ? "font-semibold text-accent" : ""}>
            {formatMoney(row.available_credit_cents, currency)}
          </span>
        ) : (
          "—"
        ),
    },
    {
      id: "overdue",
      header: "Overdue",
      className: "pl-6",
      cell: (row) =>
        row.overdue_cents > 0 ? (
          <span className="inline-flex rounded-full bg-accent px-2.5 py-0.5 text-[11px] font-semibold tabular-nums text-white">
            {formatMoney(row.overdue_cents, currency)}
          </span>
        ) : row.open_invoice_count > 0 ? (
          <span className="text-xs text-charcoal/60">
            {row.open_invoice_count} open {row.open_invoice_count === 1 ? "invoice" : "invoices"}
          </span>
        ) : (
          <span className="text-xs text-charcoal/40">Clear</span>
        ),
    },
    ...(creditModule
      ? [
          {
            id: "risk",
            header: "Risk",
            align: "center" as const,
            cell: (row: Customer) =>
              row.customer_type === "WHOLESALE" ? <RiskGradeBadge grade={row.risk_grade} score={row.risk_score} /> : "—",
          },
        ]
      : []),
    {
      id: "actions",
      header: "Actions",
      align: "right",
      cell: (row) => (
        <div className="flex items-center justify-end gap-1">
          <Link
            to={`/customers/${row.id}`}
            className="flex h-9 items-center gap-1.5 rounded-full border border-line px-3.5 text-xs font-semibold hover:border-accent hover:text-accent"
          >
            <FileSpreadsheet size={14} aria-hidden="true" />
            Statement
          </Link>
          <button
            type="button"
            aria-label={`Edit ${row.company_name ?? row.name}`}
            title="Edit"
            onClick={() => setEditing(row)}
            className="flex h-9 w-9 items-center justify-center rounded-full border border-line hover:border-accent hover:text-accent"
          >
            <SquarePen size={15} aria-hidden="true" />
          </button>
        </div>
      ),
    },
  ];

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">Receivables on account</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{formatMoney(stats.receivable, currency)}</p>
          <p className="mt-2 text-xs text-white/50">{stats.utilisation}% of extended credit in use</p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">Overdue debt</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{formatMoney(stats.overdue, currency)}</p>
          <p className="mt-2 text-xs text-white/80">
            {stats.overdueAccounts} {stats.overdueAccounts === 1 ? "account is" : "accounts are"} past their terms
          </p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Wholesale accounts</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{stats.wholesale}</p>
          <p className="mt-2 text-xs text-charcoal/50">{rows.length - stats.wholesale} retail profiles listed</p>
        </article>
      </div>

      <div className="overflow-hidden rounded-card border border-line bg-white">
        <div className="flex flex-wrap items-end gap-3 p-6 pb-5">
          <SearchField
            className="min-w-[240px] flex-1"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Company, contact, code, phone, TRN"
          />
          <SegmentedControl label="Customer type" value={type} options={typeOptions} onChange={setType} />
          <button
            type="button"
            aria-pressed={inactive}
            onClick={() => setInactive((value) => !value)}
            className={`h-10 rounded-full border px-5 text-sm font-semibold transition-colors ${
              inactive ? "border-charcoal bg-charcoal text-white" : "border-line bg-white text-charcoal/70 hover:text-charcoal"
            }`}
          >
            Show inactive
          </button>
          <button
            type="button"
            onClick={() => {
              void (async () => {
                const accepted = await confirm({
                  title: "Send statements",
                  message: "Send a statement to every wholesale account with a balance?",
                  confirmLabel: "Send",
                });
                if (!accepted) return;
                try {
                  const result = await customersApi.sendStatements();
                  setToast(`${result.queued} statements queued; ${result.skipped} accounts have no messaging consent.`);
                } catch (caught) {
                  setError(message(caught, "Could not send statements."));
                }
              })();
            }}
            className="inline-flex h-10 items-center gap-2 rounded-full border border-line bg-white px-5 text-sm font-semibold text-charcoal/80 hover:border-accent hover:text-accent"
          >
            <Send size={15} aria-hidden="true" /> Send statements
          </button>
          <PrimaryButton onClick={() => setEditing("new")}>
            <Plus size={16} aria-hidden="true" className="-ml-2 mr-1.5" />
            New customer
          </PrimaryButton>
          {error ? (
            <div className="w-full">
              <ErrorNote message={error} />
            </div>
          ) : null}
        </div>
        <DataTable
          aria-label="Customers"
          variant="flush"
          minWidth="1080px"
          columns={columns}
          data={rows}
          getRowId={(row) => row.id}
          isLoading={customers === null && error === null}
          rowClassName={(row) => (row.is_active ? "" : "opacity-50")}
          emptyState={
            query.trim().length >= 2
              ? {
                  icon: Users,
                  title: `No customer matches "${query.trim()}"`,
                  action: (
                    <button
                      type="button"
                      onClick={() => {
                        setPrefill(query.trim());
                        setEditing("new");
                      }}
                      className="inline-flex items-center gap-1.5 rounded-full bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-hover"
                    >
                      <Plus size={15} aria-hidden="true" /> Add "{query.trim()}" as new customer
                    </button>
                  ),
                }
              : { icon: Users, title: "No customers match these filters" }
          }
          pagination={{ mode: "client", resetKey: [debounced, type, inactive] }}
        />
      </div>

      {editing !== null ? (
        <CustomerFormModal
          customer={editing === "new" ? null : editing}
          currency={currency}
          prefill={editing === "new" ? prefill : ""}
          onClose={() => {
            setEditing(null);
            setPrefill("");
          }}
          onSaved={(saved) => {
            setEditing(null);
            setPrefill("");
            setQuery("");
            setToast(`${saved.company_name ?? saved.name} saved.`);
            void load();
          }}
        />
      ) : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}
