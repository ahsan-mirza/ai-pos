import { MoreVertical, type LucideIcon } from "lucide-react";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";

export interface RowActionItem {
  id: string;
  label: string;
  icon?: LucideIcon;
  onSelect: () => void;
  /** Omit the action for this role or record state. */
  hidden?: boolean;
  disabled?: boolean;
  /** Shown on a disabled action, for example a consolidated-stock hint. */
  title?: string;
  tone?: "default" | "danger";
}

interface Placement {
  left: number;
  top?: number;
  bottom?: number;
  maxHeight: number;
}

const EDGE = 8;
const GAP = 6;
const MENU_WIDTH = 224;

function place(trigger: HTMLElement): Placement {
  const rect = trigger.getBoundingClientRect();
  const rtl = document.documentElement.dir === "rtl";
  const preferred = rtl ? rect.left : rect.right - MENU_WIDTH;
  const left = Math.max(EDGE, Math.min(preferred, window.innerWidth - MENU_WIDTH - EDGE));
  const below = window.innerHeight - rect.bottom - GAP - EDGE;
  const above = rect.top - GAP - EDGE;
  if (below >= 160 || below >= above) {
    return { left, top: rect.bottom + GAP, maxHeight: Math.max(120, below) };
  }
  return { left, bottom: window.innerHeight - rect.top + GAP, maxHeight: Math.max(120, above) };
}

/** One kebab control. The menu is portalled so a scrolling table cannot clip it. */
export function RowActionsMenu({ label, actions }: { label: string; actions: readonly RowActionItem[] }) {
  const menuId = useId();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [placement, setPlacement] = useState<Placement | null>(null);
  const [active, setActive] = useState(0);
  const visible = actions.filter((action) => !action.hidden);

  useEffect(() => {
    if (!open || buttonRef.current === null) return;
    const reposition = () => {
      if (buttonRef.current) setPlacement(place(buttonRef.current));
    };
    reposition();
    const dismiss = (event: PointerEvent) => {
      const target = event.target as Node;
      if (menuRef.current?.contains(target) || buttonRef.current?.contains(target)) return;
      setOpen(false);
    };
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    document.addEventListener("pointerdown", dismiss);
    return () => {
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
      document.removeEventListener("pointerdown", dismiss);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const index = visible.findIndex((action) => !action.disabled);
    setActive(index < 0 ? 0 : index);
    menuRef.current?.focus();
  }, [open, visible.length]);

  if (visible.length === 0) return null;

  const close = (restore: boolean) => {
    setOpen(false);
    if (restore) buttonRef.current?.focus();
  };

  const choose = (action: RowActionItem) => {
    if (action.disabled) return;
    close(true);
    action.onSelect();
  };

  const onMenuKey = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((index) => nextEnabled(visible, index, 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((index) => nextEnabled(visible, index, -1));
    } else if (event.key === "Home") {
      event.preventDefault();
      setActive(nextEnabled(visible, -1, 1));
    } else if (event.key === "End") {
      event.preventDefault();
      setActive(nextEnabled(visible, visible.length, -1));
    } else if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      close(true);
    } else if (event.key === "Tab") {
      close(false);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      const action = visible[active];
      if (action) choose(action);
    }
  };

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={label}
        onClick={(event) => {
          event.stopPropagation();
          setOpen((value) => !value);
        }}
        className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-line bg-white text-charcoal outline-none hover:bg-surface focus-visible:ring-2 focus-visible:ring-primary/40 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
      >
        <MoreVertical size={18} aria-hidden="true" />
      </button>
      {open && placement
        ? createPortal(
            <div
              ref={menuRef}
              id={menuId}
              role="menu"
              tabIndex={-1}
              aria-label={label}
              onKeyDown={onMenuKey}
              style={{
                left: placement.left,
                width: `min(14rem, calc(100vw - 1rem))`,
                top: placement.top,
                bottom: placement.bottom,
                maxHeight: placement.maxHeight,
              }}
              className="fixed z-[90] overflow-y-auto rounded-2xl border border-line bg-white p-1.5 text-sm shadow-xl outline-none dark:border-zinc-700 dark:bg-zinc-900"
            >
              {visible.map((action, index) => {
                const Icon = action.icon;
                const danger = action.tone === "danger";
                return (
                  <button
                    key={action.id}
                    type="button"
                    role="menuitem"
                    title={action.title}
                    disabled={action.disabled}
                    tabIndex={-1}
                    onMouseEnter={() => setActive(index)}
                    onClick={(event) => {
                      event.stopPropagation();
                      choose(action);
                    }}
                    className={`flex min-h-11 w-full items-center gap-2 rounded-xl px-3 text-start font-medium outline-none disabled:cursor-not-allowed disabled:opacity-40 ${
                      danger ? "text-danger" : "text-charcoal dark:text-zinc-100"
                    } ${index === active ? "bg-surface dark:bg-white/10" : ""}`}
                  >
                    {Icon ? <Icon size={16} aria-hidden="true" className="shrink-0" /> : null}
                    <span className="min-w-0 truncate">{action.label}</span>
                  </button>
                );
              })}
            </div>,
            document.body,
          )
        : null}
    </>
  );
}

function nextEnabled(actions: readonly RowActionItem[], from: number, direction: 1 | -1): number {
  for (let index = from + direction; index >= 0 && index < actions.length; index += direction) {
    if (!actions[index]?.disabled) return index;
  }
  return from < 0 ? 0 : from >= actions.length ? Math.max(actions.length - 1, 0) : from;
}
