import { SEARCH_DEBOUNCE_MS } from "@ai-pos/shared-types";
import { Search } from "lucide-react";
import { useCallback, useEffect, useState, type ButtonHTMLAttributes, type ReactNode } from "react";

/** Shared list-search delay. Checkout product search already uses this value. */
export const POS_SEARCH_DEBOUNCE_MS = SEARCH_DEBOUNCE_MS;

export function useDebouncedSearch(value: string, delay = POS_SEARCH_DEBOUNCE_MS) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  const flush = useCallback(() => setDebounced(value), [value]);
  return { debounced, flush, pending: debounced !== value };
}

/** Drops a response when a newer request has already started. */
export function beginRequest(gate: { current: number }) {
  gate.current += 1;
  const id = gate.current;
  return () => id === gate.current;
}

export const posButtonBase =
  "box-border inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:cursor-not-allowed disabled:opacity-40";

/** Shared corner. Icon buttons can be circular; every other action stays a rounded rectangle. */
export const posButtonRadius = "rounded-xl";

export const posButtonSize = {
  sm: "h-9 px-3 text-xs",
  md: "h-12 px-4 text-sm",
  lg: "h-14 px-5 text-base",
} as const;

export const posButtonVariant = {
  primary: "bg-primary text-white hover:bg-primary-hover",
  secondary: "bg-white text-zinc-800 ring-1 ring-zinc-300 hover:bg-zinc-50 dark:bg-zinc-900 dark:text-zinc-100 dark:ring-zinc-700",
  outline: "bg-transparent text-zinc-800 ring-1 ring-zinc-300 hover:bg-zinc-50 dark:text-zinc-100 dark:ring-zinc-600",
  ghost: "bg-transparent text-zinc-700 hover:bg-zinc-100 dark:text-zinc-200 dark:hover:bg-white/10",
  destructive: "bg-red-600 text-white hover:bg-red-700",
} as const;

export const posIconButtonSize = {
  xs: "h-[var(--pos-control-sm)] w-[var(--pos-control-sm)]",
  sm: "h-9 w-9",
  md: "h-12 w-12",
  lg: "h-14 w-14",
} as const;

type ButtonVariant = keyof typeof posButtonVariant;
type ButtonSize = keyof typeof posButtonSize;
type IconSize = keyof typeof posIconButtonSize;

export function PosButton({
  variant = "primary",
  size = "md",
  type = "button",
  className = "",
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: ButtonSize }) {
  return (
    <button type={type} className={`${posButtonBase} ${posButtonRadius} ${posButtonSize[size]} ${posButtonVariant[variant]} ${className}`} {...props}>
      {children}
    </button>
  );
}

export function PosIconButton({
  variant = "secondary",
  size = "md",
  shape = "rounded",
  type = "button",
  label,
  className = "",
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: IconSize;
  shape?: "rounded" | "circle";
  label: string;
}) {
  const radius = shape === "circle" ? "rounded-full" : posButtonRadius;
  return (
    <button
      type={type}
      title={label}
      aria-label={label}
      className={`${posButtonBase} ${radius} ${posIconButtonSize[size]} px-0 ${posButtonVariant[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

const searchSurface = {
  surface: "box-border h-12 w-full rounded-xl border border-zinc-300 bg-white pl-10 pr-3 text-base text-zinc-900 placeholder:text-zinc-400 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:placeholder:text-zinc-500",
  inverse: "box-border h-9 w-full rounded-xl border border-white/10 bg-white/10 pl-9 pr-3 text-sm text-white placeholder:text-white/40 focus:border-white/30 focus:outline-none [&::-webkit-search-cancel-button]:hidden",
} as const;

export function PosSearchInput({
  value,
  onChange,
  placeholder,
  label,
  tone = "surface",
  className = "",
  onCommit,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  label?: string;
  tone?: keyof typeof searchSurface;
  className?: string;
  onCommit?: () => void;
}) {
  return (
    <label className={`relative block min-w-0 ${className}`}>
      <span className="sr-only">{label ?? placeholder}</span>
      <Search aria-hidden="true" className={`pointer-events-none absolute top-1/2 h-[1.125rem] w-[1.125rem] -translate-y-1/2 ${tone === "inverse" ? "left-2.5 text-white/45" : "left-3 text-zinc-400"}`} />
      <input
        type="search"
        value={value}
        placeholder={placeholder}
        aria-label={label ?? placeholder}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            onCommit?.();
          } else if (event.key === "Escape" && value !== "") {
            event.preventDefault();
            onChange("");
            onCommit?.();
          }
        }}
        className={`${searchSurface[tone]} [&::-webkit-search-cancel-button]:hidden`}
      />
    </label>
  );
}

export function PosSearchToolbarFrame({ children }: { children: ReactNode }) {
  return <div className="box-border flex w-full min-w-0 flex-nowrap items-center gap-3">{children}</div>;
}
