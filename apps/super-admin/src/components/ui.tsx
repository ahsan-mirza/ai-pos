import { X } from "lucide-react";
import { useEffect, useId, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from "react";

export function PrimaryButton({ className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...props}
      className={`inline-flex h-10 items-center justify-center gap-2 rounded-full bg-accent px-5 text-sm font-semibold text-white transition hover:bg-accent/90 disabled:opacity-50 ${className}`}
    />
  );
}

export function GhostButton({ className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...props}
      className={`inline-flex h-10 items-center justify-center gap-2 rounded-full border border-line px-4 text-sm font-semibold text-charcoal transition hover:border-charcoal/30 disabled:opacity-50 ${className}`}
    />
  );
}

export function Field({
  label,
  hint,
  className = "",
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  const id = useId();
  return (
    <label htmlFor={id} className={`block text-sm font-medium text-charcoal ${className}`}>
      {label}
      <input
        id={id}
        {...props}
        className="mt-1.5 h-11 w-full rounded-2xl border border-line bg-white px-3.5 text-sm text-charcoal placeholder:text-charcoal/40 focus:border-accent focus:outline-none focus:ring-4 focus:ring-accent/15"
      />
      {hint ? <span className="mt-1 block text-xs font-normal text-charcoal/50">{hint}</span> : null}
    </label>
  );
}

export function ErrorNote({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="mt-3 rounded-2xl bg-accent/10 px-4 py-2.5 text-sm text-accent">
      {message}
    </p>
  );
}

/** Frosted modal: blurred backdrop, rounded-3xl card; Escape closes it. */
export function Modal({
  title,
  subtitle,
  onClose,
  children,
  footer,
  wide = false,
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  const titleId = useId();
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="frost fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm" role="presentation">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`frost-card flex max-h-[90vh] w-full flex-col overflow-hidden rounded-3xl bg-white shadow-2xl ${wide ? "max-w-2xl" : "max-w-lg"}`}
      >
        <header className="sticky top-0 z-20 flex flex-none items-start justify-between gap-4 border-b border-line bg-white px-6 py-4">
          <div className="min-w-0">
            <h2 id={titleId} className="text-xl font-semibold text-charcoal">
              {title}
            </h2>
            {subtitle ? <p className="mt-1 text-sm text-charcoal/60">{subtitle}</p> : null}
          </div>
          <button type="button" aria-label="Close" onClick={onClose} className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full hover:bg-surface">
            <X size={18} aria-hidden="true" />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">{children}</div>
        {footer ? (
          <footer className="sticky bottom-0 z-20 flex flex-none flex-wrap items-center justify-end gap-3 border-t border-line bg-white px-6 py-4">
            {footer}
          </footer>
        ) : null}
      </div>
    </div>
  );
}

const STATUS_TONE: Record<string, string> = {
  active: "bg-emerald-50 text-emerald-700",
  suspended: "bg-accent/10 text-accent",
  PENDING: "bg-amber-50 text-amber-700",
  RESOLVED: "bg-emerald-50 text-emerald-700",
  REJECTED: "bg-surface text-charcoal/60",
};

export function StatusBadge({ value }: { value: string }) {
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider ${STATUS_TONE[value] ?? "bg-surface text-charcoal/70"}`}>
      {value.toLowerCase()}
    </span>
  );
}

export function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-2xl bg-surface px-4 py-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-charcoal/50">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums text-charcoal">{value}</p>
    </div>
  );
}
