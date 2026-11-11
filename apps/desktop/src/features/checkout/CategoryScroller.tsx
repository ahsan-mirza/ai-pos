import { useLocale } from "@ai-pos/ui";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type MouseEvent, type PointerEvent, type ReactNode } from "react";

export type CategoryChip = {
  value: string | null;
  label: string;
};

const EDGE = 1;

/** Whether a chip row overflows, and whether the inline start or end is already in view. */
export function scrollEdges(scrollLeft: number, scrollWidth: number, clientWidth: number, rtl: boolean) {
  const max = Math.max(0, scrollWidth - clientWidth);
  const position = rtl && scrollLeft < 0 ? -scrollLeft : scrollLeft;
  return {
    overflow: max > EDGE,
    atStart: position <= EDGE,
    atEnd: position >= max - EDGE,
  };
}

export function stepTarget(scrollLeft: number, scrollWidth: number, clientWidth: number, rtl: boolean, direction: "earlier" | "later") {
  const max = Math.max(0, scrollWidth - clientWidth);
  const position = rtl && scrollLeft < 0 ? -scrollLeft : scrollLeft;
  const amount = Math.max(160, Math.round(clientWidth * 0.72));
  const next = Math.max(0, Math.min(max, direction === "later" ? position + amount : position - amount));
  return rtl ? -next : next;
}

function reveal(scroller: HTMLElement, chip: HTMLElement, smooth: boolean) {
  const view = scroller.getBoundingClientRect();
  const box = chip.getBoundingClientRect();
  const rtl = getComputedStyle(scroller).direction === "rtl";
  let delta = 0;
  if (rtl) {
    if (box.right > view.right - 2) delta = box.right - (view.right - 2);
    else if (box.left < view.left + 2) delta = box.left - (view.left + 2);
  } else if (box.left < view.left + 2) delta = box.left - (view.left + 2);
  else if (box.right > view.right - 2) delta = box.right - (view.right - 2);
  if (delta !== 0) scroller.scrollBy({ left: delta, behavior: smooth ? "smooth" : "auto" });
}

