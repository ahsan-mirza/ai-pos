import { formatMoney, type RepairDetail } from "@ai-pos/shared-types";
import { useState } from "react";
import { GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { apiBlob, apiGet, apiPost, apiUpload } from "../../lib/api";
import { compressImageToWebp } from "../../lib/imageFile";
import { message, toCents } from "../customers/api";

/** Estimate approval, deposit, photos, passcode and the job card on an open ticket. */
export function WorkshopPanel({
  ticket,
  canUpdate,
  busy,
  run,
  onToast,
}: {
  ticket: RepairDetail;
  canUpdate: boolean;
  busy: boolean;
  run: (work: () => Promise<RepairDetail>, done?: string) => Promise<boolean>;
  onToast: (text: string) => void;
}) {
  const [deposit, setDeposit] = useState("");
  const [link, setLink] = useState<string | null>(null);
  const [passcode, setPasscode] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const money = (cents: number) => formatMoney(cents, ticket.currency);
  const open = ticket.sale_id === null && ticket.status !== "closed" && ticket.status !== "cancelled";

  async function printCard() {
    setLocalError(null);
    try {
      const blob = await apiBlob(`/api/v1/repairs/${ticket.id}/job-card.pdf`);
      window.open(URL.createObjectURL(blob), "_blank", "noopener");
    } catch (caught) {
      setLocalError(message(caught, "Could not print the job card."));
    }
  }

  async function onPhoto(file: File | undefined) {
    if (!file) return;
    setLocalError(null);
    const form = new FormData();
    form.append("kind", "INTAKE");
    form.append("file", await compressImageToWebp(file));
    try {
      await run(() => apiUpload<RepairDetail>(`/api/v1/repairs/${ticket.id}/attachments`, form), "Photo attached.");
    } catch (caught) {
      setLocalError(message(caught, "Could not attach the photo."));
    }
  }

  return (
    <div className="space-y-4 rounded-2xl border border-line p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold">Workshop</h3>
          <p className="text-xs text-charcoal/60">
            {ticket.reference ? `Job ${ticket.reference}` : "Job card"}
            {ticket.technician_name ? ` · ${ticket.technician_name}` : ""}
            {ticket.priority && ticket.priority !== "NORMAL" ? ` · ${ticket.priority}` : ""}
          </p>
        </div>
        <GhostButton onClick={() => void printCard()}>Job card</GhostButton>
      </div>

      {ticket.parts_short ? (
        <p className="rounded-xl bg-warning/10 px-3 py-2 text-xs font-medium text-warning">
          A part is short. The rest is held in stock until it arrives.
        </p>
      ) : null}

      {ticket.approval_status ? (
        <p className="text-sm">
          Estimate {ticket.approval_status.toLowerCase()}
          {ticket.approval_amount_cents != null ? ` · ${money(ticket.approval_amount_cents)}` : ""}
          {ticket.approval_note ? ` · ${ticket.approval_note}` : ""}
        </p>
      ) : null}
      {link ? (
        <p className="break-all rounded-xl bg-surface px-3 py-2 font-mono text-xs">
          Customer link: {link}
        </p>
      ) : null}
      {canUpdate && open && ticket.approval_status !== "APPROVED" ? (
        <div className="flex flex-wrap gap-2">
          <GhostButton
            disabled={busy}
            onClick={() =>
              void (async () => {
                setLocalError(null);
                try {
                  const sent = await apiPost<{ approval_url: string | null; ticket: RepairDetail }>(
                    `/api/v1/repairs/${ticket.id}/approval/request`,
                    {},
                  );
                  setLink(sent.approval_url);
                  await run(async () => sent.ticket, "Estimate sent for approval.");
                } catch (caught) {
                  setLocalError(message(caught, "Could not send the estimate."));
                }
              })()
            }
          >
            Send estimate
          </GhostButton>
          {ticket.approval_status === "PENDING" ? (
            <>
              <PrimaryButton
                disabled={busy}
                onClick={() =>
                  void run(
                    () => apiPost(`/api/v1/repairs/${ticket.id}/approval`, { decision: "approve", channel: "in_store" }),
                    "Estimate approved.",
                  )
                }
              >
                Approve in store
              </PrimaryButton>
              <GhostButton
                disabled={busy}
                onClick={() =>
                  void run(
                    () => apiPost(`/api/v1/repairs/${ticket.id}/approval`, { decision: "decline", channel: "in_store" }),
                    "Estimate declined. The device is ready to hand back.",
                  )
                }
              >
                Decline
              </GhostButton>
            </>
          ) : null}
        </div>
      ) : null}

      {(ticket.deposits ?? []).length > 0 ? (
        <ul className="space-y-1 text-sm">
          {ticket.deposits?.map((row) => (
            <li key={row.id} className="flex justify-between gap-3">
              <span>
                {row.method} deposit · {row.status.toLowerCase()}
              </span>
              <span className="tabular-nums">{money(row.amount_cents)}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {canUpdate && open ? (
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            const cents = toCents(deposit);
            if (cents === null || cents <= 0) {
              setLocalError("Enter the deposit amount.");
              return;
            }
            void run(
              () => apiPost(`/api/v1/repairs/${ticket.id}/deposits`, { amount_cents: cents, method: "cash" }),
              "Deposit taken.",
            ).then((ok) => {
              if (ok) setDeposit("");
            });
          }}
        >
          <TextField label="Deposit" value={deposit} onChange={(event) => setDeposit(event.target.value)} placeholder="0.00" className="w-32" />
          <PrimaryButton disabled={busy} type="submit">
            Take cash deposit
          </PrimaryButton>
        </form>
      ) : null}

      {ticket.has_passcode && canUpdate ? (
        <GhostButton
          disabled={busy}
          onClick={() =>
            void apiGet<{ passcode: string }>(`/api/v1/repairs/${ticket.id}/passcode`)
              .then((body) => setPasscode(body.passcode))
              .catch((caught: unknown) => setLocalError(message(caught, "Could not reveal the passcode.")))
          }
        >
          {passcode ? `Passcode ${passcode}` : "Show passcode"}
        </GhostButton>
      ) : null}

      {(ticket.attachments ?? []).length > 0 ? (
        <ul className="text-xs text-charcoal/70">
          {ticket.attachments?.map((file) => (
            <li key={file.id}>
              {file.kind.toLowerCase()} · {file.file_name}
            </li>
          ))}
        </ul>
      ) : null}
      {open ? (
        <label className="block text-sm font-medium">
          Photo
          <input
            type="file"
            accept="image/*,application/pdf"
            className="mt-1.5 block w-full text-sm"
            onChange={(event) => void onPhoto(event.target.files?.[0])}
          />
        </label>
      ) : null}

      {ticket.tracking_url ? (
        <p className="break-all text-xs text-charcoal/60">
          Tracking: {ticket.tracking_url}{" "}
          <button type="button" className="font-semibold text-accent" onClick={() => void navigator.clipboard.writeText(ticket.tracking_url ?? "").then(() => onToast("Tracking link copied."))}>
            Copy
          </button>
        </p>
      ) : null}
      {ticket.repair_warranty ? (
        <p className="text-xs text-charcoal/70">
          Repair warranty until {new Date(ticket.repair_warranty.expires_at).toLocaleDateString()}.
        </p>
      ) : null}
      {canUpdate && ticket.status === "ready" && ticket.sale_id === null && ticket.total_cents === 0 ? (
        <PrimaryButton disabled={busy} onClick={() => void run(() => apiPost(`/api/v1/repairs/${ticket.id}/pickup`, { note: "Collected" }), "Device collected.")}>
          Mark collected
        </PrimaryButton>
      ) : null}
      {localError ? <p className="text-sm text-danger">{localError}</p> : null}
    </div>
  );
}
