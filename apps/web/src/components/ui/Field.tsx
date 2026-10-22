import { useId, type ButtonHTMLAttributes, type InputHTMLAttributes } from "react";
import { Select, type SelectProps } from "./Select";

const control =
  "mt-1.5 w-full rounded-xl border border-transparent bg-surface px-4 py-3 text-sm font-normal text-charcoal transition-colors placeholder:text-charcoal/40 focus:border-accent focus:bg-white focus:outline-none disabled:cursor-not-allowed disabled:text-charcoal/50";

/** Label above every filter-bar control (store, category, status, search). */
export const filterLabel = "mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-[#6B7280]";

export function TextField({
  label,
  hint,
  className = "",
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  return (
    <label className="block text-sm font-medium">
      {label}
      <input {...props} className={`${control} ${className}`} />
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
