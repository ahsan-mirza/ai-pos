import { RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import { PosButton, PosIconButton, PosSearchInput } from "../../components/shell/posControls";
import { inventoryTableClass, inventoryTableFrameClass } from "./layout";

export function Banner({ tone, children }: { tone: "info" | "error" | "ok"; children: ReactNode }) {
  const color =
    tone === "error"
      ? "bg-red-50 text-red-800 dark:bg-red-950/40 dark:text-red-200"
      : tone === "ok"
        ? "bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200"
        : "bg-amber-50 text-amber-900 dark:bg-amber-950/40 dark:text-amber-100";
  return <p className={`rounded-xl px-3 py-2 text-sm ${color}`}>{children}</p>;
}

export function Field({
  label,
  hint,
  error,
  required,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-zinc-600 dark:text-zinc-300">
        {label}
        {required ? <span className="text-primary-600"> *</span> : null}
      </span>
      {children}
      {error ? (
        <span role="alert" className="mt-1 block text-xs font-medium text-red-700 dark:text-red-300">
          {error}
        </span>
      ) : hint ? (
        <span className="mt-1 block text-xs text-zinc-500">{hint}</span>
      ) : null}
    </label>
  );
}

export const control =
  "h-12 w-full rounded-xl border border-zinc-300 bg-white px-3 text-base dark:border-zinc-700 dark:bg-zinc-900";

export function FilterSearch({
  value,
  onChange,
  placeholder,
  className = "min-w-[12rem] max-w-xs flex-1",
  onCommit,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  className?: string;
  onCommit?: () => void;
}) {
  return <PosSearchInput className={className} value={value} onChange={onChange} placeholder={placeholder} onCommit={onCommit} />;
}

export const posSearchToolbarClass = "box-border flex w-full min-w-0 flex-nowrap items-center gap-3";
export const posSearchToolbarSearchClass = "box-border min-w-[11.25rem] flex-1";
export const posSearchToolbarStatusClass =
  "box-border h-12 w-auto min-w-[11.25rem] max-w-[16rem] shrink rounded-xl border border-zinc-300 bg-white bg-[length:1rem_1rem] bg-[position:right_1rem_center] bg-no-repeat pl-3 pr-12 text-base text-zinc-900 appearance-none dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";
export const posSearchToolbarRefreshClass = "h-12 w-12 shrink-0 rounded-xl";

const statusChevron =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%2371717a' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")";

/** Search, optional status filter, and icon-only refresh on one row. */
export function PosSearchToolbar({
  query,
  onQuery,
  placeholder,
  statusValue,
  onStatus,
  statusLabel = "Status",
  statusOptions,
  onRefresh,
  refreshing = false,
  refreshDisabled = false,
  onCommit,
}: {
  query: string;
  onQuery: (value: string) => void;
  placeholder: string;
  statusValue?: string;
  onStatus?: (value: string) => void;
  statusLabel?: string;
  statusOptions?: readonly { value: string; label: string }[];
  onRefresh?: () => void;
  refreshing?: boolean;
  refreshDisabled?: boolean;
  onCommit?: () => void;
}) {
  return (
    <div className={posSearchToolbarClass}>
      <FilterSearch className={posSearchToolbarSearchClass} placeholder={placeholder} value={query} onChange={onQuery} onCommit={onCommit} />
      {statusOptions && onStatus ? (
        <select
          className={posSearchToolbarStatusClass}
          style={{ backgroundImage: statusChevron }}
          aria-label={statusLabel}
          value={statusValue ?? ""}
          onChange={(event) => onStatus(event.target.value)}
        >
          {statusOptions.map((option) => (
            <option key={option.value || "all"} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      ) : null}
      {onRefresh ? (
        <PosIconButton className={posSearchToolbarRefreshClass} label="Refresh results" title="Refresh" disabled={refreshDisabled} onClick={onRefresh}>
          <RefreshCw size={18} aria-hidden="true" className={refreshing ? "animate-spin" : ""} />
        </PosIconButton>
      ) : null}
    </div>
  );
}

export function PrimaryButton({
  children,
  disabled,
  onClick,
  type = "button",
  form,
}: {
  children: ReactNode;
  disabled?: boolean;
  onClick?: () => void;
  type?: "button" | "submit";
  form?: string;
}) {
  return (
    <PosButton type={type} form={form} disabled={disabled} onClick={onClick}>
      {children}
    </PosButton>
  );
}

export function QuietButton({ children, onClick, disabled }: { children: ReactNode; onClick?: () => void; disabled?: boolean }) {
  return (
    <PosButton variant="secondary" disabled={disabled} onClick={onClick}>
      {children}
    </PosButton>
  );
}

export function Table({ headers, children }: { headers: string[]; children: ReactNode }) {
  return (
    <div className={inventoryTableFrameClass}>
      <table className={inventoryTableClass}>
        <thead className="bg-zinc-50 text-xs uppercase tracking-wide text-zinc-500 dark:bg-zinc-900">
          <tr>
            {headers.map((header) => (
              <th key={header} className="break-words px-3 py-2 font-semibold">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800 [&_td]:break-words [&_td]:px-3 [&_td]:py-2">{children}</tbody>
      </table>
    </div>
  );
}

/** Near full-screen product form. Business Pro uses one scrolling body and a fixed footer, not a side drawer. */
export function FormModal({
  title,
  subtitle,
  onClose,
  children,
  footer,
  headerExtra,
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  headerExtra?: ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-[#1A191D]/60 p-3" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="flex h-[96vh] max-h-[96vh] w-[96vw] min-w-0 max-w-6xl flex-col overflow-hidden rounded-3xl bg-white shadow-xl dark:bg-zinc-950"
      >
        <div className="shrink-0 border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <h2 className="text-xl font-semibold">{title}</h2>
              {subtitle ? <p className="mt-1 text-sm text-zinc-500">{subtitle}</p> : null}
            </div>
            <QuietButton onClick={onClose}>Close</QuietButton>
          </div>
          {headerExtra}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-5">{children}</div>
        {footer ? <div className="shrink-0 border-t border-zinc-200 p-4 dark:border-zinc-800">{footer}</div> : null}
      </div>
    </div>
  );
}

export function Drawer({
  title,
  onClose,
  children,
  footer,
  wide = false,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/30" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`flex h-full w-full flex-col bg-white shadow-xl dark:bg-zinc-950 ${wide ? "max-w-3xl" : "max-w-md"}`}
      >
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
          <h2 className="text-lg font-semibold">{title}</h2>
          <QuietButton onClick={onClose}>Close</QuietButton>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">{children}</div>
        {footer ? <div className="shrink-0 border-t border-zinc-200 p-4 dark:border-zinc-800">{footer}</div> : null}
      </div>
    </div>
  );
}
