import {
  MovementType,
  SerialStatus,
  formatMoney,
  movementLabel,
  type ProductCosting,
  type ProductPurchaseHistory,
  type ProductSalesHistory,
  type ProductSerials,
  type StockMovement,
} from "@ai-pos/shared-types";
import { Link } from "react-router-dom";
import {
  ArrowDownLeft,
  ArrowLeftRight,
  ArrowUpRight,
  ChefHat,
  ClipboardCheck,
  Lock,
  PackagePlus,
  RotateCcw,
  Search,
  ShieldAlert,
  TrendingDown,
  TrendingUp,
  Undo2,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { Sparkline } from "../../components/charts/Charts";
import { DocStatus, formatDate } from "./shared";
import type { Resource } from "./useProductDetails";

// --- Loading / empty states ----------------------------------------------------------------------

function Bone({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-xl bg-charcoal/[0.07] ${className}`} />;
}

export function SkeletonSummary({ cards = 3 }: { cards?: number }) {
  return (
    <div className="relative overflow-hidden rounded-2xl bg-charcoal p-5" aria-hidden="true">
      <div className="absolute inset-x-0 top-0 h-1 animate-pulse bg-accent" />
      <div className={`grid gap-4 ${cards === 4 ? "grid-cols-2 xl:grid-cols-4" : "grid-cols-2 sm:grid-cols-3"}`}>
        {Array.from({ length: cards }, (_, index) => (
          <div key={index} className="space-y-2">
            <div className="h-2.5 w-20 animate-pulse rounded-full bg-white/15" />
            <div className="h-6 w-28 animate-pulse rounded-lg bg-white/25" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function SkeletonRows({ rows = 6 }: { rows?: number }) {
  return (
    <div className="space-y-2.5" aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="flex items-center gap-3">
          <Bone className="h-9 w-1 shrink-0 rounded-full !bg-accent/30" />
          <Bone className="h-9 flex-1" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonCards() {
  return (
    <div className="grid grid-cols-2 gap-3 xl:grid-cols-3" aria-hidden="true">
      {Array.from({ length: 6 }, (_, index) => (
        <div key={index} className={`rounded-2xl p-4 ${index === 0 ? "bg-charcoal" : "bg-surface"}`}>
          <div className={`h-2.5 w-16 animate-pulse rounded-full ${index === 0 ? "bg-white/20" : "bg-charcoal/10"}`} />
          <div
            className={`mt-3 h-6 w-24 animate-pulse rounded-lg ${index === 0 ? "bg-accent/70" : "bg-charcoal/10"}`}
          />
        </div>
      ))}
    </div>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-2xl bg-surface px-5 py-10 text-center text-sm text-charcoal/60">{children}</p>;
}

export function ResourceView<T>({
  resource,
  skeleton,
  forbiddenText,
  children,
}: {
  resource: Resource<T>;
  skeleton: ReactNode;
  forbiddenText: string;
  children: (data: T) => ReactNode;
}) {
  if (resource.state === "loading") {
    return (
      <div role="status" aria-label="Loading">
        {skeleton}
      </div>
    );
  }
  if (resource.state === "forbidden") {
    return (
      <div className="flex items-center gap-3 rounded-2xl bg-surface px-5 py-6 text-sm text-charcoal/70">
        <Lock size={16} aria-hidden="true" className="shrink-0 text-accent" />
        {forbiddenText}
      </div>
    );
  }
  if (resource.state === "error") {
    return (
      <div className="flex items-center gap-3 rounded-2xl bg-danger/10 px-5 py-6 text-sm text-danger" role="alert">
        <ShieldAlert size={16} aria-hidden="true" className="shrink-0" />
        {resource.message}
      </div>
    );
  }
  return <>{children(resource.data)}</>;
}

function SummaryBar({ items }: { items: { label: string; value: string; accent?: boolean }[] }) {
  return (
    <dl className="grid grid-cols-2 gap-4 rounded-2xl bg-charcoal p-5 text-white sm:grid-cols-4">
      {items.map((item) => (
        <div key={item.label} className="min-w-0">
          <dt className="text-[11px] font-medium uppercase tracking-wide text-white/55">{item.label}</dt>
          <dd className={`mt-1 truncate text-xl font-bold tabular-nums ${item.accent ? "text-accent" : ""}`}>
            {item.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

const th = "pb-3 pr-4 font-medium whitespace-nowrap";
const td = "py-3 pr-4 whitespace-nowrap";

function HistoryTable({ head, children, minWidth }: { head: ReactNode; children: ReactNode; minWidth: string }) {
  return (
    <div className="overflow-x-auto">
      <table className={`w-full text-left text-sm ${minWidth}`}>
        <thead className="text-xs uppercase tracking-wide text-charcoal/50">
          <tr>{head}</tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

// --- Sales ---------------------------------------------------------------------------------------

export function SalesTab({ resource }: { resource: Resource<ProductSalesHistory> }) {
  return (
    <ResourceView
      resource={resource}
      skeleton={
        <div className="space-y-5">
          <SkeletonSummary cards={4} />
          <SkeletonRows />
        </div>
      }
      forbiddenText="Sales history needs the reports permission."
    >
      {(sales) => (
        <div className="space-y-5">
          <SummaryBar
            items={[
              {
                label: "Avg selling price",
                value:
                  sales.average_selling_price_cents === null
                    ? "—"
                    : formatMoney(sales.average_selling_price_cents, sales.currency),
              },
              { label: "Total revenue", value: formatMoney(sales.revenue_cents, sales.currency), accent: true },
              { label: "Units sold", value: String(sales.units_sold) },
              { label: "Invoices", value: String(sales.sale_count) },
            ]}
          />
          {sales.rows.some((row) => row.currency !== sales.currency) ? (
            <p className="text-xs text-charcoal/50">
              Totals cover {sales.currency} sales only; sales rung up in another currency are listed but not summed.
            </p>
          ) : null}
          {sales.rows.length === 0 ? (
            <Empty>No completed sales for this product yet.</Empty>
          ) : (
            <HistoryTable
              minWidth="min-w-[760px]"
              head={
                <>
                  <th className={th}>Invoice ID</th>
                  <th className={th}>Date &amp; time</th>
                  <th className={th}>Store branch</th>
                  <th className={th}>Cashier</th>
                  <th className={`${th} text-right`}>Qty</th>
                  <th className={`${th} text-right`}>Unit price</th>
                  <th className={`${th} text-right`}>Unit cost</th>
                  <th className={`${th} text-right`}>COGS</th>
                  <th className={`${th} pr-0 text-right`}>Gross profit</th>
                </>
              }
            >
              {sales.rows.map((row) => (
                <tr key={row.sale_item_id} className="border-t border-line">
                  <td className={td}>
                    <span className="font-mono text-xs font-semibold">{row.invoice}</span>
                    {row.status !== "completed" ? (
                      <span className="ml-2">
                        <DocStatus status={row.status} />
                      </span>
                    ) : null}
                  </td>
                  <td className={`${td} tabular-nums text-charcoal/70`}>{formatDate(row.sold_at)}</td>
                  <td className={td}>
                    <span className="font-semibold">{row.store_code}</span>
                    <span className="ml-1 text-charcoal/50">{row.store_name}</span>
                  </td>
                  <td className={td}>{row.cashier_name ?? "—"}</td>
                  <td className={`${td} text-right tabular-nums`}>{row.quantity}</td>
                  <td className={`${td} text-right tabular-nums`}>{formatMoney(row.unit_price_cents, row.currency)}</td>
                  <td className={`${td} text-right tabular-nums`}>
                    {row.cost_cents === null ? "Uncosted" : formatMoney(Math.round(row.cost_cents / row.quantity), row.currency)}
                    {row.cost_estimated ? <span className="block text-[11px] text-charcoal/40">estimated</span> : null}
                  </td>
                  <td className={`${td} text-right tabular-nums`}>
                    {row.cost_cents === null ? "—" : formatMoney(row.cost_cents, row.currency)}
                  </td>
                  <td className={`${td} pr-0 text-right font-semibold tabular-nums`}>
                    {row.gross_profit_cents === null ? "—" : formatMoney(row.gross_profit_cents, row.currency)}
                  </td>
                </tr>
              ))}
            </HistoryTable>
          )}
        </div>
      )}
    </ResourceView>
  );
}

// --- Purchases -----------------------------------------------------------------------------------

export function PurchasesTab({
  resource,
  costing,
  currency,
}: {
  resource: Resource<ProductPurchaseHistory>;
  costing: Resource<ProductCosting>;
  currency: string;
}) {
  return (
    <ResourceView
      resource={resource}
      skeleton={
        <div className="space-y-5">
          <SkeletonSummary cards={4} />
          <Bone className="h-36" />
          <SkeletonRows rows={4} />
        </div>
      }
      forbiddenText="Purchase costs are visible to inventory managers only."
    >
      {(history) => {
        const trend = history.rows
          .filter((row) => row.received_at !== null)
          .sort((a, b) => (a.received_at ?? "").localeCompare(b.received_at ?? ""));
        const values = trend.map((row) => row.unit_cost_cents);
        const previous = values.at(-2);
        const latest = values.at(-1);
        const change = previous && latest !== undefined ? ((latest - previous) / previous) * 100 : null;
        const first = trend.at(0);
        const last = trend.at(-1);
        const money = (cents: number | null) => (cents === null ? "—" : formatMoney(cents, currency));
        return (
          <div className="space-y-5">
            <SummaryBar
              items={[
                { label: "Latest cost / unit", value: money(history.latest_unit_cost_cents), accent: true },
                { label: "Avg cost / unit", value: money(history.average_unit_cost_cents) },
                { label: "Units received", value: String(history.units_received) },
                { label: "Total PO spend", value: money(history.total_spend_cents) },
              ]}
            />
            <div className="rounded-2xl border border-line p-5">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h4 className="font-semibold">Cost price trend</h4>
                  <p className="text-xs text-charcoal/50">Unit cost on each goods receipt, oldest to newest.</p>
                </div>
                {change !== null ? (
                  <span
                    className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold tabular-nums ${
                      change > 0 ? "bg-accent text-white" : "bg-charcoal text-white"
                    }`}
                  >
                    {change > 0 ? (
                      <TrendingUp size={13} aria-hidden="true" />
                    ) : (
                      <TrendingDown size={13} aria-hidden="true" />
                    )}
                    {change > 0 ? "+" : ""}
                    {change.toFixed(1)}% vs previous
                  </span>
                ) : null}
              </div>
              {first && last ? (
                <>
                  <Sparkline values={values} stroke="var(--primary)" />
                  <div className="mt-2 flex justify-between text-[11px] tabular-nums text-charcoal/50">
                    <span>{formatDate(first.received_at)}</span>
                    {trend.length > 1 ? <span>{formatDate(last.received_at)}</span> : null}
                  </div>
                </>
              ) : (
                <p className="py-6 text-center text-sm text-charcoal/50">No goods received yet.</p>
              )}
            </div>
            {history.rows.length === 0 ? (
              <Empty>No purchase orders include this product.</Empty>
            ) : (
              <HistoryTable
                minWidth="min-w-[700px]"
                head={
                  <>
                    <th className={th}>PO number</th>
                    <th className={th}>Supplier</th>
                    <th className={th}>Received date</th>
                    <th className={`${th} text-right`}>Cost / unit</th>
                    <th className={`${th} text-right`}>Qty received</th>
                    <th className={`${th} pr-0 text-right`}>Total PO cost</th>
                  </>
                }
              >
                {history.rows.map((row) => (
                  <tr
                    key={`${row.purchase_order_id}-${row.goods_receipt_id ?? "open"}`}
                    className="border-t border-line"
                  >
                    <td className={td}>
                      <Link to="/inventory/purchase-orders" className="font-mono text-xs font-semibold text-accent hover:underline">
                        {row.po_number}
                      </Link>
                      <span className="ml-1 text-xs text-charcoal/50">{row.grn_number ?? row.store_code}</span>
                      {row.goods_receipt_id === null ? (
                        <span className="ml-2">
                          <DocStatus status={row.po_status} />
                        </span>
                      ) : null}
                    </td>
                    <td className={td}>{row.supplier_name}</td>
                    <td className={`${td} tabular-nums text-charcoal/70`}>
                      {row.received_at ? formatDate(row.received_at) : "Awaiting delivery"}
                    </td>
                    <td className={`${td} text-right tabular-nums`}>{formatMoney(row.unit_cost_cents, currency)}</td>
                    <td className={`${td} text-right tabular-nums`}>
                      {row.quantity_received}
                      <span className="text-charcoal/40"> / {row.quantity_ordered}</span>
                    </td>
                    <td className={`${td} pr-0 text-right font-semibold tabular-nums`}>
                      {formatMoney(row.total_cost_cents, currency)}
                    </td>
                  </tr>
                ))}
              </HistoryTable>
            )}
            {costing.state === "ready" ? (
              <div className="space-y-3">
                <div>
                  <h4 className="font-semibold">Cost layers</h4>
                  <p className="text-xs text-charcoal/50">
                    Each receipt keeps its own unit cost. A later purchase does not rewrite an earlier one.
                    Realized gross profit {formatMoney(costing.data.realized_profit_cents, currency)} is from posted
                    sales. Unsold stock is not counted as profit.
                  </p>
                </div>
                {costing.data.layers.length === 0 ? (
                  <Empty>No cost layers yet. Stock received before cost layers, or never received, stays uncosted.</Empty>
                ) : (
                  <HistoryTable
                    minWidth="min-w-[760px]"
                    head={
                      <>
                        <th className={th}>Batch</th>
                        <th className={th}>Receipt date</th>
                        <th className={`${th} text-right`}>Original</th>
                        <th className={`${th} text-right`}>Remaining</th>
                        <th className={`${th} text-right`}>Unit cost</th>
                        <th className={`${th} pr-0 text-right`}>Remaining value</th>
                      </>
                    }
                  >
                    {costing.data.layers.map((layer) => (
                      <tr key={layer.batch_item_id} className="border-t border-line">
                        <td className={`${td} font-mono text-xs font-semibold`}>{layer.batch_number}</td>
                        <td className={`${td} tabular-nums text-charcoal/70`}>{formatDate(layer.receipt_date)}</td>
                        <td className={`${td} text-right tabular-nums`}>{layer.original_quantity}</td>
                        <td className={`${td} text-right tabular-nums`}>
                          {layer.remaining_quantity}
                          <span className="text-charcoal/40"> · {layer.consumed_quantity} used</span>
                        </td>
                        <td className={`${td} text-right tabular-nums`}>{formatMoney(layer.unit_cost_cents, currency)}</td>
                        <td className={`${td} pr-0 text-right font-semibold tabular-nums`}>
                          {formatMoney(layer.remaining_value_cents, currency)}
                        </td>
                      </tr>
                    ))}
                  </HistoryTable>
                )}
              </div>
            ) : null}
          </div>
        );
      }}
    </ResourceView>
  );
}

