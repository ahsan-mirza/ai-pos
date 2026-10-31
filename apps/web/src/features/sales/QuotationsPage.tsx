import { Capability, Permission, formatMoney, type Quote, type QuoteList, type QuoteStatus } from "@ai-pos/shared-types";
import { ArrowRightLeft, Ban, Banknote, FileDown, FileText, Truck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useConfirm } from "../../components/ui/ConfirmDialog";
import { DataTable, usePagination, type DataTableColumn } from "../../components/ui/DataTable";
import { ErrorNote } from "../../components/ui/Field";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { Toast } from "../../components/ui/Toast";
import { actionHoverClass, type ActionIntent } from "@ai-pos/ui";
import { useAuth } from "../../lib/auth";
import { useCapability } from "../../lib/capabilities";
import { useCurrency } from "../../lib/currency";
import { message, shortDate } from "../customers/api";
import { salesOrdersApi } from "../salesOrders/api";
import { ConvertQuoteModal } from "./ConvertQuoteModal";
import { TakeDepositModal } from "./TakeDepositModal";
import { quotesApi } from "./api";

type StatusFilter = "all" | QuoteStatus;

const statusOptions = [
  { value: "OPEN", label: "Open" },
  { value: "CONVERTED", label: "Converted" },
  { value: "EXPIRED", label: "Expired" },
  { value: "CANCELLED", label: "Cancelled" },
  { value: "all", label: "All" },
] as const;

const HOUR = 3_600_000;

function expiryLabel(quote: Quote): { text: string; urgent: boolean } {
  if (quote.quote_expiry_date === null) return { text: "—", urgent: false };
  const hours = (new Date(quote.quote_expiry_date).getTime() - Date.now()) / HOUR;
  if (quote.quote_status !== "OPEN") return { text: shortDate(quote.quote_expiry_date), urgent: false };
  if (hours <= 0) return { text: "Expiring now", urgent: true };
  if (hours < 48) return { text: `${Math.max(1, Math.round(hours))}h left`, urgent: true };
  return { text: `${Math.round(hours / 24)} days left`, urgent: false };
}

function StatusChip({ status }: { status: QuoteStatus | null }) {
  const styles: Record<QuoteStatus, string> = {
    OPEN: "bg-accent text-white",
    CONVERTED: "bg-charcoal text-white",
    EXPIRED: "bg-surface text-charcoal/50 ring-1 ring-line",
    CANCELLED: "bg-surface text-charcoal/50 ring-1 ring-line",
  };
  if (status === null) return null;
  return (
    <span className={`inline-flex whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11px] font-semibold capitalize ${styles[status]}`}>
      {status.toLowerCase()}
    </span>
  );
}

