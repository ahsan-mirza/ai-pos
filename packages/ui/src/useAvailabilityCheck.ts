import { useCallback, useEffect, useRef, useState } from "react";

/** Wait until typing pauses. Forms read this so the delay stays in one place. */
export const AVAILABILITY_DEBOUNCE_MS = 500;
export const AVAILABILITY_TIMEOUT_MS = 8_000;

export type AvailabilityState = "idle" | "checking" | "available" | "unavailable" | "error";

interface Settled<TResult> {
  identity: string;
  status: AvailabilityState;
  result: TResult | null;
}

export function availabilityBlocksSubmit(status: AvailabilityState, valueIsValid: boolean): boolean {
  if (!valueIsValid) return true;
  return status === "idle" || status === "checking" || status === "unavailable";
}

function isAbort(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/**
 * Debounced availability check. Invalid values never call `check`.
 * A newer keystroke aborts the previous request, and a late response cannot overwrite the current value.
 * Network failures land on `error`, never `available`.
 */
export function useAvailabilityCheck<TResult extends { available: boolean }>(options: {
  value: string;
  contextKey?: string;
  debounceMs?: number;
  timeoutMs?: number;
  enabled?: boolean;
  isValid: (value: string) => boolean;
  normalize: (value: string) => string;
  check: (normalized: string, signal: AbortSignal) => Promise<TResult>;
}): { status: AvailabilityState; result: TResult | null; retry: () => void } {
  const {
    value,
    contextKey = "",
    debounceMs = AVAILABILITY_DEBOUNCE_MS,
    timeoutMs = AVAILABILITY_TIMEOUT_MS,
    enabled = true,
    isValid,
    normalize,
    check,
  } = options;
  const normalized = normalize(value);
  const valid = enabled && isValid(value);
  const [attempt, setAttempt] = useState(0);
  const identity = valid ? `${contextKey}\0${normalized}\0${attempt}` : "";
  const checkRef = useRef(check);
  checkRef.current = check;
  const [settled, setSettled] = useState<Settled<TResult> | null>(null);
  const settledRef = useRef(settled);
  settledRef.current = settled;

  useEffect(() => {
    if (identity === "") return;
    const previous = settledRef.current;
    if (previous?.identity === identity && previous.status !== "checking" && previous.status !== "idle") return;
    const controller = new AbortController();
    let cancelled = false;
    let timedOut = false;
    const timer = window.setTimeout(() => {
      if (cancelled) return;
      setSettled({ identity, status: "checking", result: null });
      const timeout = window.setTimeout(() => {
        timedOut = true;
        controller.abort();
        if (!cancelled) setSettled({ identity, status: "error", result: null });
      }, timeoutMs);
      checkRef
        .current(normalized, controller.signal)
        .then(
          (result) => {
            window.clearTimeout(timeout);
            if (cancelled || timedOut) return;
            setSettled({
              identity,
              status: result.available ? "available" : "unavailable",
              result,
            });
          },
          (error: unknown) => {
            window.clearTimeout(timeout);
            if (cancelled || timedOut) return;
            if (!timedOut && (controller.signal.aborted || isAbort(error))) return;
            setSettled({ identity, status: "error", result: null });
          },
        );
    }, debounceMs);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [identity, normalized, debounceMs, timeoutMs]);

  const visible =
    identity !== "" && settled?.identity === identity
      ? { status: settled.status, result: settled.result }
      : { status: "idle" as const, result: null };

  const retry = useCallback(() => {
    setAttempt((current) => current + 1);
  }, []);

  return { status: visible.status, result: visible.result, retry };
}
