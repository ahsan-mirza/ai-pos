import {
  Capability,
  formatMoney,
  type BackorderRow,
  type FulfillmentBoard,
  type SalesOrderRow,
} from "@ai-pos/shared-types";
import { AxizTabs, pageCount, useLocale } from "@ai-pos/ui";
import { MapPinned, PackageCheck, Search, Truck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { tabBarClass } from "../../components/layout/AppShell";
import { DataTable, PaginationFooter, usePagination, type DataTableColumn } from "../../components/ui/DataTable";
import { FilterSelect } from "../../components/ui/Field";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { useAuth } from "../../lib/auth";
import { useCapability } from "../../lib/capabilities";
import { formatDate, storeOptions, useStores } from "../inventory/shared";
import { salesOrdersApi } from "./api";
import { FleetBoard, type FleetSection } from "./FleetBoard";
import { SalesOrderDetail } from "./SalesOrderDetail";
import { OrderStatusChip } from "./SalesOrdersPage";

export type FulfillmentView = "OPEN" | "DRAFT" | "DELIVERED" | "all" | "backorders";

/** English catalog key for the empty table. Translated at the call site. */
export function fulfillmentEmptyKey(
  view: FulfillmentView,
  filters: { query: string; storeId: string; lockedStore: boolean },
): "Nothing is waiting for stock" | "No orders match these filters." | "No orders in this branch." | "No open orders" | "No sales orders here" {
  if (view === "backorders") return "Nothing is waiting for stock";
  if (filters.query.trim()) return "No orders match these filters.";
  if (filters.storeId && !filters.lockedStore) return "No orders in this branch.";
  if (view === "OPEN") return "No open orders";
  return "No sales orders here";
}

function emptyTitle(
  view: FulfillmentView,
  filters: { query: string; storeId: string; lockedStore: boolean },
  t: (text: string) => string,
): string {
  const key = fulfillmentEmptyKey(view, filters);
  if (key === "Nothing is waiting for stock") return t("Nothing is waiting for stock");
  if (key === "No orders match these filters.") return t("No orders match these filters.");
  if (key === "No orders in this branch.") return t("No orders in this branch.");
  if (key === "No open orders") return t("No open orders");
  return t("No sales orders here");
}

function knownError(message: string, t: (text: string, vars?: Record<string, string | number>) => string): string {
  if (message === "Could not load this list.") return t("Could not load this list.");
  if (message === "The fulfillment board could not be loaded.") return t("The fulfillment board could not be loaded.");
  return message;
}

export interface FulfillmentBoardViewProps {
  board: FulfillmentBoard | null;
  boardError: string | null;
  view: FulfillmentView;
  onView: (view: FulfillmentView) => void;
  search: string;
  onSearch: (value: string) => void;
  storeId: string;
  onStore: (value: string) => void;
  branchOptions: { value: string; label: string }[];
  lockedStore: boolean;
  onClear: () => void;
  rows: SalesOrderRow[] | null;
  total: number;
  backorders: BackorderRow[] | null;
  listError: string | null;
  loading: boolean;
  page: number;
  pageSize: number;
  onPage: (page: number) => void;
  onPageSize: (size: number) => void;
  onRetry: () => void;
  onOpen: (id: string) => void;
}

export function FulfillmentBoardView({
  board,
  boardError,
  view,
  onView,
  search,
  onSearch,
  storeId,
  onStore,
  branchOptions,
  lockedStore,
  onClear,
  rows,
  total,
  backorders,
  listError,
  loading,
  page,
  pageSize,
  onPage,
  onPageSize,
  onRetry,
  onOpen,
}: FulfillmentBoardViewProps) {
  const { t, locale } = useLocale();
  const filters = { query: search, storeId, lockedStore };
  const filtersActive = view !== "OPEN" || search.trim() !== "" || (storeId !== "" && !lockedStore);
  const waiting = view === "backorders";
  const list = waiting ? null : rows;
  const waitingRows = waiting ? backorders : null;
  const source = waiting ? waitingRows : list;
  const recordCount = waiting ? (waitingRows?.length ?? 0) : total;
  const start = (page - 1) * pageSize;
  const orderPage = list ?? [];
  const backorderPage = (waitingRows ?? []).slice(start, start + pageSize);
  const pageIsEmpty = waiting ? backorderPage.length === 0 : orderPage.length === 0;
  const listFailed = !loading && listError !== null && source === null;
  const title = emptyTitle(view, filters, t);
  const zone = board?.timezone
    ? t("Today follows the business timezone ({zone}).", { zone: board.timezone })
    : t("Today follows the business timezone.");

  const orderColumns: DataTableColumn<SalesOrderRow>[] = [
    {
      id: "order",
      header: t("Order"),
      cell: (row) => (
        <button type="button" onClick={() => onOpen(row.id)} className="font-mono text-xs font-semibold text-charcoal hover:text-accent">
          {row.number}
        </button>
      ),
    },
    {
      id: "customer",
      header: t("Customer"),
      cell: (row) => <span className="font-medium">{row.customer_name}</span>,
    },
    { id: "status", header: t("Status"), cell: (row) => <OrderStatusChip status={row.status} /> },
    {
      id: "outstanding",
      header: t("Outstanding"),
      align: "right",
      cell: (row) => (
        <>
          <span className="tabular-nums">{row.outstanding_units.toLocaleString()}</span>
          {row.backordered_units > 0 ? (
            <span className="block text-xs font-semibold text-accent">
              {t("{count} backordered", { count: row.backordered_units })}
            </span>
          ) : null}
        </>
      ),
    },
    {
      id: "total",
      header: t("Total"),
      align: "right",
      className: "tabular-nums font-semibold",
      cell: (row) => formatMoney(row.total_cents, row.currency),
    },
    {
      id: "requested",
      header: t("Requested"),
      className: "hidden lg:table-cell",
      cell: (row) => formatDate(row.requested_date),
    },
    {
      id: "created",
      header: t("Created"),
      className: "hidden 2xl:table-cell whitespace-nowrap",
      cell: (row) => formatDate(row.created_at, board?.timezone),
    },
    {
      id: "actions",
      header: t("Actions"),
      align: "right",
      cell: (row) => (
        <button type="button" onClick={() => onOpen(row.id)} className="text-xs font-semibold text-accent">
          {t("View")}
        </button>
      ),
    },
  ];

  const backorderColumns: DataTableColumn<BackorderRow>[] = [
    {
      id: "order",
      header: t("Order"),
      cell: (row) => (
        <button type="button" onClick={() => onOpen(row.order_id)} className="font-mono text-xs font-semibold hover:text-accent">
          {row.order_number}
        </button>
      ),
    },
    { id: "customer", header: t("Customer"), cell: (row) => row.customer_name },
    {
      id: "product",
      header: t("Product"),
      cell: (row) => (
        <>
          <span className="block font-medium">{row.product_name}</span>
          <span className="block font-mono text-xs text-charcoal/50">{row.sku}</span>
        </>
      ),
    },
    {
      id: "waiting",
      header: t("Backordered"),
      align: "right",
      className: "font-semibold text-accent tabular-nums",
      cell: (row) => row.backordered.toLocaleString(),
    },
    {
      id: "free",
      header: t("Free now"),
      align: "right",
      className: "hidden md:table-cell tabular-nums",
      cell: (row) => row.available_now.toLocaleString(),
    },
    {
      id: "since",
      header: t("Ordered"),
      className: "hidden lg:table-cell",
      cell: (row) => formatDate(row.ordered_at),
    },
  ];

  const cards = [
    { label: t("Open orders"), value: board?.orders_open },
    { label: t("Orders today"), value: board?.orders_today },
    { label: t("Out for delivery"), value: board?.out_for_delivery },
    { label: t("Delivered today"), value: board?.delivered_today },
  ];
  const pageTotal = pageCount(recordCount, pageSize);

  return (
    <section dir={locale === "ar" ? "rtl" : "ltr"} className="min-w-0 max-w-full space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-charcoal">{t("Fulfillment")}</h1>
          <p className="mt-1 text-sm text-charcoal/60">{zone}</p>
        </div>
        <Link to="/sales-orders" className="text-sm font-semibold text-accent">
          {t("View all orders")}
        </Link>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-busy={board === null && boardError === null}>
        {cards.map((card) => (
          <article key={card.label} className="flex h-full min-w-0 flex-col rounded-2xl border border-line bg-white px-4 py-3">
            <p className="text-xs font-medium text-charcoal/55">{card.label}</p>
            {card.value === undefined && boardError === null ? (
              <span className="mt-2 block h-8 w-16 animate-pulse rounded-full bg-charcoal/10" />
            ) : (
              <p className="mt-1 text-2xl font-semibold tabular-nums text-charcoal">
                {card.value === undefined ? "—" : card.value.toLocaleString()}
              </p>
            )}
          </article>
        ))}
      </div>
      {boardError ? (
        <p role="alert" className="rounded-2xl bg-danger/10 px-4 py-3 text-sm text-danger">
          {knownError(boardError, t)}{" "}
          <button type="button" onClick={onRetry} className="font-semibold underline">
            {t("Try again")}
          </button>
        </p>
      ) : null}
      <p className="text-xs text-charcoal/55">{t("On-time delivery is omitted until an order records a promised time.")}</p>

      {board?.map_configured ? (
        <section aria-label={t("Delivery map")} className="min-h-72 rounded-2xl border border-line bg-white" />
      ) : (
        <section className="flex min-w-0 items-start gap-3 rounded-2xl border border-line bg-surface px-4 py-3">
          <MapPinned size={18} aria-hidden="true" className="mt-0.5 shrink-0 text-charcoal/40" />
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-charcoal">{t("Map provider is not configured.")}</h2>
            <p className="mt-1 text-sm text-charcoal/60">
              {t("Delivery locations appear here once a map provider is connected. No positions are estimated.")}
            </p>
          </div>
        </section>
      )}

      <div className="min-w-0 rounded-2xl border border-line bg-white">
        <div className="flex flex-wrap items-end justify-between gap-3 p-4">
          <SegmentedControl
            label={t("Order view")}
            value={view}
            onChange={onView}
            options={[
              { value: "OPEN", label: t("Open") },
              { value: "DRAFT", label: t("Drafts") },
              { value: "DELIVERED", label: t("Delivered") },
              { value: "all", label: t("All") },
              { value: "backorders", label: t("Backorders") },
            ]}
          />
          <div className="flex min-w-0 flex-1 flex-wrap items-end justify-end gap-3">
            {waiting ? null : (
              <label className="w-full min-w-0 sm:w-64">
                <span className="sr-only">{t("Find an order")}</span>
                <span className="relative block">
                  <Search size={15} aria-hidden="true" className="absolute start-3.5 top-1/2 -translate-y-1/2 text-charcoal/40" />
                  <input
                    value={search}
                    onChange={(event) => onSearch(event.target.value)}
                    placeholder={t("Order, customer or their ref")}
                    className="w-full rounded-full border border-line bg-white py-2.5 pe-4 ps-9 text-sm focus:border-accent focus:outline-none"
                  />
                </span>
              </label>
            )}
            {lockedStore ? null : (
              <FilterSelect
                label={t("Branch")}
                value={storeId}
                options={[{ value: "", label: t("All branches") }, ...branchOptions]}
                onChange={onStore}
                className="w-full sm:w-52"
              />
            )}
            {filtersActive ? (
              <button type="button" onClick={onClear} className="h-10 text-sm font-semibold text-charcoal/70 hover:text-charcoal">
                {t("Clear filters")}
              </button>
            ) : null}
          </div>
        </div>

        <div className="hidden min-w-0 md:block">
          {waiting ? (
            <DataTable
              aria-label={t("Backorders")}
              variant="flush"
              columns={backorderColumns}
              data={backorderPage}
              getRowId={(row) => `${row.order_id}-${row.product_id}`}
              isLoading={loading && waitingRows === null}
              error={listFailed ? knownError(listError ?? "", t) : null}
              onRetry={onRetry}
              onRowClick={(row) => onOpen(row.order_id)}
              emptyState={{ icon: PackageCheck, title }}
              pagination={{
                mode: "server",
                currentPage: page,
                pageSize,
                totalRecords: recordCount,
                onPageChange: onPage,
                onPageSizeChange: onPageSize,
              }}
            />
          ) : (
            <DataTable
              aria-label={t("Sales orders")}
              variant="flush"
              columns={orderColumns}
              data={orderPage}
              getRowId={(row) => row.id}
              isLoading={loading && list === null}
              error={listFailed ? knownError(listError ?? "", t) : null}
              onRetry={onRetry}
              onRowClick={(row) => onOpen(row.id)}
              emptyState={{ icon: Truck, title }}
              pagination={{
                mode: "server",
                currentPage: page,
                pageSize,
                totalRecords: recordCount,
                onPageChange: onPage,
                onPageSizeChange: onPageSize,
              }}
            />
          )}
        </div>

        <div className="min-w-0 space-y-3 p-4 md:hidden">
          {loading && source === null && !listError ? (
            <div aria-hidden="true" className="space-y-2">
              {Array.from({ length: 4 }, (_, index) => (
                <div key={index} className="h-24 animate-pulse rounded-2xl bg-charcoal/5" />
              ))}
            </div>
          ) : null}
          {listFailed ? (
            <div className="px-2 py-8 text-center">
              <p className="text-sm font-semibold">{t("Could not load this list")}</p>
              <p className="mt-1 text-sm text-charcoal/60">{knownError(listError ?? "", t)}</p>
              <button type="button" onClick={onRetry} className="mt-4 rounded-full border border-line px-4 py-2 text-sm font-semibold">
                {t("Try again")}
              </button>
            </div>
          ) : null}
          {!loading && !listFailed && pageIsEmpty ? (
            <div className="px-2 py-8 text-center">
              <p className="text-sm font-semibold">{title}</p>
            </div>
          ) : null}
          {waiting
            ? backorderPage.map((row) => (
                <button
                  key={`${row.order_id}-${row.product_id}`}
                  type="button"
                  onClick={() => onOpen(row.order_id)}
                  className="block w-full rounded-2xl border border-line bg-white p-3 text-start"
                >
                  <span className="font-mono text-xs font-semibold">{row.order_number}</span>
                  <span className="mt-1 block font-medium">{row.customer_name}</span>
                  <span className="mt-1 block text-sm text-charcoal/70">{row.product_name}</span>
                  <span className="mt-2 flex items-center justify-between gap-3 text-sm tabular-nums">
                    <span>{t("Outstanding")} {row.backordered.toLocaleString()}</span>
                    <span className="font-semibold text-accent">{t("Backordered")}</span>
                  </span>
                </button>
              ))
            : orderPage.map((row) => (
                <button
                  key={row.id}
                  type="button"
                  onClick={() => onOpen(row.id)}
                  className="block w-full rounded-2xl border border-line bg-white p-3 text-start"
                >
                  <span className="flex items-start justify-between gap-3">
                    <span className="font-mono text-xs font-semibold">{row.number}</span>
                    <OrderStatusChip status={row.status} />
                  </span>
                  <span className="mt-1 block text-start font-medium">{row.customer_name}</span>
                  <span className="mt-1 block text-sm text-charcoal/70">
                    {row.promised_on ? (
                      <>
                        {t("Promised")} <span dir="ltr">{formatDate(row.promised_on)}</span>
                      </>
                    ) : row.requested_date ? (
                      <>
                        {t("Requested")} <span dir="ltr">{formatDate(row.requested_date)}</span>
                      </>
                    ) : (
                      t("Not promised")
                    )}
                  </span>
                  <span className="mt-2 flex items-center justify-between gap-3 text-sm tabular-nums">
                    <span>
                      {t("Outstanding")} {row.outstanding_units.toLocaleString()}
                    </span>
                    <span className="font-semibold">{formatMoney(row.total_cents, row.currency)}</span>
                  </span>
                </button>
              ))}
          {listFailed || (loading && source === null) ? null : (
            <PaginationFooter
              page={page}
              pageSize={pageSize}
              totalRecords={recordCount}
              totalPages={pageTotal}
              onPageChange={onPage}
              onPageSizeChange={onPageSize}
              disabled={loading}
            />
          )}
        </div>
      </div>
    </section>
  );
}

export function FulfillmentBoardPage() {
  const { t } = useLocale();
  const { user } = useAuth();
  const fleetOn = useCapability(Capability.FleetDispatch);
  const [section, setSection] = useState<FleetSection | "orders">("orders");
  const { stores } = useStores();
  const lockedStore = Boolean(user?.store_id);
  const [view, setView] = useState<FulfillmentView>("OPEN");
  const [storeId, setStoreId] = useState(user?.store_id ?? "");
  const [search, setSearch] = useState("");
  const pager = usePagination({ resetKeys: [view, storeId, search] });
  const [board, setBoard] = useState<FulfillmentBoard | null>(null);
  const [boardScope, setBoardScope] = useState<string | null>(null);
  const [boardError, setBoardError] = useState<string | null>(null);
  const [rows, setRows] = useState<SalesOrderRow[] | null>(null);
  const [total, setTotal] = useState(0);
  const [backorders, setBackorders] = useState<BackorderRow[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reloadToken, setReloadToken] = useState(0);
  const [openId, setOpenId] = useState<string | null>(null);
  const loadedScope = useRef<string | null>(null);
  const scope = storeId || null;

  useEffect(() => {
    let cancelled = false;
    setBoardError(null);
    salesOrdersApi
      .board(scope)
      .then((next) => {
        if (cancelled) return;
        loadedScope.current = scope ?? "";
        setBoard(next);
        setBoardScope(scope ?? "");
        setBoardError(null);
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setBoardError(caught instanceof Error ? caught.message : "The fulfillment board could not be loaded.");
        if (loadedScope.current !== (scope ?? "")) {
          setBoard(null);
          setBoardScope(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [scope, reloadToken]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setListError(null);
    setRows(null);
    setBackorders(null);
    setTotal(0);
    const run = async () => {
      try {
        if (view === "backorders") {
          const waiting = await salesOrdersApi.backorders(scope);
          if (cancelled) return;
          setBackorders(waiting);
        } else {
          const page = await salesOrdersApi.list(
            { status: view === "all" ? null : view, store_id: scope, q: search.trim() || null },
            { offset: pager.offset, limit: pager.pageSize },
          );
          if (cancelled) return;
          setRows(page.rows);
          setTotal(page.total);
        }
        setListError(null);
      } catch (caught: unknown) {
        if (cancelled) return;
        setListError(caught instanceof Error ? caught.message : "Could not load this list.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [view, scope, search, pager.offset, pager.pageSize, reloadToken]);

  if (openId) {
    return (
      <SalesOrderDetail
        orderId={openId}
        onBack={() => {
          setOpenId(null);
          setReloadToken((token) => token + 1);
        }}
      />
    );
  }

  const visibleBoard = boardScope === (scope ?? "") ? board : null;

  const boardView = (
    <FulfillmentBoardView
      board={visibleBoard}
      boardError={boardError}
      view={view}
      onView={setView}
      search={search}
      onSearch={setSearch}
      storeId={storeId}
      onStore={setStoreId}
      branchOptions={storeOptions(stores)}
      lockedStore={lockedStore}
      onClear={() => {
        setView("OPEN");
        setSearch("");
        if (!lockedStore) setStoreId("");
      }}
      rows={rows}
      total={total}
      backorders={backorders}
      listError={listError}
      loading={loading}
      page={pager.page}
      pageSize={pager.pageSize}
      onPage={pager.setPage}
      onPageSize={pager.setPageSize}
      onRetry={() => setReloadToken((token) => token + 1)}
      onOpen={setOpenId}
    />
  );

  if (!fleetOn) return boardView;

  return (
    <div className="min-w-0">
      <AxizTabs
        ariaLabel={t("Fulfillment")}
        className={tabBarClass}
        activeTab={section}
        onChange={(id) => setSection(id as FleetSection | "orders")}
        tabs={[
          { id: "orders", label: t("Orders") },
          { id: "unscheduled", label: t("Unscheduled") },
          { id: "scheduled", label: t("Scheduled") },
          { id: "unassigned", label: t("Unassigned") },
          { id: "plans", label: t("Dispatch plans") },
          { id: "assigned", label: t("Assigned") },
          { id: "dispatched", label: t("Dispatched") },
          { id: "delivered", label: t("Delivered") },
          { id: "exceptions", label: t("Exceptions") },
          { id: "fleet", label: t("Fleet") },
        ]}
      />
      <div className="pt-4 md:pt-5">
        {section === "orders" ? (
          boardView
        ) : (
          <FleetBoard section={section} storeId={storeId} onOpen={setOpenId} />
        )}
      </div>
    </div>
  );
}
