import { Calendar, ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useRef, useState, type ChangeEvent, type InputHTMLAttributes } from "react";
import { createPortal } from "react-dom";
import {
  compareIso,
  DATE_PLACEHOLDER,
  DATETIME_PLACEHOLDER,
  displayToIso,
  isoToDisplay,
  maskDateInput,
} from "./dateFormat";
import { useLocale } from "./LocaleSwitch";

export type AxizDatePickerVariant = "default" | "compact" | "inline" | "datetime";

export interface AxizDatePickerProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "value" | "defaultValue" | "onChange" | "min" | "max"> {
  /** ISO `YYYY-MM-DD`, or `YYYY-MM-DDTHH:mm` when a time is shown. */
  value?: string;
  defaultValue?: string;
  onChange?: (event: ChangeEvent<HTMLInputElement>) => void;
  /** ISO lower bound, same shape as `value`. */
  min?: string | number;
  /** ISO upper bound, same shape as `value`. */
  max?: string | number;
  /** ISO dates the calendar cannot select. */
  disabledDates?: string[];
  isDateDisabled?: (isoDate: string) => boolean;
  /** Shows a Clear action. Deleting the text always clears an optional field. */
  clearable?: boolean;
  /** Message rendered under the field. Pages that already show their own error can omit this. */
  error?: string;
  withTime?: boolean;
  variant?: AxizDatePickerVariant;
  /** Calendar icon inside the left edge. Leave unset inside a field that already draws one. */
  leading?: boolean;
}

export interface AxizDateRangeProps {
  from: string;
  to: string;
  onFromChange: (value: string) => void;
  onToChange: (value: string) => void;
  min?: string;
  max?: string;
  disabled?: boolean;
  fromLabel?: string;
  toLabel?: string;
  className?: string;
}

const fieldShell =
  "h-11 w-full rounded-xl border border-transparent bg-gray-50 py-0 text-sm font-normal text-charcoal transition placeholder:text-charcoal/40 focus:border-orange-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-orange-500 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

function changeEvent(value: string): ChangeEvent<HTMLInputElement> {
  return { target: { value }, currentTarget: { value } } as ChangeEvent<HTMLInputElement>;
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

function daysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate();
}

