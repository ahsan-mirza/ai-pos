import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Inbox, type LucideIcon } from "lucide-react";
import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
} from "react";
import { PageSizeSelect } from "./PageSizeSelect";
import { DEFAULT_PAGE_SIZE, PAGE_SIZE_OPTIONS, clampPage, pageCount, pageRange, pageWindow } from "./pagination";

export type ColumnAlign = "left" | "center" | "right";

export interface DataTableColumn<T> {
  /** Stable key; defaults to `accessorKey`. Required when two columns share an accessor or neither has one. */
  id?: string;
  header: ReactNode;
  /** Renders `row[accessorKey]` when no `cell` renderer is given. */
  accessorKey?: keyof T & string;
  cell?: (row: T, index: number) => ReactNode;
  /** CSS width, e.g. `"120px"`, `"20%"` or a number of pixels. */
  width?: string | number;
  align?: ColumnAlign;
  /** Extra classes on every body cell (e.g. responsive `hidden lg:table-cell`). */
  className?: string;
  /** Extra classes on the header cell; defaults to `className` so responsive visibility stays in sync. */
  headerClassName?: string;
  /** Client mode and unpaged tables sort by this value when the header is clicked. */
  sortValue?: (row: T) => string | number | null;
}

interface PaginationBase {
  pageSizeOptions?: readonly number[];
  /** Hides the rows-per-page selector (e.g. for fixed-size embedded tables). */
  hidePageSize?: boolean;
}

/** The parent fetches each page from the API (`offset`/`skip` + `limit`) and passes the total record count. */
export interface ServerPagination extends PaginationBase {
  mode: "server";
  /** One-based. */
  currentPage: number;
  pageSize: number;
  totalRecords: number;
  totalPages?: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}

/** The table slices the full `data` array itself. Page state is internal unless the parent controls it. */
export interface ClientPagination extends PaginationBase {
  mode: "client";
  currentPage?: number;
  pageSize?: number;
  /** Ignored in client mode; derived from `data.length`. */
  totalRecords?: number;
  totalPages?: number;
  onPageChange?: (page: number) => void;
  onPageSizeChange?: (pageSize: number) => void;
  /** Returns to page 1 whenever this value changes (pass the active filters). */
  resetKey?: unknown;
}

export type DataTablePagination = ServerPagination | ClientPagination;

export interface DataTableEmptyState {
  title: string;
  description?: string;
  icon?: LucideIcon;
  action?: ReactNode;
}

export interface DataTableProps<T> {
  columns: readonly DataTableColumn<T>[];
  /** Server mode: the current page. Client mode: every row. */
  data: readonly T[];
  getRowId: (row: T, index: number) => string;
  /** Replaces the body with skeleton rows (first load, or a page change in server mode). */
  isLoading?: boolean;
  /** Keeps rows visible but dims them under a thin progress bar (background refresh). */
  isFetching?: boolean;
  /** Replaces the body when a load failed and there are no rows to keep on screen. */
  error?: string | null;
  onRetry?: () => void;
  pagination?: DataTablePagination | false;
  onRowClick?: (row: T, index: number) => void;
  isRowActive?: (row: T) => boolean;
  rowClassName?: (row: T, index: number) => string;
  emptyState?: DataTableEmptyState | ReactNode;
  /** `card` draws the rounded border; `flush` sits edge-to-edge inside a panel. */
  variant?: "card" | "flush";
  density?: "comfortable" | "compact";
  /** Minimum table width before it scrolls horizontally, e.g. `"760px"`. */
  minWidth?: string;
  /** Pins the header while the table's own container scrolls (`className` must give it a height). */
  stickyHeader?: boolean;
  "aria-label": string;
  className?: string;
  skeletonRows?: number;
}

const alignClass: Record<ColumnAlign, string> = { left: "text-left", center: "text-center", right: "text-right" };
const INTERACTIVE = "a,button,input,select,textarea,label,summary,[role='button'],[role='checkbox'],[role='switch']";

function columnKey<T>(column: DataTableColumn<T>, index: number): string {
  return column.id ?? column.accessorKey ?? `column-${index}`;
}

