import { DateInput, actionButtonClass, actionIntentFromNodes, inputLeadingIcon, type ActionIntent } from "@ai-pos/ui";
import { Eye, EyeOff, X } from "lucide-react";
import { useEffect, useId, useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from "react";

type SpinnerPosition = "leading" | "trailing";

interface BusyButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  loading?: boolean;
  loadingText?: string;
  spinnerPosition?: SpinnerPosition;
}

const primaryTone =
  "inline-flex items-center justify-center gap-2 rounded-full bg-accent px-8 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 disabled:hover:bg-accent";

function ButtonSpinner({ active }: { active: boolean }) {
  if (!active) return <span className="inline-block h-4 w-4 shrink-0" aria-hidden="true" />;
  return (
    <span
      className="inline-block h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-current border-r-transparent motion-reduce:animate-none"
      aria-hidden="true"
    />
  );
}

function BusyButton({
  loading = false,
  loadingText,
  spinnerPosition = "leading",
  className = "",
  disabled,
  children,
  onClick,
  tone,
  ...props
}: BusyButtonProps & { tone: string }) {
  const reserve = loading || loadingText !== undefined;
  return (
    <button
      type="button"
      {...props}
      aria-busy={loading || undefined}
      disabled={Boolean(disabled) || loading}
      onClick={(event) => {
        if (loading || disabled) {
          event.preventDefault();
          return;
        }
        onClick?.(event);
      }}
      className={`${tone} ${loading ? "!opacity-100" : "disabled:opacity-40"} ${className}`}
    >
      {reserve ? (
        <span className="inline-grid items-center justify-items-center whitespace-nowrap">
          <span className={`col-start-1 row-start-1 ${loading ? "invisible" : ""}`} aria-hidden={loading || undefined}>
            {children}
          </span>
          <span
            className={`col-start-1 row-start-1 inline-flex items-center gap-2 ${loading ? "" : "invisible"}`}
            aria-hidden={loading ? undefined : true}
          >
            {spinnerPosition === "leading" ? <ButtonSpinner active={loading} /> : null}
            {loadingText ?? children}
            {spinnerPosition === "trailing" ? <ButtonSpinner active={loading} /> : null}
          </span>
        </span>
      ) : (
        children
      )}
    </button>
  );
}

export function PrimaryButton({ className = "", ...props }: BusyButtonProps) {
  return <BusyButton tone={primaryTone} className={className} {...props} />;
}

export function GhostButton({
  className = "",
  intent,
  children,
  ...props
}: BusyButtonProps & { intent?: ActionIntent }) {
  const named = typeof props["aria-label"] === "string" ? props["aria-label"] : undefined;
  const resolved = intent ?? actionIntentFromNodes(children, named);
  return (
    <BusyButton tone={actionButtonClass(resolved)} className={className} {...props}>
      {children}
    </BusyButton>
  );
}

