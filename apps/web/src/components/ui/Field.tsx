import { Eye, EyeOff, Lock, Mail, ShieldCheck, type LucideIcon } from "lucide-react";
import { useId, useState, type ButtonHTMLAttributes, type InputHTMLAttributes } from "react";
import { Select, type SelectProps } from "./Select";

const control =
  "w-full rounded-xl border border-transparent bg-surface py-3 text-sm font-normal text-charcoal transition placeholder:text-charcoal/40 focus:bg-white focus:outline-none disabled:cursor-not-allowed disabled:text-charcoal/50";

function leadingIcon(type: string | undefined, autoComplete: string | undefined): LucideIcon | null {
  if (type === "password") return Lock;
  if (type === "email") return Mail;
  if (autoComplete === "one-time-code") return ShieldCheck;
  return null;
}

/** Label above every filter-bar control (store, category, status, search). */
export const filterLabel = "mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-[#6B7280]";

export function TextField({
  label,
  hint,
  className = "",
  type,
  autoComplete,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  const [showPassword, setShowPassword] = useState(false);
  const isPassword = type === "password";
  const Icon = leadingIcon(type, typeof autoComplete === "string" ? autoComplete : undefined);
  return (
    <label className="block text-sm font-medium">
      {label}
      <span className="relative mt-1.5 block">
        {Icon ? (
          <Icon className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-400" aria-hidden="true" />
        ) : null}
        <input
          {...props}
          type={isPassword && showPassword ? "text" : type}
          autoComplete={autoComplete}
          className={`${control} ${
            Icon
              ? `pl-10 focus:border-orange-500 focus:ring-2 focus:ring-orange-500 ${isPassword ? "pr-12" : "pr-4"}`
              : "px-4 focus:border-accent"
          } ${className}`}
        />
        {isPassword ? (
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
      {hint ? <span className="mt-1.5 block text-xs font-normal text-charcoal/50">{hint}</span> : null}
    </label>
  );
}

type LabelledSelectProps<T extends string> = Omit<SelectProps<T>, "id" | "labelledBy" | "aria-label"> & {
  label: string;
  hint?: string;
};

/** Select inside a form, labelled like `TextField` so mixed rows line up. */
export function SelectField<T extends string>({ label, hint, className = "", ...props }: LabelledSelectProps<T>) {
  const id = useId();
  return (
    <div className={`block ${className}`}>
      <label id={`${id}-label`} htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      <Select {...props} id={id} labelledBy={`${id}-label`} className="mt-1.5" />
      {hint ? <span className="mt-1.5 block text-xs font-normal text-charcoal/50">{hint}</span> : null}
    </div>
  );
}

/** Select in a list page's filter bar. */
export function FilterSelect<T extends string>({ label, hint, className = "", ...props }: LabelledSelectProps<T>) {
  const id = useId();
  return (
    <div className={className}>
      <label id={`${id}-label`} htmlFor={id} className={filterLabel}>
        {label}
      </label>
      <Select {...props} id={id} labelledBy={`${id}-label`} />
      {hint ? <span className="mt-1.5 block text-xs text-charcoal/50">{hint}</span> : null}
    </div>
  );
}

export function PrimaryButton({ children, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...props}
      className="inline-flex items-center justify-center rounded-full bg-accent px-8 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-accent-hover disabled:opacity-40 disabled:hover:bg-accent"
    >
      {children}
    </button>
  );
}

export function GhostButton({ children, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...props}
      className="inline-flex items-center justify-center rounded-full border border-gray-200 bg-white px-6 py-2.5 text-sm font-medium text-black transition-colors hover:bg-gray-50 disabled:opacity-40"
    >
      {children}
    </button>
  );
}

export function ErrorNote({ message }: { message: string | null }) {
  if (message === null) return null;
  return (
    <p role="alert" className="mt-4 rounded-2xl bg-accent/10 px-4 py-3 text-sm text-accent">
      {message}
    </p>
  );
}
