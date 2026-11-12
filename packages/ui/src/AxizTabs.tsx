import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
} from "react";

/** One navigation tab. Visibility, permissions, and data stay in the parent. */
export interface AxizTabDefinition {
  id: string;
  label: ReactNode;
  icon?: ReactNode;
  badge?: ReactNode;
  disabled?: boolean;
  /** Quieter, but still selectable. Use when the section opens onto a permission message. */
  dimmed?: boolean;
  /** Drop the tab. Parents use this for permissions and entitlements. */
  hidden?: boolean;
  /** Address for a real link, so back and forward keep working. */
  href?: string;
  title?: string;
  busy?: boolean;
}

export interface AxizTabProps {
  id: string;
  role: "tab";
  "aria-selected": boolean;
  "aria-controls"?: string;
  "aria-disabled"?: boolean;
  "aria-busy"?: boolean;
  "data-axiz-tab": string;
  "data-state": "active" | "inactive";
  tabIndex: number;
  className: string;
  title?: string;
  children: ReactNode;
  onClick: (event: MouseEvent<HTMLElement>) => void;
}

export interface AxizTabRenderArgs {
  tab: AxizTabDefinition;
  selected: boolean;
  tabProps: AxizTabProps;
}

export interface AxizTabsProps {
  tabs: readonly AxizTabDefinition[];
  /** Controlled selection. Omit it to let the component keep the selection. */
  activeTab?: string;
  defaultTab?: string;
  onChange?: (id: string) => void;
  ariaLabel: string;
  /**
   * Replace the default button or anchor. Spread `tabProps` onto the element
   * so keyboard focus, ARIA, and the underline stay intact. Used for router links.
   */
  renderTab?: (args: AxizTabRenderArgs) => ReactNode;
  /** Optional panel for the active tab. Leave it unset when the page renders the section itself. */
  children?: ReactNode;
  className?: string;
  listClassName?: string;
  panelClassName?: string;
  /** Kept for existing callers. Tabs sit flush; this no longer adds side padding. */
  inset?: "page" | "compact";
  /** Stable prefix when a panel outside this component needs `aria-labelledby`. */
  idPrefix?: string;
  /** Id of a panel rendered by the parent. Sets `aria-controls` on each tab. */
  controls?: string;
}

const KEYS = new Set(["ArrowRight", "ArrowLeft", "Home", "End"]);

/** Next enabled tab for a horizontal tablist. Arrow keys follow the reading direction. */
export function nextTabId(
  ids: readonly string[],
  currentId: string,
  key: string,
  direction: "ltr" | "rtl",
): string | null {
  if (!KEYS.has(key) || ids.length === 0) return null;
  const index = Math.max(0, ids.indexOf(currentId));
  const forward = direction === "rtl" ? "ArrowLeft" : "ArrowRight";
  const backward = direction === "rtl" ? "ArrowRight" : "ArrowLeft";
  if (key === "Home") return ids[0] ?? null;
  if (key === "End") return ids[ids.length - 1] ?? null;
  if (key === forward) return ids[(index + 1) % ids.length] ?? null;
  if (key === backward) return ids[(index - 1 + ids.length) % ids.length] ?? null;
  return null;
}

function readingDirection(node: HTMLElement): "ltr" | "rtl" {
  let current: HTMLElement | null = node;
  while (current) {
    const dir = current.getAttribute("dir");
    if (dir === "rtl" || dir === "ltr") return dir;
    current = current.parentElement;
  }
  return document.documentElement.getAttribute("dir") === "rtl" ? "rtl" : "ltr";
}

function domId(prefix: string, id: string): string {
  return `${prefix}-tab-${id.replace(/[^A-Za-z0-9_-]/g, "-")}`;
}

function tabClass(selected: boolean, tab: AxizTabDefinition): string {
  return [
    "relative inline-flex h-12 shrink-0 items-center gap-1.5 whitespace-nowrap bg-transparent px-3 text-[13px] outline-none transition-colors motion-reduce:transition-none",
    "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[var(--tab-focus)]",
    selected
      ? "font-semibold text-[var(--tab-text)]"
      : "font-medium text-[var(--tab-text-muted)] hover:text-[var(--tab-hover)]",
    tab.disabled ? "cursor-not-allowed text-[var(--tab-text-disabled)] hover:text-[var(--tab-text-disabled)]" : "",
    tab.dimmed ? "opacity-60" : "",
  ]
    .filter(Boolean)
    .join(" ");
}

/**
 * Page and section navigation. Active tab is charcoal text with the AxizPOS
 * orange underline. Filters and segmented controls stay on their own components.
 */