export function QuotationsPage() {
  const { can } = useAuth();
  const { currency } = useCurrency();
  const [status, setStatus] = useState<StatusFilter>("OPEN");
  const pager = usePagination({ resetKeys: [status] });
  const [data, setData] = useState<QuoteList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [converting, setConverting] = useState<Quote | null>(null);
  const [depositFor, setDepositFor] = useState<Quote | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);
  const manage = can(Permission.CustomersManage);
  const ordersOn = useCapability(Capability.SalesOrders) && can(Permission.SalesOrders);
  const navigate = useNavigate();
  const confirm = useConfirm();

  const toOrder = async (quote: Quote) => {
    setBusyId(quote.id);
    try {
      const order = await salesOrdersApi.fromQuote(quote.id);
      setToast(`${quote.number} became sales order ${order.number}; its stock hold moved with it.`);
      navigate("/sales-orders");
    } catch (caught) {
      setError(message(caught, "Could not make a sales order."));
    } finally {
      setBusyId(null);
    }
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(
        await quotesApi.list(status === "all" ? null : status, { offset: pager.offset, limit: pager.pageSize }),
      );
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load quotations."));
    } finally {
      setLoading(false);
    }
  }, [status, pager.offset, pager.pageSize]);

  useEffect(() => {
    void load();
  }, [load]);

  const stats = data?.stats;
  const shown = data?.currency ?? currency;
  const quotes = data?.quotes ?? [];

  const cancel = async (quote: Quote) => {
    const accepted = await confirm({
      title: "Cancel quotation",
      message: `Cancel ${quote.number}? Its reserved stock is released.`,
      confirmLabel: "Cancel quotation",
      tone: "danger",
    });
    if (!accepted) return;
    setBusyId(quote.id);
    try {
      await quotesApi.cancel(quote.id);
      setToast(`${quote.number} cancelled. Reserved stock released.`);
      await load();
    } catch (caught) {
      setError(message(caught, "Could not cancel the quote."));
    } finally {
      setBusyId(null);
    }
  };

  const openPdf = async (quote: Quote) => {
    setBusyId(quote.id);
    try {
      await quotesApi.openPdf(quote.id);
    } catch (caught) {
      setError(message(caught, "Could not open the PDF."));
    } finally {
      setBusyId(null);
    }
  };

  const iconAction = (intent: ActionIntent) =>
    `flex h-9 w-9 items-center justify-center rounded-full border border-line disabled:opacity-40 ${actionHoverClass(intent)}`;

  const columns: DataTableColumn<Quote>[] = [
    {
      id: "quote",
      header: "Quote",
      cell: (quote) => (
        <>
          <span className="block font-mono text-xs font-semibold">{quote.number}</span>
          <span className="block text-xs text-charcoal/50">
            {shortDate(quote.created_at)}
            {quote.quote_kind === "LAYAWAY" ? (
              <span className="ml-1.5 rounded-full bg-charcoal px-2 py-0.5 text-[10px] font-semibold text-white">
                Layaway
              </span>
            ) : null}
          </span>
        </>
      ),
    },
    {
      id: "customer",
      header: "Customer",
      cell: (quote) => (
        <>
          {quote.customer_id ? (
            <Link to={`/customers/${quote.customer_id}`} className="font-medium hover:text-accent">
              {quote.customer_name}
            </Link>
          ) : (
            <span className="text-charcoal/60">Walk-in</span>
          )}
          <span className="block text-xs text-charcoal/50">
            {quote.sale_type === "WHOLESALE" ? "Wholesale pricing" : "Retail pricing"}
          </span>
        </>
      ),
    },
    { id: "cashier", header: "Prepared by", cell: (quote) => quote.cashier_name ?? "—" },
    {
      id: "units",
      header: "Units",
      align: "right",
      cell: (quote) => quote.items.reduce((sum, item) => sum + item.quantity, 0),
    },
    {
      id: "value",
      header: "Value",
      align: "right",
      className: "font-semibold",
      cell: (quote) => (
        <>
          {formatMoney(quote.total_cents, shown)}
          {quote.quote_kind === "LAYAWAY" ? (
            <span className="block text-xs font-normal text-charcoal/60">
              {formatMoney(quote.deposits_cents ?? 0, shown)} deposited
              {quote.refund_due_cents ? ` · ${formatMoney(quote.refund_due_cents, shown)} to refund` : ""}
            </span>
          ) : null}
        </>
      ),
    },
    {
      id: "validity",
      header: "Validity",
      className: "pl-6",
      cell: (quote) => {
        const expiry = expiryLabel(quote);
        return <span className={expiry.urgent ? "font-semibold text-accent" : ""}>{expiry.text}</span>;
      },
    },
    { id: "status", header: "Status", cell: (quote) => <StatusChip status={quote.quote_status} /> },
    {
      id: "actions",
      header: "Actions",
      align: "right",
      cell: (quote) => (
        <div className="flex items-center justify-end gap-1">
          <button
            type="button"
            aria-label={`Open ${quote.number} PDF`}
            title="Open PDF"
            disabled={busyId === quote.id}
            onClick={() => void openPdf(quote)}
            className={iconAction("info")}
          >
            <FileDown size={15} aria-hidden="true" />
          </button>
          {quote.quote_status === "OPEN" && manage ? (
            <>
              <button
                type="button"
                aria-label={`Cancel ${quote.number}`}
                title="Cancel and release stock"
                disabled={busyId === quote.id}
                onClick={() => void cancel(quote)}
                className={iconAction("danger")}
              >
                <Ban size={15} aria-hidden="true" />
              </button>
              {quote.quote_kind === "LAYAWAY" ? (
                <button
                  type="button"
                  aria-label={`Take a deposit on ${quote.number}`}
                  title="Take a deposit"
                  disabled={busyId === quote.id}
                  onClick={() => setDepositFor(quote)}
                  className={iconAction("neutral")}
                >
                  <Banknote size={15} aria-hidden="true" />
                </button>
              ) : null}
              {ordersOn && quote.quote_kind !== "LAYAWAY" && quote.customer_id ? (
                <button
                  type="button"
                  aria-label={`Make ${quote.number} a sales order`}
                  title="Make a sales order (deliver in parts)"
                  disabled={busyId === quote.id}
                  onClick={() => void toOrder(quote)}
                  className={iconAction("primary")}
                >
                  <Truck size={15} aria-hidden="true" />
                </button>
              ) : null}
              <button
                type="button"
                disabled={busyId === quote.id}
                onClick={() => setConverting(quote)}
                className="flex h-9 items-center gap-1.5 whitespace-nowrap rounded-full bg-accent px-3.5 text-xs font-semibold text-white hover:bg-accent-hover disabled:opacity-40"
              >
                <ArrowRightLeft size={14} aria-hidden="true" />
                Convert to sale
              </button>
            </>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">Open quotations</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{stats?.open_count ?? "—"}</p>
          <p className="mt-2 text-xs text-white/50 tabular-nums">
            {stats ? `${formatMoney(stats.open_value_cents, shown)} of stock on hold` : "Loading…"}
          </p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">Conversion rate</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">
            {stats ? `${(stats.conversion_rate_bps / 100).toFixed(1)}%` : "—"}
          </p>
          <p className="mt-2 text-xs text-white/80 tabular-nums">
            {stats ? `${stats.converted_count} converted · ${formatMoney(stats.converted_value_cents, shown)}` : ""}
          </p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Expiring in 48 hours</p>
          <p className={`mt-4 text-4xl font-semibold tabular-nums ${stats?.expiring_soon_count ? "text-accent" : ""}`}>
            {stats?.expiring_soon_count ?? "—"}
          </p>
          <p className="mt-2 text-xs text-charcoal/50">Follow up before the stock is released</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Lost</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">
            {stats ? stats.expired_count + stats.cancelled_count : "—"}
          </p>
          <p className="mt-2 text-xs text-charcoal/50">
            {stats ? `${stats.expired_count} expired · ${stats.cancelled_count} cancelled` : ""}
          </p>
        </article>
      </div>

      <div className="overflow-hidden rounded-card border border-line bg-white">
        <div className="flex flex-wrap items-center justify-between gap-3 p-6 pb-5">
          <SegmentedControl label="Quote status" value={status} options={statusOptions} onChange={setStatus} />
          <p className="text-sm text-charcoal/60">Quotes are created at the register with “Save as Proforma Quote”.</p>
          {error ? (
            <div className="w-full">
              <ErrorNote message={error} />
            </div>
          ) : null}
        </div>
        <DataTable
          aria-label="Quotations"
          variant="flush"
          minWidth="1040px"
          columns={columns}
          data={quotes}
          getRowId={(quote) => quote.id}
          isLoading={data === null && error === null}
          isFetching={loading && data !== null}
          emptyState={{ icon: FileText, title: "No quotations with this status" }}
          pagination={{
            mode: "server",
            currentPage: pager.page,
            pageSize: pager.pageSize,
            totalRecords: data?.total ?? 0,
            onPageChange: pager.setPage,
            onPageSizeChange: pager.setPageSize,
          }}
        />
      </div>

      {converting ? (
        <ConvertQuoteModal
          quote={converting}
          currency={shown}
          onClose={() => setConverting(null)}
          onConverted={(quote) => {
            setConverting(null);
            setToast(`${quote.number} converted into a completed sale.`);
            void load();
          }}
        />
      ) : null}
      {depositFor ? (
        <TakeDepositModal
          quote={depositFor}
          currency={shown}
          onClose={() => setDepositFor(null)}
          onSaved={(quote) => {
            setDepositFor(null);
            setToast(`Deposit recorded on ${quote.number}. ${formatMoney(quote.total_cents - (quote.deposits_cents ?? 0), shown)} left.`);
            void load();
          }}
        />
      ) : null}
      {toast ? <Toast message={toast} onDismiss={dismissToast} /> : null}
    </section>
  );
}
