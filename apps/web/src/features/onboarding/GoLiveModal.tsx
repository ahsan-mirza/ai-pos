import type { GoLiveResult } from "@ai-pos/shared-types";
import { Rocket } from "lucide-react";
import { useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { ApiRequestError, apiPost } from "../../lib/api";

const CLEARED = [
  "Every practice sale, return, quotation and payment",
  "Shifts, cash movements and journal entries",
  "Sample products and sample customers",
];
const KEPT = ["Your own products, stock and customers", "Users, registers and settings"];

export function GoLiveModal({
  storeName,
  onClose,
  onLive,
}: {
  storeName: string;
  onClose: () => void;
  onLive: (result: GoLiveResult) => void;
}) {
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GoLiveResult | null>(null);

  const matches = storeName !== "" && confirm.trim().toLowerCase() === storeName.trim().toLowerCase();

  const goLive = async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(await apiPost<GoLiveResult>("/api/v1/onboarding/go-live", { confirm }));
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Could not go live.");
    } finally {
      setBusy(false);
    }
  };

  if (result !== null) {
    return (
      <Modal
        title="You are live"
        subtitle="The next sale is invoice number 1."
        onClose={() => onLive(result)}
        footer={<PrimaryButton onClick={() => onLive(result)}>Start selling</PrimaryButton>}
      >
        <div className="flex items-center gap-4 rounded-2xl bg-emerald-50 p-4 text-sm text-emerald-900">
          <Rocket size={22} aria-hidden="true" className="shrink-0" />
          <p>
            Cleared {result.sales_removed} practice sale{result.sales_removed === 1 ? "" : "s"},{" "}
            {result.sample_products_removed} sample item{result.sample_products_removed === 1 ? "" : "s"} and{" "}
            {result.sample_customers_removed} sample customer{result.sample_customers_removed === 1 ? "" : "s"}. Stock
            taken by practice sales is back on the shelf.
          </p>
        </div>
      </Modal>
    );
  }

  return (
    <Modal
      title="Go live"
      subtitle="Start with clean books. This can only be done once."
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Not yet</GhostButton>
          <PrimaryButton onClick={() => void goLive()} disabled={!matches || busy}>
            {busy ? "Going live…" : "Go live"}
          </PrimaryButton>
        </>
      }
    >
      <div className="grid gap-4 text-sm sm:grid-cols-2">
        <div>
          <p className="font-semibold">Cleared</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-charcoal/70">
            {CLEARED.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
        <div>
          <p className="font-semibold">Kept</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-charcoal/70">
            {KEPT.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      </div>
      <p className="mt-4 rounded-2xl bg-surface px-4 py-3 text-sm text-charcoal/70">
        Invoice and receipt numbers restart from 1, and stock sold in practice goes back on the shelf.
      </p>
      <div className="mt-5">
        <TextField
          label={`Type "${storeName}" to confirm`}
          value={confirm}
          onChange={(event) => setConfirm(event.target.value)}
          autoComplete="off"
        />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
