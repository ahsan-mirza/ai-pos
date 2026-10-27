import { ChevronDown } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { DateInput } from "./DateInput";
import { Select, type SelectOption } from "./Select";

const field = "!w-auto min-w-0 max-w-[10.5rem] shrink-0 basis-[8.75rem]";
const trigger =
  "inline-flex h-11 min-w-[8.75rem] max-w-[10.5rem] shrink-0 items-center justify-between gap-2 rounded-2xl border border-gray-200 bg-gray-50 px-3 text-sm font-medium text-charcoal hover:border-gray-300 focus:outline-none focus:ring-2 focus:ring-orange-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

export interface RepairJobsToolbarProps {
  search: string;
  onSearch: (value: string) => void;
  status: string;
  onStatus: (value: string) => void;
  statusOptions: readonly SelectOption[];
  type?: string;
  onType?: (value: string) => void;
  typeOptions?: readonly SelectOption[];
  from?: string;
  to?: string;
  onFrom?: (value: string) => void;
  onTo?: (value: string) => void;
  technician?: string;
  onTechnician?: (value: string) => void;
  technicianOptions?: readonly SelectOption[];
  /** Warranty and any other secondary control. Stays inside More filters. */
  more?: ReactNode;
  onClear?: () => void;
  clearVisible?: boolean;
  /** True when a control that lives inside More filters on large screens is set. */
  moreActive?: boolean;
  action?: ReactNode;
}

function datesSet(from?: string, to?: string): boolean {
  return Boolean(from || to);
}

/** Search, the repair filters that exist, and the page action on one row. */
export function RepairJobsToolbar({
  search,
  onSearch,
  status,
  onStatus,
  statusOptions,
  type,
  onType,
  typeOptions,
  from,
  to,
  onFrom,
  onTo,
  technician,
  onTechnician,
  technicianOptions,
  more,
  onClear,
  clearVisible = false,
  moreActive = false,
  action,
}: RepairJobsToolbarProps) {
  const hasType = typeOptions != null && onType != null && type != null;
  const hasDates = onFrom != null && onTo != null;
  const hasTechnician = technicianOptions != null && onTechnician != null && technician != null;
  const collapsedActive = (hasType && type !== "") || datesSet(from, to) || (hasTechnician && technician !== "");
  const showMenu = hasType || hasDates || hasTechnician || more != null;

  return (
    <div className="@container w-full min-w-0">
    <div className="flex w-full min-w-0 flex-wrap items-center gap-2 @[640px]:flex-nowrap">
      <input
        value={search}
        onChange={(event) => onSearch(event.target.value)}
        placeholder="Search repairs..."
        aria-label="Search repair jobs"
        className="h-11 w-full min-w-0 rounded-2xl border border-gray-200 bg-gray-50 px-4 text-sm text-charcoal outline-none placeholder:text-gray-400 focus:border-orange-500 focus:ring-2 focus:ring-orange-500 @[640px]:w-auto @[640px]:min-w-[12rem] @[640px]:flex-[1_1_240px] dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:placeholder:text-zinc-500"
      />
      <Select aria-label="Status" className={field} value={status} onChange={onStatus} options={statusOptions} />
      <div className="hidden @[1080px]:contents">
        {hasType ? <Select aria-label="Repair type" className={field} value={type} onChange={onType} options={typeOptions} /> : null}
        {hasDates ? <DateRange from={from ?? ""} to={to ?? ""} onFrom={onFrom} onTo={onTo} /> : null}
        {hasTechnician ? (
          <Select aria-label="Technician" className={field} value={technician} onChange={onTechnician} options={technicianOptions} />
        ) : null}
      </div>
      {showMenu ? (
        <FilterMenu
          collapsedActive={collapsedActive}
          moreActive={moreActive}
          hideOnLarge={!more}
        >
          <div className="grid gap-3 @[1080px]:hidden">
            {hasType ? <Select aria-label="Repair type" value={type} onChange={onType} options={typeOptions} /> : null}
            {hasDates ? (
              <div className="grid gap-2">
                <DateInput aria-label="Received from" value={from ?? ""} onChange={(event) => onFrom(event.target.value)} className={dateField} />
                <DateInput aria-label="Received to" value={to ?? ""} onChange={(event) => onTo(event.target.value)} className={dateField} />
              </div>
            ) : null}
            {hasTechnician ? (
              <Select aria-label="Technician" value={technician} onChange={onTechnician} options={technicianOptions} />
            ) : null}
          </div>
          {more}
        </FilterMenu>
      ) : null}
      {clearVisible && onClear ? (
        <button type="button" onClick={onClear} className="h-11 shrink-0 px-2 text-sm font-semibold text-charcoal hover:underline focus:outline-none focus:ring-2 focus:ring-orange-500 dark:text-zinc-100">
          Clear
        </button>
      ) : null}
      {action ? <div className="ml-auto shrink-0 @[640px]:ml-0">{action}</div> : null}
    </div>
    </div>
  );
}

const dateField =
  "h-11 w-full rounded-xl border border-gray-200 bg-white px-3 text-sm text-charcoal focus:outline-none focus:ring-2 focus:ring-orange-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

function DateRange({ from, to, onFrom, onTo }: { from: string; to: string; onFrom: (value: string) => void; onTo: (value: string) => void }) {
  return (
    <FilterMenu label="Date range" active={datesSet(from, to)} panelClass="w-64">
      <div className="grid gap-2">
        <DateInput aria-label="Received from" value={from} onChange={(event) => onFrom(event.target.value)} className={dateField} />
        <DateInput aria-label="Received to" value={to} onChange={(event) => onTo(event.target.value)} className={dateField} />
      </div>
    </FilterMenu>
  );
}

function FilterMenu({
  label = "More filters",
  active = false,
  collapsedActive = false,
  moreActive = false,
  hideOnLarge = false,
  panelClass = "w-72",
  children,
}: {
  label?: string;
  active?: boolean;
  collapsedActive?: boolean;
  moreActive?: boolean;
  hideOnLarge?: boolean;
  panelClass?: string;
  children: ReactNode;
}) {
  const panelId = useId();
  const root = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const close = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const marked = active || moreActive;
  return (
    <div ref={root} className={`relative shrink-0 ${hideOnLarge ? "@[1080px]:hidden" : ""}`}>
      <button
        type="button"
        className={trigger}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
      >
        {collapsedActive && !marked ? <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-orange-500 @[1080px]:hidden" /> : null}
        {marked ? <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-orange-500" /> : null}
        <span className="truncate">{label}</span>
        <ChevronDown aria-hidden="true" className="h-4 w-4 shrink-0 text-gray-500" />
      </button>
      {open ? (
        <div id={panelId} className={`absolute left-0 top-12 z-30 rounded-2xl border border-gray-200 bg-white p-3 shadow-lg dark:border-zinc-700 dark:bg-zinc-900 ${panelClass}`}>
          {children}
        </div>
      ) : null}
    </div>
  );
}