export function AxizTabs({
  tabs,
  activeTab,
  defaultTab,
  onChange,
  ariaLabel,
  renderTab,
  children,
  className = "",
  listClassName = "",
  panelClassName = "",
  inset = "compact",
  idPrefix,
  controls,
}: AxizTabsProps) {
  const reactId = useId();
  const prefix = idPrefix ?? reactId;
  const scrollerRef = useRef<HTMLDivElement>(null);
  const startRef = useRef<HTMLSpanElement>(null);
  const endRef = useRef<HTMLSpanElement>(null);
  const visible = tabs.filter((tab) => !tab.hidden);
  const controlled = activeTab !== undefined;
  const [uncontrolled, setUncontrolled] = useState(defaultTab ?? visible[0]?.id ?? "");
  const selectedId = controlled ? activeTab : uncontrolled;
  const [focusId, setFocusId] = useState(selectedId);
  const tabStop = visible.some((tab) => tab.id === focusId) ? focusId : selectedId;
  const [edges, setEdges] = useState({ start: false, end: false });
  const panelId = controls ?? (children != null ? `${prefix}-panel` : undefined);
  void inset;
  const gutter = "";

  const select = (id: string) => {
    const tab = visible.find((item) => item.id === id);
    if (!tab || tab.disabled) return;
    setFocusId(id);
    if (!controlled) setUncontrolled(id);
    onChange?.(id);
  };

  useEffect(() => {
    setFocusId(selectedId);
  }, [selectedId]);

  useEffect(() => {
    const root = scrollerRef.current;
    const start = startRef.current;
    const end = endRef.current;
    if (!root || !start || !end || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        setEdges((current) => {
          const next = { ...current };
          for (const entry of entries) {
            if (entry.target === start) next.start = !entry.isIntersecting;
            if (entry.target === end) next.end = !entry.isIntersecting;
          }
          return next.start === current.start && next.end === current.end ? current : next;
        });
      },
      { root, threshold: 1 },
    );
    observer.observe(start);
    observer.observe(end);
    return () => observer.disconnect();
  }, [visible.length]);

  useEffect(() => {
    const node = scrollerRef.current?.querySelector<HTMLElement>(`[data-axiz-tab="${CSS.escape(selectedId)}"]`);
    node?.scrollIntoView({ inline: "nearest", block: "nearest" });
  }, [selectedId, visible.length]);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    const current = (event.target as HTMLElement | null)?.closest?.<HTMLElement>("[data-axiz-tab]");
    if (!current || !scrollerRef.current?.contains(current)) return;
    const id = current.getAttribute("data-axiz-tab") ?? "";
    const tab = visible.find((item) => item.id === id);
    if (!tab) return;
    if (event.key === "Enter" || event.key === " ") {
      if (tab.disabled) {
        event.preventDefault();
        return;
      }
      if (event.key === " " || !tab.href) {
        event.preventDefault();
        if (tab.href && event.key === " ") current.click();
        else select(id);
      }
      return;
    }
    const enabled = visible.filter((item) => !item.disabled).map((item) => item.id);
    const next = nextTabId(enabled, id, event.key, readingDirection(event.currentTarget));
    if (!next) return;
    event.preventDefault();
    setFocusId(next);
    const node = scrollerRef.current?.querySelector<HTMLElement>(`[data-axiz-tab="${CSS.escape(next)}"]`);
    node?.focus();
    node?.scrollIntoView({ inline: "nearest", block: "nearest" });
  };

  return (
    <div className={`relative min-w-0 max-w-full bg-[var(--tab-bg)] ${className}`}>
      <div
        ref={scrollerRef}
        role="tablist"
        aria-label={ariaLabel}
        aria-orientation="horizontal"
        onKeyDown={onKeyDown}
        className={`no-scrollbar flex h-12 w-full min-w-0 flex-nowrap items-stretch gap-1 overflow-x-auto overflow-y-hidden border-b border-[var(--tab-line)] ${gutter} ${listClassName}`}
      >
        <span ref={startRef} className="w-px shrink-0" aria-hidden="true" />
        {visible.map((tab) => {
          const selected = tab.id === selectedId;
          const tabProps: AxizTabProps = {
            id: domId(prefix, tab.id),
            role: "tab",
            "aria-selected": selected,
            "aria-controls": panelId,
            "aria-disabled": tab.disabled || undefined,
            "aria-busy": tab.busy || undefined,
            "data-axiz-tab": tab.id,
            "data-state": selected ? "active" : "inactive",
            tabIndex: tab.id === tabStop ? 0 : -1,
            className: tabClass(selected, tab),
            title: tab.title,
            onClick: (event) => {
              if (tab.disabled) {
                event.preventDefault();
                return;
              }
              select(tab.id);
            },
            children: (
              <>
                {tab.icon ? <span className="inline-flex shrink-0 items-center gap-1.5">{tab.icon}</span> : null}
                <span>{tab.label}</span>
                {tab.badge != null && tab.badge !== false ? (
                  <span className="text-[11px] font-semibold tabular-nums text-[var(--tab-text-muted)]">{tab.badge}</span>
                ) : null}
                <span
                  aria-hidden="true"
                  data-axiz-underline=""
                  className={`pointer-events-none absolute inset-x-3 bottom-0 h-0.5 transition-colors motion-reduce:transition-none ${
                    selected ? "bg-[var(--tab-underline)]" : "bg-transparent"
                  }`}
                />
              </>
            ),
          };
          if (renderTab) {
            return <span key={tab.id} className="contents">{renderTab({ tab, selected, tabProps })}</span>;
          }
          if (tab.href && !tab.disabled) {
            return (
              <a key={tab.id} href={tab.href} {...tabProps}>
                {tabProps.children}
              </a>
            );
          }
          return (
            <button key={tab.id} type="button" {...tabProps}>
              {tabProps.children}
            </button>
          );
        })}
        <span ref={endRef} className="w-px shrink-0" aria-hidden="true" />
      </div>
      {edges.start ? (
        <span
          aria-hidden="true"
          data-axiz-overflow="start"
          className="pointer-events-none absolute inset-y-0 start-0 z-10 w-8 bg-gradient-to-r from-[var(--tab-bg)] to-transparent rtl:bg-gradient-to-l"
        />
      ) : null}
      {edges.end ? (
        <span
          aria-hidden="true"
          data-axiz-overflow="end"
          className="pointer-events-none absolute inset-y-0 end-0 z-10 w-8 bg-gradient-to-l from-[var(--tab-bg)] to-transparent rtl:bg-gradient-to-r"
        />
      ) : null}
      {children != null ? (
        <div role="tabpanel" id={panelId} aria-labelledby={domId(prefix, selectedId)} tabIndex={0} className={`w-full ${panelClassName}`}>
          {children}
        </div>
      ) : null}
    </div>
  );
}
