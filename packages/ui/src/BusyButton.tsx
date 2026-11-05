import { useRef, useState, type ButtonHTMLAttributes, type MouseEvent } from "react";

type SpinnerPosition = "leading" | "trailing";

export interface BusyButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onClick"> {
  loading?: boolean;
  loadingText?: string;
  spinnerPosition?: SpinnerPosition;
  /** Visual classes for this button. The loading treatment does not replace them. */
  tone?: string;
  onClick?: (event: MouseEvent<HTMLButtonElement>) => void | Promise<void>;
}

function ButtonSpinner({ active }: { active: boolean }) {
  if (!active) return <span className="inline-block h-4 w-4 shrink-0" aria-hidden="true" />;
  return (
    <span
      className="inline-block h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-current border-r-transparent motion-reduce:animate-none"
      aria-hidden="true"
    />
  );
}

/** Keeps the idle label in the layout so the button does not change size when the spinner appears. */
export function BusyButton({
  loading = false,
  loadingText,
  spinnerPosition = "leading",
  tone = "",
  className = "",
  disabled,
  children,
  onClick,
  type = "button",
  ...props
}: BusyButtonProps) {
  const reserve = loading || loadingText !== undefined;
  return (
    <button
      type={type}
      {...props}
      aria-busy={loading || undefined}
      disabled={Boolean(disabled) || loading}
      onClick={(event) => {
        if (loading || disabled) {
          event.preventDefault();
          return;
        }
        void onClick?.(event);
      }}
      className={`${tone} inline-flex items-center justify-center gap-2 ${loading ? "!opacity-100" : ""} ${className}`}
    >
      {reserve ? (
        <span className="inline-grid items-center justify-items-center whitespace-nowrap">
          <span className={`col-start-1 row-start-1 inline-flex items-center ${loading ? "invisible" : ""}`} aria-hidden={loading || undefined}>
            {children}
          </span>
          <span
            className={`col-start-1 row-start-1 inline-flex items-center gap-2 ${loading ? "" : "invisible"}`}
            aria-hidden={loading ? undefined : true}
          >
            {spinnerPosition === "leading" ? <ButtonSpinner active={loading} /> : null}
            {loadingText ?? children}
            {spinnerPosition === "trailing" ? <ButtonSpinner active={loading} /> : null}
          </span>
        </span>
      ) : (
        children
      )}
    </button>
  );
}

/** Sets loading around a click that returns a promise, and ignores a second click until it settles. */
export function AsyncButton({
  onClick,
  loading: controlled = false,
  disabled,
  children,
  ...props
}: BusyButtonProps) {
  const [pending, setPending] = useState(false);
  const lock = useRef(false);
  const loading = controlled || pending;
  return (
    <BusyButton
      {...props}
      loading={loading}
      disabled={disabled}
      onClick={async (event) => {
        if (lock.current || controlled || disabled) return;
        const result = onClick?.(event);
        if (result === undefined || typeof (result as Promise<void>).then !== "function") return;
        lock.current = true;
        setPending(true);
        try {
          await result;
        } finally {
          lock.current = false;
          setPending(false);
        }
      }}
    >
      {children}
    </BusyButton>
  );
}
