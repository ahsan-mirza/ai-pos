import { Search, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/** Title on the left, search and filters on the right. Matches the Tenants page. */
export function PageHeader({
  icon: Icon,
  title,
  description,
  controls,
}: {
  icon?: LucideIcon;
  title: string;
  description?: ReactNode;
  controls?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex min-w-0 items-center gap-3">
        {Icon ? (
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-charcoal text-white">
            <Icon size={20} aria-hidden="true" />
          </span>
        ) : null}
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold">{title}</h1>
          {description ? <p className="text-sm text-charcoal/60">{description}</p> : null}
        </div>
      </div>
      {controls ? (
        <div className="flex w-full min-w-0 flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center lg:w-auto lg:max-w-full lg:justify-end">
          {controls}
        </div>
      ) : null}
    </div>
  );
}

/** Rounded search field used beside page filters. The label is read by screen readers. */
export function FilterSearch({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <label className="relative w-full min-w-0 sm:w-64 xl:w-72">
      <span className="sr-only">{label}</span>
      <Search size={15} aria-hidden="true" className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-charcoal/40" />
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="h-11 w-full rounded-full border border-line bg-white pl-9 pr-4 text-sm focus:border-accent focus:outline-none"
      />
    </label>
  );
}

/** Gives a dropdown a stable width on desktop and the full row on a phone. */
export function FilterSlot({ children, wide = false }: { children: ReactNode; wide?: boolean }) {
  return <div className={wide ? "w-full sm:w-56" : "w-full sm:w-44"}>{children}</div>;
}
