import { useState } from "react";
import { CANCEL_REASONS, cancellationReason, cancelWarning, type CancelStage } from "./cancelOrder";

export function CancelOrderDialog({
  stage,
  onClose,
  onSubmit,
}: {
  stage: CancelStage;
  onClose: () => void;
  onSubmit: (reason: string) => void;
}) {
  const [code, setCode] = useState<string>(CANCEL_REASONS[0][0]);
  const [note, setNote] = useState("");
  const warning = cancelWarning(stage);
  const reason = cancellationReason(code, note);
  const other = code === "other";

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="cancel-order-title"
        className="modal-card max-w-md space-y-4"
        onClick={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault();
          if (reason) onSubmit(reason);
        }}
      >
        <div>
          <h2 id="cancel-order-title" className="text-xl font-semibold">Cancel this order?</h2>
          <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">
            Please select a reason for cancelling this order. This action may affect kitchen operations, inventory, payment, and delivery.
          </p>
        </div>
        <label className="block text-sm font-medium">
          Cancellation reason
          <select
            aria-label="Cancellation reason"
            value={code}
            onChange={(event) => setCode(event.target.value)}
            className="modal-input mt-1"
          >
            {CANCEL_REASONS.map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
        <label className="block text-sm font-medium">
          {other ? "Explanation" : "Additional note"}
          <textarea
            aria-label={other ? "Explanation" : "Additional note"}
            required={other}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            rows={3}
            placeholder={other ? "Required" : "Optional"}
            className="modal-input mt-1"
          />
        </label>
        {warning ? (
          <p className="rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-500/10 dark:text-amber-200">{warning}</p>
        ) : null}
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" onClick={onClose} className="h-12 rounded-full px-4 text-sm font-semibold text-zinc-700 dark:text-zinc-200">
            Go Back
          </button>
          <button
            type="submit"
            disabled={reason === null}
            className="h-12 rounded-full bg-red-600 px-4 text-sm font-semibold text-white disabled:opacity-40"
          >
            Submit Cancellation Request
          </button>
        </div>
      </form>
    </div>
  );
}