export function Field({
  label,
  hint,
  error,
  required = false,
  className = "",
  type,
  autoComplete,
  multiline = false,
  rows = 4,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  multiline?: boolean;
  rows?: number;
}) {
  const id = useId();
  const describedBy =
    [props["aria-describedby"], error ? `${id}-error` : hint ? `${id}-hint` : undefined].filter(Boolean).join(" ") || undefined;
  const [showPassword, setShowPassword] = useState(false);
  const isPassword = type === "password";
  const isMultiline = multiline || /\bdescription\b/i.test(label);
  const isDate = type === "date" || type === "datetime-local";
  const fieldClass = `w-full rounded-xl border bg-surface py-3 pl-10 text-sm font-normal text-charcoal transition placeholder:text-charcoal/40 focus:bg-white focus:outline-none focus:ring-2 disabled:cursor-not-allowed disabled:text-charcoal/50 ${
    error ? "border-danger bg-danger/10 focus:border-danger focus:ring-danger" : "border-transparent focus:border-orange-500 focus:ring-orange-500"
  } ${isPassword ? "pr-12" : "pr-4"}`;
  const Icon = inputLeadingIcon({
    type,
    autoComplete: typeof autoComplete === "string" ? autoComplete : undefined,
    inputMode: props.inputMode,
    name: props.name,
    id,
    placeholder: typeof props.placeholder === "string" ? props.placeholder : undefined,
    label,
  });
  return (
    <label htmlFor={id} className={`block text-sm font-medium text-charcoal ${className}`}>
      {label}
      {required ? (
        <span className="text-danger" aria-hidden="true">
          {" "}
          *
        </span>
      ) : null}
      <span className="relative mt-1.5 block">
        <Icon
          className={`pointer-events-none absolute left-3 h-5 w-5 text-gray-400 ${isMultiline ? "top-3.5" : "top-1/2 -translate-y-1/2"}`}
          aria-hidden="true"
        />
        {isMultiline ? (
          <textarea
            id={id}
            rows={rows}
            {...(props as TextareaHTMLAttributes<HTMLTextAreaElement>)}
            aria-required={required || undefined}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedBy}
            className={`min-h-24 w-full resize-y rounded-xl border bg-surface py-3 pl-10 pr-4 text-sm font-normal text-charcoal transition placeholder:text-charcoal/40 focus:bg-white focus:outline-none focus:ring-2 disabled:cursor-not-allowed disabled:text-charcoal/50 ${
              error ? "border-danger focus:border-danger focus:ring-danger" : "border-transparent focus:border-orange-500 focus:ring-orange-500"
            }`}
          />
        ) : isDate ? (
          <DateInput
            id={id}
            withTime={type === "datetime-local"}
            autoComplete={autoComplete}
            {...props}
            value={typeof props.value === "string" ? props.value : ""}
            aria-required={required || undefined}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedBy}
            className={fieldClass}
          />
        ) : (
        <input
          id={id}
          type={isPassword && showPassword ? "text" : type}
          autoComplete={autoComplete}
          {...props}
          required={undefined}
          aria-required={required || undefined}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={fieldClass}
        />
        )}
        {isPassword && !isMultiline ? (
          <button
            type="button"
            tabIndex={-1}
            aria-label={showPassword ? "Hide password" : "Show password"}
            aria-pressed={showPassword}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => setShowPassword((value) => !value)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
          >
            {showPassword ? <EyeOff className="h-5 w-5" aria-hidden="true" /> : <Eye className="h-5 w-5" aria-hidden="true" />}
          </button>
        ) : null}
      </span>
      {error ? (
        <span id={`${id}-error`} role="alert" className="mt-1.5 block text-xs font-normal text-danger">
          {error}
        </span>
      ) : hint ? (
        <span id={`${id}-hint`} className="mt-1.5 block text-xs font-normal text-charcoal/50">
          {hint}
        </span>
      ) : null}
    </label>
  );
}

export function ErrorNote({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="mt-4 rounded-2xl bg-danger/10 px-4 py-3 text-sm text-danger">
      {message}
    </p>
  );
}

const modalHeader =
  "sticky top-0 z-20 flex flex-none items-start justify-between gap-4 border-b border-line bg-white px-6 py-4 sm:px-7";
const modalBody = "min-h-0 flex-1 overflow-y-auto overscroll-contain px-6 py-4 sm:px-7";
const modalFooter =
  "sticky bottom-0 z-20 flex flex-none flex-wrap items-center justify-end gap-3 border-t border-line bg-white px-6 py-4 sm:px-7";

/** Shared dialog shell: title and actions stay visible while the form scrolls. */
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

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  return (
    <div className="modal-backdrop fixed inset-0 z-50 flex items-center justify-center bg-charcoal/40 p-4 backdrop-blur-[8px]" role="presentation">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`modal-card flex max-h-[90vh] w-full flex-col overflow-hidden rounded-3xl bg-white shadow-2xl ${wide ? "max-w-2xl" : "max-w-md"}`}
      >
        <header className={modalHeader}>
          <div className="min-w-0">
            <h2 id={titleId} className="text-xl font-semibold">
              {title}
            </h2>
            {subtitle ? <p className="mt-0.5 text-sm text-charcoal/60">{subtitle}</p> : null}
          </div>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="-mr-1 -mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-charcoal/70 transition-colors hover:bg-gray-100 hover:text-charcoal"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </header>
        <div className={modalBody}>{children}</div>
        {footer ? <footer className={modalFooter}>{footer}</footer> : null}
      </div>
    </div>
  );
}

const STATUS_TONE: Record<string, string> = {
  active: "bg-emerald-50 text-emerald-700",
  suspended: "bg-danger/10 text-danger",
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
