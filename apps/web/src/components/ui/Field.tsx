import { DateInput, inputLeadingIcon } from "@ai-pos/ui";
import { Eye, EyeOff, Search } from "lucide-react";
import { useId, useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { Select, type SelectProps } from "./Select";

const control =
  "w-full rounded-xl border bg-surface py-3 text-sm font-normal text-charcoal transition placeholder:text-charcoal/40 focus:bg-white focus:outline-none disabled:cursor-not-allowed disabled:text-charcoal/50";

/** Label above every filter-bar control (store, category, status, search). */
export const filterLabel = "mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-[#6B7280]";

function isDescriptionLabel(label: string): boolean {
  return /\bdescription\b/i.test(label);
}

export function TextField({
  label,
  hint,
  error,
  required = false,
  className = "",
  type,
  autoComplete,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string; error?: string; required?: boolean }) {
  const id = useId();
  const fieldId = props.id ?? id;
  const describedBy =
    [props["aria-describedby"], error ? `${fieldId}-error` : hint ? `${fieldId}-hint` : undefined].filter(Boolean).join(" ") ||
    undefined;
  const [showPassword, setShowPassword] = useState(false);
  const isPassword = type === "password";
  const Icon = inputLeadingIcon({
    type,
    autoComplete: typeof autoComplete === "string" ? autoComplete : undefined,
    inputMode: props.inputMode,
    name: props.name,
    id: props.id,
    placeholder: typeof props.placeholder === "string" ? props.placeholder : undefined,
    label,
  });
  const multiline = isDescriptionLabel(label);
  const isDate = type === "date" || type === "datetime-local";
  const controlClass = `${control} pl-10 ${
    error
      ? `border-danger bg-danger/10 focus:border-danger focus:ring-2 focus:ring-danger ${isPassword ? "pr-12" : "pr-4"}`
      : `border-transparent focus:border-orange-500 focus:ring-2 focus:ring-orange-500 ${isPassword ? "pr-12" : "pr-4"}`
  } ${className}`;
  return (
    <label htmlFor={multiline ? undefined : fieldId} className="block text-sm font-medium">
      {label}
      {required ? (
        <span className="text-danger" aria-hidden="true">
          {" "}
          *
        </span>
      ) : null}
      <span className="relative mt-1.5 block">
        <Icon
          className={`pointer-events-none absolute left-3 z-10 h-5 w-5 text-gray-400 ${multiline ? "top-3.5" : "top-1/2 -translate-y-1/2"}`}
          aria-hidden="true"
        />
        {multiline ? (
          <textarea
            {...(props as TextareaHTMLAttributes<HTMLTextAreaElement>)}
            id={fieldId}
            rows={3}
            aria-required={required || undefined}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedBy}
            className={`${control} min-h-24 resize-y border-transparent py-3 pl-10 pr-4 focus:border-orange-500 focus:ring-2 focus:ring-orange-500 ${
              error ? "border-danger bg-danger/10 focus:border-danger focus:ring-danger" : ""
            } ${className}`}
          />
        ) : isDate ? (
          <DateInput
            {...props}
            id={fieldId}
            withTime={type === "datetime-local"}
            value={typeof props.value === "string" ? props.value : ""}
            autoComplete={autoComplete}
            aria-required={required || undefined}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedBy}
            className={controlClass}
          />
        ) : (
        <input
          {...props}
          id={fieldId}
          type={isPassword && showPassword ? "text" : type}
          autoComplete={autoComplete}
          required={undefined}
          aria-required={required || undefined}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={controlClass}
        />
        )}
        {isPassword && !multiline ? (
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
        <span id={`${fieldId}-error`} role="alert" className="mt-1.5 block text-xs font-medium text-danger">
          {error}
        </span>
      ) : hint ? (
        <span id={`${fieldId}-hint`} className="mt-1.5 block text-xs font-normal text-charcoal/50">
          {hint}
        </span>
      ) : null}
    </label>
  );
}

type LabelledSelectProps<T extends string> = Omit<SelectProps<T>, "id" | "labelledBy" | "aria-label"> & {
  label: string;
  hint?: string;
  error?: string;
};

/** Filter-bar search. The icon lives here so every list search looks the same. */
export function SearchField({
  label = "Search",
  hideLabel = false,
  className = "",
  ...props
}: Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & { label?: string; hideLabel?: boolean }) {
  const id = useId();
  const fieldId = props.id ?? id;
  return (
    <label htmlFor={fieldId} className={className}>
      <span className={hideLabel ? "sr-only" : filterLabel}>{label}</span>
      <span className="relative block">
        <Search aria-hidden="true" className="pointer-events-none absolute left-4 top-1/2 z-10 h-4 w-4 -translate-y-1/2 text-charcoal/40" />
        <input
          {...props}
          id={fieldId}
          type="search"
          className="h-11 w-full rounded-full border border-line bg-white pl-10 pr-4 text-sm font-medium text-charcoal transition-all placeholder:font-normal placeholder:text-charcoal/40 hover:border-gray-400 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20 [&::-webkit-search-cancel-button]:hidden"
        />
      </span>
    </label>
  );
}

/** Select inside a form, labelled like `TextField` so mixed rows line up. */
export function SelectField<T extends string>({
  label,
  hint,
  error,
  required = false,
  className = "",
  ...props
}: LabelledSelectProps<T> & { required?: boolean }) {
  const id = useId();
  return (
    <div className={`block ${className}`}>
      <label id={`${id}-label`} htmlFor={id} className="block text-sm font-medium">
        {label}
        {required ? (
          <span className="text-danger" aria-hidden="true">
            {" "}
            *
          </span>
        ) : null}
      </label>
      <Select
        {...props}
        id={id}
        labelledBy={`${id}-label`}
        invalid={Boolean(error)}
        className="mt-1.5"
      />
      {error ? (
        <span id={`${id}-error`} role="alert" className="mt-1.5 block text-xs font-medium text-danger">
          {error}
        </span>
      ) : hint ? (
        <span id={`${id}-hint`} className="mt-1.5 block text-xs font-normal text-charcoal/50">
          {hint}
        </span>
      ) : null}
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
    <p role="alert" className="mt-4 rounded-2xl bg-danger/10 px-4 py-3 text-sm text-danger">
      {message}
    </p>
  );
}
