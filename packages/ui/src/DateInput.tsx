import { Calendar } from "lucide-react";
import { useEffect, useId, useRef, useState, type ChangeEvent, type InputHTMLAttributes } from "react";
import { compareIso, DATE_PLACEHOLDER, DATETIME_PLACEHOLDER, displayToIso, isoToDisplay, maskDateInput } from "./dateFormat";

export interface DateInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "value" | "onChange" | "min" | "max"> {
  /** ISO `YYYY-MM-DD`, or `YYYY-MM-DDTHH:mm` when `withTime` is set. */
  value?: string;
  onChange?: (event: ChangeEvent<HTMLInputElement>) => void;
  /** ISO lower bound, same shape as `value`. */
  min?: string | number;
  /** ISO upper bound, same shape as `value`. */
  max?: string | number;
  /** Show and edit a time after the date. The value stays `YYYY-MM-DDTHH:mm`. */
  withTime?: boolean;
}

function changeEvent(value: string): ChangeEvent<HTMLInputElement> {
  return { target: { value }, currentTarget: { value } } as ChangeEvent<HTMLInputElement>;
}

function rangeMessage(iso: string, min?: string, max?: string, withTime = false): string {
  if (min && compareIso(iso, min) < 0) return `Enter a date on or after ${isoToDisplay(min, withTime) || min}.`;
  if (max && compareIso(iso, max) > 0) return `Enter a date on or before ${isoToDisplay(max, withTime) || max}.`;
  return "";
}

/**
 * Text date field that always shows DD-MM-YYYY. `onChange` still reports ISO, so existing
 * form and filter handlers keep working. A calendar button fills the same value.
 */
export function DateInput({
  value = "",
  onChange,
  min,
  max,
  withTime = false,
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
}: DateInputProps) {
  const pickerId = useId();
  const textRef = useRef<HTMLInputElement>(null);
  const pickerRef = useRef<HTMLInputElement>(null);
  const [text, setText] = useState(() => isoToDisplay(value, withTime));
  const [focused, setFocused] = useState(false);
  const minIso = typeof min === "string" ? min : undefined;
  const maxIso = typeof max === "string" ? max : undefined;
  const placeholderText = placeholder ?? (withTime ? DATETIME_PLACEHOLDER : DATE_PLACEHOLDER);
  const parsed = displayToIso(text, withTime);
  const pickerValue = parsed && parsed.length > 0 ? parsed : "";

  useEffect(() => {
    if (!focused) setText(isoToDisplay(value, withTime));
  }, [value, withTime, focused]);

  useEffect(() => {
    const field = textRef.current;
    if (!field) return;
    const finished = withTime ? text.length >= 16 : text.length >= 10;
    if (!text || (focused && !finished)) {
      field.setCustomValidity("");
      return;
    }
    if (parsed === null) {
      field.setCustomValidity(withTime ? "Enter the date as DD-MM-YYYY HH:mm." : "Enter the date as DD-MM-YYYY.");
      return;
    }
    field.setCustomValidity(rangeMessage(parsed, minIso, maxIso, withTime));
  }, [text, parsed, minIso, maxIso, withTime, focused]);

  function commit(iso: string) {
    if (iso === value) return;
    onChange?.(changeEvent(iso));
  }

  function applyText(next: string) {
    setText(next);
    if (!next) {
      commit("");
      return;
    }
    const iso = displayToIso(next, withTime);
    if (!iso) return;
    if (rangeMessage(iso, minIso, maxIso, withTime)) return;
    commit(iso);
  }

  return (
    <span className="relative block">
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
        maxLength={withTime ? 16 : 10}
        className={className}
        style={{ ...style, paddingRight: "2.5rem" }}
        onFocus={(event) => {
          setFocused(true);
          onFocus?.(event);
        }}
        onBlur={(event) => {
          setFocused(false);
          onBlur?.(event);
        }}
        onChange={(event) => applyText(maskDateInput(event.target.value, withTime))}
      />
      <button
        type="button"
        tabIndex={-1}
        disabled={disabled || readOnly}
        aria-label={withTime ? "Open date and time picker" : "Open calendar"}
        className="absolute right-2 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-md text-current opacity-60 hover:bg-black/5 hover:opacity-100 disabled:opacity-30"
        onMouseDown={(event) => event.preventDefault()}
        onClick={() => {
          const picker = pickerRef.current;
          if (!picker) return;
          try {
            picker.showPicker();
          } catch {
            picker.focus();
          }
        }}
      >
        <Calendar className="h-4 w-4" aria-hidden="true" />
      </button>
      <input
        ref={pickerRef}
        id={pickerId}
        tabIndex={-1}
        aria-hidden="true"
        type={withTime ? "datetime-local" : "date"}
        value={pickerValue}
        min={minIso || undefined}
        max={maxIso || undefined}
        name={name}
        disabled={disabled}
        className="pointer-events-none"
        style={{
          position: "absolute",
          width: 1,
          height: 1,
          minWidth: 0,
          minHeight: 0,
          margin: 0,
          padding: 0,
          border: 0,
          opacity: 0,
          overflow: "hidden",
          pointerEvents: "none",
          clipPath: "inset(50%)",
        }}
        onChange={(event) => {
          const iso = event.target.value;
          setText(isoToDisplay(iso, withTime));
          commit(iso);
        }}
      />
    </span>
  );
}