export function CategoryScroller({
  chips,
  selected,
  onSelect,
}: {
  chips: CategoryChip[];
  selected: string | null;
  onSelect: (value: string | null) => void;
}) {
  const { t } = useLocale();
  const reduced = useReducedMotion() === true;
  const scrollerRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const drag = useRef({ origin: 0, start: 0, dragged: false, active: false });
  const [edges, setEdges] = useState({ overflow: false, atStart: true, atEnd: true });
  const [direction, setDirection] = useState(() => (document.documentElement.dir === "rtl" ? "rtl" : "ltr"));
  const chipKey = chips.map((chip) => `${chip.value ?? ""}\u0000${chip.label}`).join("\u0001");

  useLayoutEffect(() => {
    const read = () => setDirection(document.documentElement.dir === "rtl" ? "rtl" : "ltr");
    read();
    const observer = new MutationObserver(read);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["dir"] });
    return () => observer.disconnect();
  }, []);

  const measure = useCallback(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const rtl = getComputedStyle(el).direction === "rtl";
    const next = scrollEdges(el.scrollLeft, el.scrollWidth, el.clientWidth, rtl);
    setEdges((current) =>
      current.overflow === next.overflow && current.atStart === next.atStart && current.atEnd === next.atEnd ? current : next,
    );
  }, []);

  useLayoutEffect(() => {
    const el = scrollerRef.current;
    const track = trackRef.current;
    if (!el) return;
    measure();
    const observer = new ResizeObserver(() => measure());
    observer.observe(el);
    if (track) observer.observe(track);
    el.addEventListener("scroll", measure, { passive: true });
    return () => {
      observer.disconnect();
      el.removeEventListener("scroll", measure);
    };
  }, [chipKey, measure, direction]);

  useLayoutEffect(() => {
    const scroller = scrollerRef.current;
    const chip = scroller?.querySelector<HTMLElement>("[data-selected='true']");
    if (!scroller || !chip) return;
    reveal(scroller, chip, !reduced);
  }, [selected, chipKey, reduced, direction]);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const onWheel = (event: WheelEvent) => {
      if (el.scrollWidth <= el.clientWidth + EDGE) return;
      if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
      event.preventDefault();
      const rtl = getComputedStyle(el).direction === "rtl";
      const position = rtl && el.scrollLeft < 0 ? -el.scrollLeft : el.scrollLeft;
      const max = Math.max(0, el.scrollWidth - el.clientWidth);
      const next = Math.max(0, Math.min(max, position + event.deltaY));
      el.scrollTo({ left: rtl ? -next : next });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [chipKey]);

  const step = (direction: "earlier" | "later") => {
    const el = scrollerRef.current;
    if (!el) return;
    const rtl = getComputedStyle(el).direction === "rtl";
    el.scrollTo({
      left: stepTarget(el.scrollLeft, el.scrollWidth, el.clientWidth, rtl, direction),
      behavior: reduced ? "auto" : "smooth",
    });
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const target = event.target;
    if (!(target instanceof HTMLButtonElement) || target.dataset.categoryChip !== "true") return;
    const buttons = [...event.currentTarget.querySelectorAll<HTMLButtonElement>("[data-category-chip='true']")];
    const index = buttons.indexOf(target);
    if (index < 0) return;
    const rtl = getComputedStyle(event.currentTarget).direction === "rtl";
    let next = index;
    if (event.key === "ArrowRight") next = rtl ? index - 1 : index + 1;
    else if (event.key === "ArrowLeft") next = rtl ? index + 1 : index - 1;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = buttons.length - 1;
    else return;
    event.preventDefault();
    const button = buttons[Math.max(0, Math.min(buttons.length - 1, next))];
    if (!button || button === target) return;
    button.focus({ preventScroll: true });
    reveal(event.currentTarget, button, !reduced);
  };

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    drag.current = { origin: event.clientX, start: event.currentTarget.scrollLeft, dragged: false, active: true };
  };

  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const state = drag.current;
    if (!state.active) return;
    const dx = event.clientX - state.origin;
    if (!state.dragged && Math.abs(dx) <= 8) return;
    state.dragged = true;
    if (event.pointerType === "touch") return;
    event.currentTarget.setPointerCapture(event.pointerId);
    event.currentTarget.scrollLeft = state.start - dx;
  };

  const onPointerEnd = () => {
    drag.current.active = false;
  };

  const onClickCapture = (event: MouseEvent<HTMLDivElement>) => {
    if (!drag.current.dragged) return;
    event.preventDefault();
    event.stopPropagation();
    drag.current.dragged = false;
  };

  return (
    <div className="-mx-5 flex w-full min-w-0 max-w-full items-center gap-1.5 px-5">
      <ScrollArrow
        name="earlier"
        show={edges.overflow}
        disabled={edges.atStart}
        label={t("Scroll to earlier categories")}
        reduced={reduced}
        onClick={() => step("earlier")}
      >
        <ChevronLeft className="h-4 w-4 rtl:scale-x-[-1]" aria-hidden="true" />
      </ScrollArrow>
      <div
        ref={scrollerRef}
        role="group"
        aria-label={t("Categories")}
        aria-orientation="horizontal"
        className="no-scrollbar min-w-0 flex-1 touch-pan-x overflow-x-auto overflow-y-hidden overscroll-x-contain"
        onKeyDown={onKeyDown}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerEnd}
        onPointerCancel={onPointerEnd}
        onClickCapture={onClickCapture}
      >
        <div ref={trackRef} className="flex w-max flex-nowrap gap-2">
          {chips.map((chip) => {
            const active = selected === chip.value;
            return (
              <button
                key={chip.label}
                type="button"
                data-category-chip="true"
                data-selected={active ? "true" : "false"}
                aria-pressed={active}
                onClick={() => onSelect(chip.value)}
                className={`h-12 shrink-0 whitespace-nowrap rounded-2xl px-4 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50 ${
                  active
                    ? "bg-primary-500 text-white"
                    : "border border-zinc-200 bg-white text-zinc-600 hover:border-zinc-300 hover:text-zinc-900 dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-zinc-300 dark:hover:border-zinc-700 dark:hover:text-white"
                }`}
              >
                {chip.label}
              </button>
            );
          })}
        </div>
      </div>
      <ScrollArrow
        name="later"
        show={edges.overflow}
        disabled={edges.atEnd}
        label={t("Scroll to later categories")}
        reduced={reduced}
        onClick={() => step("later")}
      >
        <ChevronRight className="h-4 w-4 rtl:scale-x-[-1]" aria-hidden="true" />
      </ScrollArrow>
    </div>
  );
}

function ScrollArrow({
  name,
  show,
  disabled,
  label,
  reduced,
  onClick,
  children,
}: {
  name: "earlier" | "later";
  show: boolean;
  disabled: boolean;
  label: string;
  reduced: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <AnimatePresence initial={false}>
      {show ? (
        <motion.button
          key={name}
          type="button"
          aria-label={label}
          disabled={disabled}
          onClick={onClick}
          initial={reduced ? false : { opacity: 0, scale: 0.92 }}
          animate={{ opacity: disabled ? 0.35 : 1, scale: 1 }}
          exit={reduced ? { opacity: 0 } : { opacity: 0, scale: 0.92 }}
          transition={{ duration: reduced ? 0 : 0.16 }}
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-zinc-200 bg-zinc-100 text-zinc-600 hover:bg-zinc-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50 disabled:pointer-events-none dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
        >
          {children}
        </motion.button>
      ) : null}
    </AnimatePresence>
  );
}