function todayIso(): string {
  const now = new Date();
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function datePart(iso: string): string {
  return iso.slice(0, 10);
}

function timePart(iso: string): string {
  const match = /T(\d{2}):(\d{2})/.exec(iso);
  return match ? `${match[1]}:${match[2]}` : "00:00";
}

function rangeMessage(iso: string, min?: string, max?: string, withTime = false): string {
  if (min && compareIso(iso, min) < 0) return `Enter a date on or after ${isoToDisplay(min, withTime) || min}.`;
  if (max && compareIso(iso, max) > 0) return `Enter a date on or before ${isoToDisplay(max, withTime) || max}.`;
  return "";
}

function readingDirection(node: HTMLElement | null): "ltr" | "rtl" {
  if (typeof document === "undefined") return "ltr";
  let current: HTMLElement | null = node;
  while (current) {
    const dir = current.getAttribute("dir");
    if (dir === "rtl" || dir === "ltr") return dir;
    current = current.parentElement;
  }
  return document.documentElement.dir === "rtl" ? "rtl" : "ltr";
}

function MonthCalendar({
  cursor,
  selected,
  min,
  max,
  blocked,
  locale,
  dir,
  onCursor,
  onSelect,
}: {
  cursor: string;
  selected: string;
  min?: string;
  max?: string;
  blocked: (iso: string) => boolean;
  locale: string;
  dir: "ltr" | "rtl";
  onCursor: (iso: string) => void;
  onSelect: (iso: string) => void;
}) {
  const year = Number(cursor.slice(0, 4));
  const month = Number(cursor.slice(5, 7));
  const count = daysInMonth(year, month);
  const firstWeekday = new Date(year, month - 1, 1).getDay();
  const monthLabel = new Intl.DateTimeFormat(locale, { month: "long", year: "numeric" }).format(new Date(year, month - 1, 1));
  const weekdays = [0, 1, 2, 3, 4, 5, 6].map((offset) =>
    new Intl.DateTimeFormat(locale, { weekday: "narrow" }).format(new Date(2023, 0, 1 + offset)),
  );
  const today = todayIso();
  const cells: Array<number | null> = [...Array(firstWeekday).fill(null), ...Array.from({ length: count }, (_, index) => index + 1)];
  const pendingFocus = useRef<string | null>(null);

  useEffect(() => {
    const iso = pendingFocus.current;
    if (!iso) return;
    pendingFocus.current = null;
    document.querySelector<HTMLButtonElement>(`[data-axiz-day="${iso}"]`)?.focus();
  }, [cursor]);

  function shiftMonth(by: number) {
    const next = new Date(year, month - 1 + by, 1);
    onCursor(`${next.getFullYear()}-${pad(next.getMonth() + 1)}-01`);
  }

  function moveDay(iso: string, by: number) {
    const parts = iso.split("-").map(Number);
    const y = parts[0] ?? 2026;
    const m = parts[1] ?? 1;
    const d = parts[2] ?? 1;
    const next = new Date(y, m - 1, d + by);
    const value = `${next.getFullYear()}-${pad(next.getMonth() + 1)}-${pad(next.getDate())}`;
    pendingFocus.current = value;
    onCursor(value);
  }

  return (
    <div dir={dir}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <button type="button" aria-label="Previous month" className="grid h-8 w-8 place-items-center rounded-lg text-charcoal hover:bg-black/5 dark:text-zinc-100 dark:hover:bg-white/10" onClick={() => shiftMonth(dir === "rtl" ? 1 : -1)}>
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
        </button>
        <p className="text-sm font-semibold text-charcoal dark:text-zinc-100">{monthLabel}</p>
        <button type="button" aria-label="Next month" className="grid h-8 w-8 place-items-center rounded-lg text-charcoal hover:bg-black/5 dark:text-zinc-100 dark:hover:bg-white/10" onClick={() => shiftMonth(dir === "rtl" ? -1 : 1)}>
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
      <div className="grid grid-cols-7 gap-0.5 text-center text-[11px] font-medium text-charcoal/50 dark:text-zinc-400">
        {weekdays.map((label, index) => (
          <span key={`${label}-${index}`}>{label}</span>
        ))}
      </div>
      <div className="mt-1 grid grid-cols-7 gap-0.5" role="grid" aria-label={monthLabel}>
        {cells.map((day, index) => {
          if (day === null) return <span key={`blank-${index}`} />;
          const iso = `${year}-${pad(month)}-${pad(day)}`;
          const unavailable = blocked(iso) || (min ? compareIso(iso, datePart(min)) < 0 : false) || (max ? compareIso(iso, datePart(max)) > 0 : false);
          const isSelected = selected !== "" && datePart(selected) === iso;
          const isToday = iso === today;
          return (
            <button
              key={iso}
              type="button"
              role="gridcell"
              data-axiz-day={iso}
              disabled={unavailable}
              aria-pressed={isSelected}
              aria-current={isToday ? "date" : undefined}
              aria-label={new Intl.DateTimeFormat(locale, { day: "numeric", month: "long", year: "numeric" }).format(new Date(year, month - 1, day))}
              className={`h-8 rounded-lg text-sm tabular-nums focus:outline-none focus-visible:ring-2 focus-visible:ring-orange-500 disabled:cursor-not-allowed disabled:text-charcoal/25 dark:disabled:text-zinc-600 ${
                isSelected ? "bg-accent font-semibold text-white" : isToday ? "ring-1 ring-accent text-charcoal dark:text-zinc-100" : "text-charcoal hover:bg-black/5 dark:text-zinc-100 dark:hover:bg-white/10"
              }`}
              onClick={() => onSelect(iso)}
              onKeyDown={(event) => {
                const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : event.key === "ArrowDown" ? 7 : event.key === "ArrowUp" ? -7 : 0;
                if (!step) return;
                event.preventDefault();
                moveDay(iso, dir === "rtl" && (event.key === "ArrowRight" || event.key === "ArrowLeft") ? -step : step);
              }}
            >
              {day}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Date field that always shows and accepts DD-MM-YYYY. `onChange` reports ISO, so existing
 * form and filter handlers keep working. The calendar is drawn by AxizPOS, not the browser.
 */
export function AxizDatePicker({
  value,
  defaultValue = "",
  onChange,
  min,
  max,
  disabledDates,
  isDateDisabled,
  clearable = false,
  error,
  withTime = false,
  variant = "default",
  leading,
  className = "",
  placeholder,
  required,
  disabled,
  readOnly,
  name,
  style,
  onBlur,
  onFocus,
  ...props
}: AxizDatePickerProps) {
  const { locale } = useLocale();
  const calendarLocale = locale === "ar" ? "ar" : "en-GB";
  const timed = withTime || variant === "datetime";
  const showLeading = leading ?? className === "";
  const rootRef = useRef<HTMLSpanElement>(null);
  const textRef = useRef<HTMLInputElement>(null);
  const [internal, setInternal] = useState(defaultValue);
  const current = value !== undefined ? value : internal;
  const [text, setText] = useState(() => isoToDisplay(current, timed));
  const [focused, setFocused] = useState(false);
  const [open, setOpen] = useState(variant === "inline");
  const [cursor, setCursor] = useState(() => `${(datePart(current) || todayIso()).slice(0, 8)}01`);
  const [box, setBox] = useState<DOMRect | null>(null);
  const minIso = typeof min === "string" ? min : undefined;
  const maxIso = typeof max === "string" ? max : undefined;
  const blocked = new Set((disabledDates ?? []).map(datePart));
  const placeholderText = placeholder ?? (timed ? DATETIME_PLACEHOLDER : DATE_PLACEHOLDER);
  const parsed = displayToIso(text, timed);
  const dir = readingDirection(rootRef.current);

  useEffect(() => {
    if (!focused) setText(isoToDisplay(current, timed));
  }, [current, timed, focused]);

  useEffect(() => {
    const field = textRef.current;
    if (!field) return;
    const finished = timed ? text.length >= 16 : text.length >= 10;
    if (!text || (focused && !finished)) {
      field.setCustomValidity("");
      return;
    }
    if (parsed === null) {
      field.setCustomValidity(timed ? "Enter the date as DD-MM-YYYY HH:mm." : "Enter the date as DD-MM-YYYY.");
      return;
    }
    if (blocked.has(datePart(parsed)) || isDateDisabled?.(datePart(parsed))) {
      field.setCustomValidity("This date is not available.");
      return;
    }
    field.setCustomValidity(rangeMessage(parsed, minIso, maxIso, timed));
  }, [text, parsed, minIso, maxIso, timed, focused, disabledDates, isDateDisabled]);

  useEffect(() => {
    if (!open || variant === "inline") return;
    function place() {
      setBox(rootRef.current?.getBoundingClientRect() ?? null);
    }
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    function outside(event: MouseEvent) {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (rootRef.current?.contains(target)) return;
      if (target instanceof Element && target.closest("[data-axiz-calendar]")) return;
      setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
      document.removeEventListener("mousedown", outside);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, variant]);

  function commit(iso: string) {
    if (value === undefined) setInternal(iso);
    if (iso === current) return;
    onChange?.(changeEvent(iso));
  }

  function unavailable(iso: string): boolean {
    return blocked.has(iso) || Boolean(isDateDisabled?.(iso));
  }

  function applyText(next: string) {
    setText(next);
    if (!next) {
      commit("");
      return;
    }
    const iso = displayToIso(next, timed);
    if (!iso) return;
    if (unavailable(datePart(iso)) || rangeMessage(iso, minIso, maxIso, timed)) return;
    commit(iso);
  }

  function selectDay(iso: string) {
    if (unavailable(iso)) return;
    const next = timed ? `${iso}T${timePart(parsed && parsed.length > 10 ? parsed : current)}` : iso;
    if (rangeMessage(next, minIso, maxIso, timed)) return;
    setText(isoToDisplay(next, timed));
    commit(next);
    if (variant !== "inline") setOpen(false);
    textRef.current?.focus();
  }

  function selectTime(hour: string, minute: string) {
    const day = datePart(parsed && parsed.length >= 10 ? parsed : current || todayIso());
    const next = `${day}T${hour}:${minute}`;
    setText(isoToDisplay(next, true));
    if (!rangeMessage(next, minIso, maxIso, true)) commit(next);
  }

  const shell = className || (variant === "compact" ? `${fieldShell} h-9 text-[13px]` : fieldShell);
  const clock = timePart(parsed && parsed.length > 10 ? parsed : current);
  const [hour, minute] = clock.split(":");
  const popover = (
    <div
      data-axiz-calendar=""
      role="dialog"
      aria-label="Choose a date"
      dir={dir}
      className="z-[80] w-[17.5rem] rounded-2xl border border-gray-200 bg-white p-3 text-charcoal shadow-lg dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
      style={
        variant === "inline" || !box
          ? undefined
          : {
              position: "fixed",
              top: box.bottom + 4,
              left: dir === "rtl" ? undefined : box.left,
              right: dir === "rtl" ? window.innerWidth - box.right : undefined,
            }
      }
      onMouseDown={(event) => event.preventDefault()}
    >
      <MonthCalendar
        cursor={cursor}
        selected={parsed && parsed.length >= 10 ? parsed : current}
        min={minIso}
        max={maxIso}
        blocked={unavailable}
        locale={calendarLocale}
        dir={dir}
        onCursor={setCursor}
        onSelect={selectDay}
      />
      {timed ? (
        <div className="mt-3 flex items-center gap-2 border-t border-gray-100 pt-3 dark:border-zinc-800">
          <span className="text-xs font-medium text-charcoal/60 dark:text-zinc-400">Time</span>
          <select aria-label="Hour" className="h-8 rounded-lg border border-gray-200 bg-white px-2 text-sm dark:border-zinc-700 dark:bg-zinc-900" value={hour} onChange={(event) => selectTime(event.target.value, minute ?? "00")}>
            {Array.from({ length: 24 }, (_, index) => pad(index)).map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
          <span aria-hidden="true">:</span>
          <select aria-label="Minute" className="h-8 rounded-lg border border-gray-200 bg-white px-2 text-sm dark:border-zinc-700 dark:bg-zinc-900" value={minute} onChange={(event) => selectTime(hour ?? "00", event.target.value)}>
            {Array.from({ length: 60 }, (_, index) => pad(index)).map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </div>
      ) : null}
      <div className="mt-3 flex items-center justify-between gap-2">
        <button type="button" className="text-sm font-medium text-accent" onClick={() => selectDay(todayIso())}>
          Today
        </button>
        {clearable && !required ? (
          <button
            type="button"
            className="text-sm text-charcoal/60 dark:text-zinc-400"
            onClick={() => {
              setText("");
              commit("");
              if (variant !== "inline") setOpen(false);
            }}
          >
            Clear
          </button>
        ) : null}
      </div>
    </div>
  );

  return (
    <span ref={rootRef} data-axiz-date-picker="" data-variant={variant} className={variant === "inline" ? "block" : "relative block"}>
      <span className="relative block">
        {showLeading ? <Calendar className="pointer-events-none absolute left-3 top-1/2 z-10 h-4 w-4 -translate-y-1/2 text-gray-400" aria-hidden="true" /> : null}
        <input
          {...props}
          ref={textRef}
          type="text"
          inputMode="numeric"
          autoComplete="off"
          placeholder={placeholderText}
          value={text}
          required={required}
          disabled={disabled}
          readOnly={readOnly}
          maxLength={timed ? 16 : 10}
          aria-invalid={error ? true : props["aria-invalid"]}
          aria-expanded={open}
          aria-haspopup="dialog"
          className={shell}
          style={{ ...style, paddingLeft: showLeading ? "2.5rem" : style?.paddingLeft, paddingRight: "2.5rem" }}
          onFocus={(event) => {
            setFocused(true);
            onFocus?.(event);
          }}
          onBlur={(event) => {
            setFocused(false);
            onBlur?.(event);
          }}
          onChange={(event) => applyText(maskDateInput(event.target.value, timed))}
          onKeyDown={(event) => {
            props.onKeyDown?.(event);
            if (event.key === "ArrowDown" && !readOnly && !disabled) {
              event.preventDefault();
              setCursor(`${(datePart(current) || todayIso()).slice(0, 8)}01`);
              setOpen(true);
            }
          }}
        />
        <button
          type="button"
          tabIndex={-1}
          disabled={disabled || readOnly}
          aria-label={timed ? "Open date and time picker" : "Open calendar"}
          className="absolute right-2 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-md text-current opacity-60 hover:bg-black/5 hover:opacity-100 disabled:opacity-30"
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => {
            setCursor(`${(datePart(current) || todayIso()).slice(0, 8)}01`);
            setOpen((valueOpen) => variant === "inline" || !valueOpen);
          }}
        >
          <Calendar className="h-4 w-4" aria-hidden="true" />
        </button>
        <input type="hidden" name={name} value={parsed && parsed.length > 0 ? parsed : ""} />
      </span>
      {error ? <span role="alert" className="mt-1.5 block text-xs font-medium text-danger">{error}</span> : null}
      {open && variant !== "inline" && box ? createPortal(popover, document.body) : null}
      {variant === "inline" ? <div className="mt-2">{popover}</div> : null}
    </span>
  );
}

/** From / To pair. The parent still receives both values; the message only reports an inverted range. */
export function AxizDateRange({
  from,
  to,
  onFromChange,
  onToChange,
  min,
  max,
  disabled,
  fromLabel = "From",
  toLabel = "To",
  className = "",
}: AxizDateRangeProps) {
  const { t } = useLocale();
  const inverted = Boolean(from && to && compareIso(from, to) > 0);
  return (
    <div className={`flex flex-wrap items-end gap-3 ${className}`}>
      <label className="block text-sm font-medium">
        {fromLabel}
        <span className="mt-1.5 block">
          <AxizDatePicker aria-label={fromLabel} value={from} min={min} max={to || max} disabled={disabled} onChange={(event) => onFromChange(event.target.value)} />
        </span>
      </label>
      <label className="block text-sm font-medium">
        {toLabel}
        <span className="mt-1.5 block">
          <AxizDatePicker aria-label={toLabel} value={to} min={from || min} max={max} disabled={disabled} onChange={(event) => onToChange(event.target.value)} />
        </span>
      </label>
      {inverted ? <p role="alert" className="text-xs font-medium text-danger">{t("From is after To.")}</p> : null}
    </div>
  );
}
