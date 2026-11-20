import type { ReactNode } from "react";
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
    <button
      type={type}
      form={form}
      disabled={disabled}
      onClick={onClick}
      className="h-12 rounded-xl bg-primary-500 px-4 text-sm font-semibold text-white disabled:opacity-40"
    >
      {children}
    </button>
  );
}

export function QuietButton({ children, onClick, disabled }: { children: ReactNode; onClick?: () => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="h-12 rounded-xl px-3 text-sm font-semibold text-zinc-700 ring-1 ring-zinc-300 disabled:opacity-40 dark:text-zinc-200 dark:ring-zinc-700"
    >
      {children}
    </button>
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