// --- Serials -------------------------------------------------------------------------------------

const serialStyles: Record<SerialStatus, string> = {
  in_stock: "bg-charcoal text-white",
  reserved: "bg-surface text-charcoal ring-1 ring-line",
  in_transit: "bg-accent/10 text-accent ring-1 ring-accent/40",
  sold: "bg-accent text-white",
  defective: "bg-danger/10 text-danger ring-1 ring-danger/40",
  repair: "bg-surface text-charcoal ring-1 ring-charcoal/30",
  quarantine: "bg-surface text-charcoal/60 ring-1 ring-line",
  scrapped: "bg-surface text-charcoal/40 line-through ring-1 ring-line",
  reversed: "bg-surface text-charcoal/40 line-through ring-1 ring-line",
};

const serialLabel = (status: SerialStatus) => status.replace(/_/g, " ").toUpperCase();

export function SerialsTab({
  resource,
  status,
  query,
  onStatus,
  onQuery,
}: {
  resource: Resource<ProductSerials>;
  status: SerialStatus | null;
  query: string;
  onStatus: (status: SerialStatus | null) => void;
  onQuery: (query: string) => void;
}) {
  const [draft, setDraft] = useState(query);
  const counts = resource.state === "ready" ? resource.data.status_counts : {};
  const total = Object.values(counts).reduce((sum, value) => sum + (value ?? 0), 0);
  const filters: (SerialStatus | null)[] = [null, ...Object.values(SerialStatus).filter((value) => counts[value])];
  if (status !== null && !filters.includes(status)) filters.push(status);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by status">
          {filters.map((value) => (
            <button
              key={value ?? "all"}
              type="button"
              aria-pressed={status === value}
              onClick={() => onStatus(value)}
              className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                status === value ? "bg-charcoal text-white" : "bg-surface text-charcoal/70 hover:text-charcoal"
              }`}
            >
              {value === null ? "All" : serialLabel(value)}
              <span className={`ml-1.5 tabular-nums ${status === value ? "text-accent" : "text-charcoal/40"}`}>
                {value === null ? total : (counts[value] ?? 0)}
              </span>
            </button>
          ))}
        </div>
        <form
          className="relative w-full xl:w-72"
          onSubmit={(event) => {
            event.preventDefault();
            onQuery(draft);
          }}
        >
          <Search
            size={15}
            aria-hidden="true"
            className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-charcoal/40"
          />
          <input
            type="search"
            value={draft}
            onChange={(event) => {
              setDraft(event.target.value);
              if (event.target.value === "") onQuery("");
            }}
            placeholder="Full IMEI or last 4 digits"
            aria-label="Search IMEI or serial"
            autoComplete="off"
            spellCheck={false}
            className="h-10 w-full rounded-full border border-line bg-surface pl-9 pr-4 text-sm"
          />
        </form>
      </div>
      <ResourceView resource={resource} skeleton={<SkeletonRows />} forbiddenText="You cannot view serials.">
        {(serials) =>
          serials.rows.length === 0 ? (
            <Empty>{query || status ? "No serials match this filter." : "No IMEIs or serials registered yet."}</Empty>
          ) : (
            <>
              <HistoryTable
                minWidth="min-w-[680px]"
                head={
                  <>
                    <th className={th}>IMEI / Serial</th>
                    <th className={th}>Status</th>
                    <th className={th}>Store</th>
                    <th className={th}>Assigned customer</th>
                    <th className={`${th} pr-0`}>Warranty expiry</th>
                  </>
                }
              >
                {serials.rows.map((row) => (
                  <tr key={row.serial_number_id} className="border-t border-line">
                    <td className={td}>
                      <span className="font-mono text-xs font-semibold tracking-wider">•••• {row.last4}</span>
                      <span className="ml-2 text-[11px] uppercase text-charcoal/40">{row.kind}</span>
                    </td>
                    <td className={td}>
                      <span
                        className={`inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${serialStyles[row.status]}`}
                      >
                        {serialLabel(row.status)}
                      </span>
                    </td>
                    <td className={td}>
                      <span className="font-semibold">{row.store_code}</span>
                      <span className="ml-1 text-charcoal/50">{row.store_name}</span>
                    </td>
                    <td className={td}>
                      {row.sale_invoice ? (
                        <span className="text-charcoal/70">
                          Sold on <span className="font-mono text-xs">{row.sale_invoice}</span>
                        </span>
                      ) : (
                        <span className="text-charcoal/40">—</span>
                      )}
                    </td>
                    <td className={`${td} pr-0 text-charcoal/40`}>Not recorded</td>
                  </tr>
                ))}
              </HistoryTable>
              <p className="text-xs text-charcoal/50">
                IMEIs are masked to the last four digits. Search with the full number for an exact match.
                {serials.total > serials.rows.length ? ` Showing ${serials.rows.length} of ${serials.total}.` : ""}
              </p>
            </>
          )
        }
      </ResourceView>
    </div>
  );
}

// --- Stock timeline ------------------------------------------------------------------------------

const movementIcons: Record<MovementType, typeof PackagePlus> = {
  PURCHASE_IN: PackagePlus,
  SALE_OUT: ArrowUpRight,
  RETURN_IN: RotateCcw,
  TRANSFER_IN: ArrowDownLeft,
  TRANSFER_OUT: ArrowLeftRight,
  DAMAGE_SHRINKAGE: ShieldAlert,
  AUDIT_ADJUSTMENT: ClipboardCheck,
  PURCHASE_REVERSAL: Undo2,
  RECIPE_OUT: ChefHat,
};

export function TimelineTab({ resource }: { resource: Resource<StockMovement[]> }) {
  const [type, setType] = useState<MovementType | "all">("all");
  return (
    <ResourceView resource={resource} skeleton={<SkeletonRows rows={7} />} forbiddenText="You cannot view movements.">
      {(movements) => {
        const present = Object.values(MovementType).filter((value) =>
          movements.some((movement) => movement.movement_type === value),
        );
        const shown = type === "all" ? movements : movements.filter((movement) => movement.movement_type === type);
        return (
          <div className="space-y-4">
            {present.length > 1 ? (
              <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by movement type">
                {(["all", ...present] as const).map((value) => (
                  <button
                    key={value}
                    type="button"
                    aria-pressed={type === value}
                    onClick={() => setType(value)}
                    className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                      type === value ? "bg-charcoal text-white" : "bg-surface text-charcoal/70 hover:text-charcoal"
                    }`}
                  >
                    {value === "all" ? "All movements" : movementLabel(value)}
                  </button>
                ))}
              </div>
            ) : null}
            {shown.length === 0 ? (
              <Empty>No stock movements recorded yet.</Empty>
            ) : (
              <ol className="relative">
                {shown.map((movement, index) => {
                  const Icon = movementIcons[movement.movement_type];
                  const inbound = movement.quantity > 0;
                  return (
                    <li key={movement.id} className="relative flex gap-4 pb-5 last:pb-0">
                      {index < shown.length - 1 ? (
                        <span
                          className="absolute left-[17px] top-9 h-[calc(100%-2.25rem)] w-px bg-line"
                          aria-hidden="true"
                        />
                      ) : null}
                      <span
                        className={`grid h-9 w-9 shrink-0 place-items-center rounded-full ${
                          inbound ? "bg-charcoal text-white" : "bg-accent text-white"
                        }`}
                      >
                        <Icon size={15} aria-hidden="true" />
                      </span>
                      <div className="min-w-0 flex-1 rounded-2xl bg-surface px-4 py-3">
                        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                          <p className="text-sm font-semibold">
                            {movementLabel(movement.movement_type)}
                            <span className="ml-2 font-mono text-[11px] font-medium text-charcoal/40">
                              {movement.movement_type}
                            </span>
                          </p>
                          <p
                            className={`text-base font-bold tabular-nums ${inbound ? "text-charcoal" : "text-accent"}`}
                          >
                            {inbound ? "+" : ""}
                            {movement.quantity}
                          </p>
                        </div>
                        <p className="mt-1 text-xs text-charcoal/60">
                          <span className="font-semibold text-charcoal/80">{movement.store_code}</span>
                          {" · "}
                          {formatDate(movement.created_at)}
                          {" · "}
                          {movement.user_name ?? "System"}
                          {" · "}
                          <span className="tabular-nums">{movement.quantity_after} after</span>
                        </p>
                        {movement.note ? (
                          <p className="mt-1 truncate text-xs text-charcoal/50">{movement.note}</p>
                        ) : null}
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
          </div>
        );
      }}
    </ResourceView>
  );
}
