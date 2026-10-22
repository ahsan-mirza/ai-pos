import { Check, ChevronDown } from "lucide-react";
import { useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";

const GAP = 6;
const ROW = 40;

interface Placement {
  left: number;
  width: number;
  top?: number;
  bottom?: number;
}

/** Compact pill listbox for "rows per page"; the menu is portalled with fixed coordinates so tables cannot clip it. */
export function PageSizeSelect({
  value,
  options,
  onChange,
  disabled = false,
  label = "Rows per page",
  labelledBy,
}: {
  value: number;
  options: readonly number[];
  onChange: (value: number) => void;
  disabled?: boolean;
  label?: string;
  /** Id of a visible label beside the trigger; replaces the built-in aria-label. */
  labelledBy?: string;
}) {
  const id = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(Math.max(0, options.indexOf(value)));
  const [placement, setPlacement] = useState<Placement | null>(null);

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return;
    const place = () => {
      const rect = triggerRef.current!.getBoundingClientRect();
      const height = options.length * ROW + 12;
      const width = Math.max(rect.width, 96);
      const left = Math.min(rect.left, window.innerWidth - width - 8);
      setPlacement(
        window.innerHeight - rect.bottom >= height + GAP
          ? { left, width, top: rect.bottom + GAP }
          : { left, width, bottom: window.innerHeight - rect.top + GAP },
      );
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open, options.length]);

  useEffect(() => {
    if (!open) return;
    listRef.current?.focus();
    const onPointer = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!triggerRef.current?.contains(target) && !listRef.current?.contains(target)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [open]);

  const choose = (index: number) => {
    const next = options[index];
    setOpen(false);
    triggerRef.current?.focus();
    if (next !== undefined && next !== value) onChange(next);
  };

  const openMenu = () => {
    setActive(Math.max(0, options.indexOf(value)));
    setOpen(true);
  };

  const onTriggerKey = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) {
      event.preventDefault();
      openMenu();
    }
  };

  const onListKey = (event: KeyboardEvent<HTMLUListElement>) => {
    if (event.key === "ArrowDown") setActive((index) => Math.min(options.length - 1, index + 1));
    else if (event.key === "ArrowUp") setActive((index) => Math.max(0, index - 1));
    else if (event.key === "Home") setActive(0);
    else if (event.key === "End") setActive(options.length - 1);
    else if (event.key === "Enter" || event.key === " ") choose(active);
    else if (event.key === "Escape" || event.key === "Tab") {
      setOpen(false);
      if (event.key === "Escape") triggerRef.current?.focus();
      return;
    } else return;
    event.preventDefault();
  };

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? `${id}-list` : undefined}
        aria-labelledby={labelledBy ? `${labelledBy} ${id}-value` : undefined}
        aria-label={labelledBy ? undefined : `${label}: ${value}`}
        onClick={() => (open ? setOpen(false) : openMenu())}
        onKeyDown={onTriggerKey}
        className={`inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg border bg-white pl-3 pr-2 text-[13px] font-semibold tabular-nums text-zinc-900 outline-none transition-colors disabled:cursor-not-allowed disabled:opacity-50 dark:bg-zinc-900 dark:text-zinc-100 ${
          open
            ? "border-primary ring-2 ring-primary/20"
            : "border-zinc-200 hover:border-zinc-300 focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/20 dark:border-zinc-700 dark:hover:border-zinc-600"
        }`}
      >
        <span id={`${id}-value`} className="min-w-[1.5rem] text-left">
          {value}
        </span>
        <ChevronDown
          size={14}
          strokeWidth={2.25}
          aria-hidden="true"
          className={`shrink-0 text-zinc-400 transition-transform duration-200 dark:text-zinc-500 ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && placement
        ? createPortal(
            <ul
              ref={listRef}
              id={`${id}-list`}
              role="listbox"
              tabIndex={-1}
              aria-label={label}
              aria-activedescendant={`${id}-option-${active}`}
              onKeyDown={onListKey}
              style={{ left: placement.left, width: placement.width, top: placement.top, bottom: placement.bottom }}
              className="fixed z-[70] rounded-2xl border border-line bg-white p-1.5 font-sans shadow-xl outline-none dark:border-zinc-700 dark:bg-zinc-900"
            >
              {options.map((option, index) => {
                const selected = option === value;
                return (
                  <li
                    key={option}
                    id={`${id}-option-${index}`}
                    role="option"
                    aria-selected={selected}
                    onPointerEnter={() => setActive(index)}
                    onClick={() => choose(index)}
                    className={`flex h-10 cursor-pointer items-center justify-between gap-3 rounded-xl px-3 text-[13px] tabular-nums transition-colors ${
                      index === active ? "bg-surface dark:bg-white/5" : ""
                    } ${selected ? "font-semibold text-primary" : "text-charcoal dark:text-zinc-100"}`}
                  >
                    {option}
                    {selected ? <Check size={15} strokeWidth={2.5} aria-hidden="true" /> : null}
                  </li>
                );
              })}
            </ul>,
            document.body,
          )
        : null}
    </>
  );
}