function widthStyle(width: string | number | undefined): CSSProperties | undefined {
  if (width === undefined) return undefined;
  return { width: typeof width === "number" ? `${width}px` : width };
}

function isEmptyState(value: unknown): value is DataTableEmptyState {
  return typeof value === "object" && value !== null && "title" in value && typeof value.title === "string";
}

export function DataTable<T>({
  columns,
  data,
  getRowId,
  isLoading = false,
  isFetching = false,
  error = null,
  onRetry,
  pagination = false,
  onRowClick,
  isRowActive,
  rowClassName,
  emptyState = { title: "No records found" },
  variant = "card",
  density = "comfortable",
  minWidth,
  stickyHeader = false,
  "aria-label": ariaLabel,
  className = "",
  skeletonRows,
}: DataTableProps<T>) {
  const client = pagination !== false && pagination.mode === "client" ? pagination : null;
  const [innerPage, setInnerPage] = useState(1);
  const [innerSize, setInnerSize] = useState(client?.pageSize ?? DEFAULT_PAGE_SIZE);
  const resetSignature = client ? JSON.stringify(client.resetKey ?? null) : "";
  const lastReset = useRef(resetSignature);
  const onClientPage = useRef(client?.onPageChange);
  onClientPage.current = client?.onPageChange;

  useEffect(() => {
    if (lastReset.current === resetSignature) return;
    lastReset.current = resetSignature;
    setInnerPage(1);
    onClientPage.current?.(1);
  }, [resetSignature]);

  const [sort, setSort] = useState<{ id: string; direction: "asc" | "desc" } | null>(null);
  const clientSort = pagination === false || pagination.mode === "client";
  const rows = useMemo(() => {
    if (!clientSort || sort === null) return data;
    const column = columns.find((item, index) => columnKey(item, index) === sort.id);
    if (!column?.sortValue) return data;
    const read = column.sortValue;
    const factor = sort.direction === "asc" ? 1 : -1;
    return [...data].sort((left, right) => {
      const a = read(left);
      const b = read(right);
      if (a === b) return 0;
      if (a === null) return 1;
      if (b === null) return -1;
      if (typeof a === "number" && typeof b === "number") return (a - b) * factor;
      return String(a).localeCompare(String(b)) * factor;
    });
  }, [clientSort, columns, data, sort]);

  const view = useMemo(() => {
    if (pagination === false) {
      return { rows, page: 1, pageSize: rows.length, totalRecords: rows.length, totalPages: 1 };
    }
    if (pagination.mode === "server") {
      const totalPages = pagination.totalPages ?? pageCount(pagination.totalRecords, pagination.pageSize);
      return {
        rows,
        page: clampPage(pagination.currentPage, totalPages),
        pageSize: pagination.pageSize,
        totalRecords: pagination.totalRecords,
        totalPages,
      };
    }
    const pageSize = pagination.pageSize ?? innerSize;
    const totalPages = pageCount(rows.length, pageSize);
    const page = clampPage(pagination.currentPage ?? innerPage, totalPages);
    const start = (page - 1) * pageSize;
    return { rows: rows.slice(start, start + pageSize), page, pageSize, totalRecords: rows.length, totalPages };
  }, [rows, pagination, innerPage, innerSize]);

  const changePage = (page: number) => {
    const next = clampPage(page, view.totalPages);
    if (next === view.page || pagination === false) return;
    if (pagination.mode === "client") setInnerPage(next);
    pagination.onPageChange?.(next);
  };

  const changePageSize = (size: number) => {
    if (pagination === false) return;
    if (pagination.mode === "client") {
      setInnerSize(size);
      setInnerPage(1);
    }
    pagination.onPageSizeChange?.(size);
    if (pagination.mode === "client") pagination.onPageChange?.(1);
  };

  const pad = density === "compact" ? "py-2" : "py-3";
  const cellX = "px-3 first:pl-4 last:pr-4 sm:first:pl-5 sm:last:pr-5";
  const skeletonCount = skeletonRows ?? Math.min(Math.max(view.rows.length, 5), Math.min(view.pageSize || 8, 10));

  const onRowKey = (event: KeyboardEvent<HTMLTableRowElement>, row: T, index: number) => {
    if (event.target !== event.currentTarget || !onRowClick) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onRowClick(row, index);
    }
  };
  const onRowMouse = (event: MouseEvent<HTMLTableRowElement>, row: T, index: number) => {
    const interactive = (event.target as HTMLElement).closest(INTERACTIVE);
    if (interactive && interactive !== event.currentTarget && event.currentTarget.contains(interactive)) return;
    onRowClick?.(row, index);
  };

  const shell =
    variant === "card"
      ? "overflow-hidden rounded-card border border-line bg-white dark:border-zinc-800 dark:bg-zinc-900"
      : "bg-white dark:bg-zinc-900";

  return (
    <div className={`relative flex min-w-0 flex-col ${shell} ${className}`}>
      {isFetching && !isLoading ? (
        <div aria-hidden="true" className="absolute inset-x-0 top-0 z-20 h-0.5 overflow-hidden bg-primary/15">
          <div className="h-full w-1/3 animate-pulse rounded-full bg-primary" />
        </div>
      ) : null}
      <div className={`min-h-0 flex-1 overflow-x-auto ${stickyHeader ? "overflow-y-auto" : ""}`}>
        <table
          aria-label={ariaLabel}
          aria-busy={isLoading || isFetching}
          className="w-full border-collapse text-left text-sm tabular-nums text-charcoal dark:text-zinc-100"
          style={minWidth ? { minWidth } : undefined}
        >
          <thead className={stickyHeader ? "sticky top-0 z-10" : undefined}>
            <tr className="bg-surface/70 text-[11px] font-semibold uppercase tracking-wider text-[#6B7280] shadow-[inset_0_-1px_0_#DBDBDB] backdrop-blur dark:bg-zinc-900/90 dark:text-zinc-400 dark:shadow-[inset_0_-1px_0_#27272a]">
              {columns.map((column, index) => (
                <th
                  key={columnKey(column, index)}
                  scope="col"
                  aria-sort={
                    sort?.id === columnKey(column, index) ? (sort.direction === "asc" ? "ascending" : "descending") : column.sortValue && clientSort ? "none" : undefined
                  }
                  style={widthStyle(column.width)}
                  className={`${cellX} h-10 whitespace-nowrap font-semibold ${alignClass[column.align ?? "left"]} ${
                    column.headerClassName ?? column.className ?? ""
                  }`}
                >
                  {column.sortValue && clientSort ? (
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 rounded outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
                      onClick={() => {
                        const id = columnKey(column, index);
                        setSort((current) =>
                          current?.id === id
                            ? { id, direction: current.direction === "asc" ? "desc" : "asc" }
                            : { id, direction: "asc" },
                        );
                      }}
                    >
                      {column.header}
                      <span aria-hidden="true" className="text-[10px] text-charcoal/40 dark:text-zinc-500">
                        {sort?.id === columnKey(column, index) ? (sort.direction === "asc" ? "↑" : "↓") : "↕"}
                      </span>
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody
            className={`divide-y divide-line/80 transition-opacity dark:divide-zinc-800 ${
              isFetching && !isLoading ? "opacity-60" : ""
            }`}
          >
            {isLoading
              ? Array.from({ length: skeletonCount }, (_, rowIndex) => (
                  <tr key={`skeleton-${rowIndex}`} aria-hidden="true">
                    {columns.map((column, index) => (
                      <td key={columnKey(column, index)} className={`${cellX} ${pad} ${column.className ?? ""}`}>
                        <div
                          className={`h-4 animate-pulse rounded-full ${
                            index === 0 ? "w-3/4 bg-primary/20" : "bg-charcoal/[0.07] dark:bg-white/[0.07]"
                          } ${column.align === "right" ? "ml-auto w-2/3" : index === 0 ? "" : "w-full"}`}
                          style={{ animationDelay: `${(rowIndex * 60 + index * 25) % 600}ms` }}
                        />
                      </td>
                    ))}
                  </tr>
                ))
              : null}
            {!isLoading && error ? (
              <tr>
                <td colSpan={columns.length} className="px-6 py-14 text-center">
                  <div className="mx-auto flex max-w-sm flex-col items-center">
                    <p className="text-sm font-semibold">Could not load this list</p>
                    <p className="mt-1 text-sm text-charcoal/50 dark:text-zinc-400">{error}</p>
                    {onRetry ? (
                      <button
                        type="button"
                        onClick={onRetry}
                        className="mt-4 rounded-full border border-line px-4 py-2 text-sm font-semibold outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
                      >
                        Try again
                      </button>
                    ) : null}
                  </div>
                </td>
              </tr>
            ) : null}
            {!isLoading && !error && view.rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-6 py-14 text-center">
                  {isEmptyState(emptyState) ? <EmptyState {...emptyState} /> : emptyState}
                </td>
              </tr>
            ) : null}
            {!isLoading && !error
              ? view.rows.map((row, index) => {
                  const active = isRowActive?.(row) ?? false;
                  const rowId = getRowId(row, index);
                  return (
                    <tr
                      key={rowId}
                      data-row-id={rowId}
                      onClick={onRowClick ? (event) => onRowMouse(event, row, index) : undefined}
                      onKeyDown={onRowClick ? (event) => onRowKey(event, row, index) : undefined}
                      tabIndex={onRowClick ? 0 : undefined}
                      aria-selected={isRowActive ? active : undefined}
                      className={`transition-colors ${
                        onRowClick
                          ? "cursor-pointer outline-none focus-visible:bg-primary/[0.04] focus-visible:shadow-[inset_3px_0_0_rgb(var(--primary-rgb))]"
                          : ""
                      } ${
                        active
                          ? "bg-primary/[0.06] shadow-[inset_3px_0_0_rgb(var(--primary-rgb))]"
                          : "hover:bg-surface/60 dark:hover:bg-white/[0.03]"
                      } ${rowClassName?.(row, index) ?? ""}`}
                    >
                      {columns.map((column, columnIndex) => (
                        <td
                          key={columnKey(column, columnIndex)}
                          style={widthStyle(column.width)}
                          className={`${cellX} ${pad} align-middle ${alignClass[column.align ?? "left"]} ${
                            column.className ?? ""
                          }`}
                        >
                          {column.cell
                            ? column.cell(row, index)
                            : column.accessorKey !== undefined
                              ? (row[column.accessorKey] as ReactNode)
                              : null}
                        </td>
                      ))}
                    </tr>
                  );
                })
              : null}
          </tbody>
        </table>
      </div>
      {pagination !== false ? (
        <PaginationFooter
          page={view.page}
          pageSize={view.pageSize}
          totalRecords={view.totalRecords}
          totalPages={view.totalPages}
          pageSizeOptions={pagination.pageSizeOptions ?? PAGE_SIZE_OPTIONS}
          hidePageSize={pagination.hidePageSize ?? false}
          disabled={isLoading}
          onPageChange={changePage}
          onPageSizeChange={changePageSize}
        />
      ) : null}
    </div>
  );
}

function EmptyState({ title, description, icon: Icon = Inbox, action }: DataTableEmptyState) {
  return (
    <div className="mx-auto flex max-w-sm flex-col items-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-surface text-charcoal/40 dark:bg-white/5 dark:text-zinc-500">
        <Icon size={22} aria-hidden="true" />
      </span>
      <p className="mt-3 text-sm font-semibold">{title}</p>
      {description ? <p className="mt-1 text-sm text-charcoal/50 dark:text-zinc-400">{description}</p> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

const navButton =
  "flex h-8 min-w-[2.25rem] shrink-0 items-center justify-center gap-1 rounded-lg border px-2 text-[13px] tabular-nums outline-none transition-colors focus-visible:ring-2 focus-visible:ring-primary/30 disabled:pointer-events-none disabled:opacity-35";
const idleButton =
  "border-transparent font-semibold text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-300 dark:hover:bg-white/5 dark:hover:text-white";
const currentPage = "border-primary/30 bg-primary/10 font-bold text-primary";

export interface PaginationFooterProps {
  page: number;
  pageSize: number;
  totalRecords: number;
  totalPages: number;
  pageSizeOptions?: readonly number[];
  hidePageSize?: boolean;
  disabled?: boolean;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}

/** "Showing 1 to 25 of 383 entries" · rows per page · First / Previous / pages / Next / Last. */
export function PaginationFooter({
  page,
  pageSize,
  totalRecords,
  totalPages,
  pageSizeOptions = PAGE_SIZE_OPTIONS,
  hidePageSize = false,
  disabled = false,
  onPageChange,
  onPageSizeChange,
}: PaginationFooterProps) {
  const labelId = useId();
  const { from, to } = pageRange(page, pageSize, totalRecords);
  const first = page <= 1 || disabled;
  const last = page >= totalPages || disabled;
  const sizes = pageSizeOptions.includes(pageSize) ? pageSizeOptions : [...pageSizeOptions, pageSize].sort((a, b) => a - b);
  const strong = "font-semibold text-zinc-900 dark:text-zinc-100";

  return (
    <nav
      aria-label="Pagination"
      className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 border-t border-zinc-200 bg-white px-6 py-3.5 text-[13px] text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400"
    >
      <p className="whitespace-nowrap tabular-nums" aria-live="polite">
        Showing <span className={strong}>{from.toLocaleString()}</span> to{" "}
        <span className={strong}>{to.toLocaleString()}</span> of{" "}
        <span className={strong}>{totalRecords.toLocaleString()}</span> {totalRecords === 1 ? "entry" : "entries"}
      </p>

      <div className="flex flex-wrap items-center gap-6">
        {hidePageSize ? null : (
          <div className="flex items-center gap-2">
            <span id={labelId} className="whitespace-nowrap">
              Rows per page
            </span>
            <PageSizeSelect
              value={pageSize}
              options={sizes}
              onChange={onPageSizeChange}
              disabled={disabled}
              labelledBy={labelId}
            />
          </div>
        )}

        <div className="flex items-center gap-1">
          <button type="button" className={`${navButton} ${idleButton}`} disabled={first} onClick={() => onPageChange(1)}>
            <ChevronsLeft size={15} aria-hidden="true" />
            <span className="hidden md:inline">First</span>
          </button>
          <button
            type="button"
            className={`${navButton} ${idleButton}`}
            disabled={first}
            onClick={() => onPageChange(page - 1)}
          >
            <ChevronLeft size={15} aria-hidden="true" />
            <span className="hidden md:inline">Previous</span>
          </button>
          <ul className="flex items-center gap-1">
            {pageWindow(page, totalPages).map((item) =>
              typeof item === "number" ? (
                <li key={item}>
                  <button
                    type="button"
                    aria-label={`Page ${item}`}
                    aria-current={item === page ? "page" : undefined}
                    disabled={disabled}
                    onClick={() => onPageChange(item)}
                    className={`${navButton} ${item === page ? currentPage : idleButton}`}
                  >
                    {item.toLocaleString()}
                  </button>
                </li>
              ) : (
                <li
                  key={item}
                  aria-hidden="true"
                  className="flex h-8 min-w-6 items-center justify-center text-zinc-400 dark:text-zinc-500"
                >
                  …
                </li>
              ),
            )}
          </ul>
          <button
            type="button"
            className={`${navButton} ${idleButton}`}
            disabled={last}
            onClick={() => onPageChange(page + 1)}
          >
            <span className="hidden md:inline">Next</span>
            <ChevronRight size={15} aria-hidden="true" />
          </button>
          <button
            type="button"
            className={`${navButton} ${idleButton}`}
            disabled={last}
            onClick={() => onPageChange(totalPages)}
          >
            <span className="hidden md:inline">Last</span>
            <ChevronsRight size={15} aria-hidden="true" />
          </button>
        </div>
      </div>
    </nav>
  );
}
