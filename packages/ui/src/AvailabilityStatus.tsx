import { Loader2 } from "lucide-react";
import type { AvailabilityState } from "./useAvailabilityCheck";

/** Reserved line under a field so checking, success, and errors do not shift the form. */
export function AvailabilityStatus({
  status,
  availableText,
  unavailableText,
  errorText,
  onRetry,
}: {
  status: AvailabilityState;
  availableText: string;
  unavailableText: string;
  errorText: string;
  onRetry: () => void;
}) {
  return (
    <p className="mt-1.5 min-h-5 text-xs" aria-live="polite">
      {status === "checking" ? (
        <span className="inline-flex items-center gap-1.5 text-charcoal/50">
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
          Checking…
        </span>
      ) : null}
      {status === "available" ? <span className="text-emerald-700">{availableText}</span> : null}
      {status === "unavailable" ? <span className="font-medium text-danger">{unavailableText}</span> : null}
      {status === "error" ? (
        <span className="font-medium text-danger">
          {errorText}{" "}
          <button type="button" className="font-semibold underline" onClick={onRetry}>
            Retry
          </button>
        </span>
      ) : null}
    </p>
  );
}
