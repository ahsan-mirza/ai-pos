import {
  ROLLBACK_REASON_MIN_LENGTH,
  formatMoney,
  type BatchDetail,
  type RollbackPreview,
  type RollbackResult,
} from "@ai-pos/shared-types";
import { AlertTriangle, Loader2, Lock, Trash2, Undo2 } from "lucide-react";
import { useEffect, useState } from "react";
import { ErrorNote, GhostButton } from "../../../components/ui/Field";
import { Modal } from "../../../components/ui/Modal";
import { message } from "../api";
import { batchesApi } from "../import/api";

export function RollbackModal({
  batch,
  onClose,
  onDone,
}: {
  batch: BatchDetail;
  onClose: () => void;
  onDone: (result: RollbackResult) => void;
}) {
  const [preview, setPreview] = useState<RollbackPreview | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    batchesApi
      .rollbackPreview(batch.id)
      .then(setPreview)
      .catch((caught: unknown) => setError(message(caught, "Could not check this batch.")));
  }, [batch.id]);

  const confirm = async () => {
    setBusy(true);
    setError(null);
    try {
      onDone(await batchesApi.rollback(batch.id, reason.trim()));
    } catch (caught) {
      setError(message(caught, "The rollback failed."));
      setBusy(false);
    }
  };

  const deleting = preview?.mode === "DELETE";
  const ready = preview !== null && preview.can_rollback && reason.trim().length >= ROLLBACK_REASON_MIN_LENGTH;

  return (
    <Modal
      title={deleting ? "Delete & roll back batch" : "Roll back batch"}
      subtitle={`${batch.batch_number} · ${batch.store_code} · ${batch.total_items_count.toLocaleString()} units`}
      onClose={busy ? () => undefined : onClose}
      width="lg"
      footer={
        <>
          <GhostButton disabled={busy} onClick={onClose}>
            Cancel
          </GhostButton>
          <button
            type="button"
            disabled={!ready || busy}
            onClick={() => void confirm()}
            className="inline-flex items-center justify-center gap-2 rounded-full bg-accent px-8 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-accent-hover disabled:opacity-40 disabled:hover:bg-accent"
          >
            {busy ? (
              <Loader2 size={16} className="animate-spin" aria-hidden="true" />
            ) : deleting ? (
              <Trash2 size={16} aria-hidden="true" />
            ) : (
              <Undo2 size={16} aria-hidden="true" />
            )}
            {deleting ? "Delete batch" : "Reverse remaining stock"}
          </button>
        </>
      }
    >
      {preview === null ? (
        error ? null : (
          <div className="flex items-center gap-2 py-6 text-sm text-charcoal/60">
            <Loader2 size={16} className="animate-spin" aria-hidden="true" /> Checking what can be pulled back…
          </div>
        )
      ) : (
        <div className="space-y-4">
          <div
            className={`flex items-start gap-3 rounded-2xl px-4 py-3 text-sm ${
              deleting ? "bg-charcoal/[0.04] text-charcoal/80" : "bg-accent/10 text-accent"
            }`}
          >
            {deleting ? (
              <Trash2 size={18} className="mt-0.5 shrink-0" aria-hidden="true" />
            ) : (
              <AlertTriangle size={18} className="mt-0.5 shrink-0" aria-hidden="true" />
            )}
            <p>
              {deleting
                ? "Nothing from this batch has been sold or moved. The batch is deleted, its units are removed from branch stock, and any IMEIs it registered are voided so they can be imported again."
                : "Units from this batch were already sold or moved, so it cannot be deleted. Stock still on the shelf is pulled back, sold records stay locked as history, and the batch is marked Reversed."}
            </p>
          </div>

          <dl className="grid grid-cols-3 gap-3">
            <div className="rounded-2xl bg-surface px-4 py-3">
              <dt className="text-[11px] font-semibold uppercase tracking-wider text-[#6B7280]">Pull back</dt>
              <dd className="mt-1 text-lg font-semibold tabular-nums">{preview.units_to_remove}</dd>
            </div>
            <div className="rounded-2xl bg-surface px-4 py-3">
              <dt className="text-[11px] font-semibold uppercase tracking-wider text-[#6B7280]">Sold · locked</dt>
              <dd className="mt-1 text-lg font-semibold tabular-nums">{preview.units_sold}</dd>
            </div>
            <div className="rounded-2xl bg-surface px-4 py-3">
              <dt className="text-[11px] font-semibold uppercase tracking-wider text-[#6B7280]">Cost reversed</dt>
              <dd className="mt-1 truncate text-lg font-semibold tabular-nums">
                {formatMoney(preview.cost_written_back_cents, batch.currency)}
              </dd>
            </div>
          </dl>

          {preview.conflicts.length ? (
            <div>
              <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold">
                <Lock size={14} className="text-accent" aria-hidden="true" /> Conflict summary
              </h3>
              <ul className="max-h-48 divide-y divide-line overflow-y-auto rounded-2xl border border-line">
                {preview.conflicts.map((conflict) => (
                  <li key={conflict.sku} className="flex items-start justify-between gap-3 px-4 py-2.5">
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium">{conflict.product_name}</span>
                      <span className="block text-xs text-charcoal/60">{conflict.detail}</span>
                    </span>
                    <span className="shrink-0 text-right text-xs tabular-nums text-charcoal/60">
                      <span className="block font-semibold text-charcoal">
                        {conflict.reversible} / {conflict.remaining}
                      </span>
                      reversible
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <label className="block text-sm font-medium">
            Reason for the audit trail <span className="text-accent">*</span>
            <textarea
              value={reason}
              autoFocus
              maxLength={500}
              rows={3}
              onChange={(event) => setReason(event.target.value)}
              placeholder="e.g. Supplier invoice was duplicated; wrong cost on the delivery note…"
              className="mt-1.5 w-full resize-none rounded-xl border border-transparent bg-surface px-4 py-3 text-sm font-normal transition-colors placeholder:text-charcoal/40 focus:border-accent focus:bg-white focus:outline-none"
            />
            <span className="mt-1 block text-xs font-normal text-charcoal/50">
              Required, at least {ROLLBACK_REASON_MIN_LENGTH} characters. Recorded with your name in the audit trail.
            </span>
          </label>
        </div>
      )}
      <ErrorNote message={error} />
    </Modal>
  );
}
