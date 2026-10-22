import { Smartphone, ShieldCheck, X } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import {
  askRemoteApproval,
  cancelRemoteApproval,
  remoteApprovalStatus,
  type RemoteApprovalSpec,
} from "../features/approvals/remoteApproval";
import type { CashierProfile } from "../lib/tauri";

const POLL_MS = 2500;

interface ManagerApprovalModalProps {
  /** What the manager is approving, one line each. */
  reasons: string[];
  subtitle: string;
  verify: (username: string, pin: string) => Promise<CashierProfile>;
  onClose: () => void;
  onApproved: (approver: CashierProfile, note: string) => void;
  /** Extra inputs (for example the new price) shown above the manager's credentials. */
  children?: ReactNode;
  /** False while the extra inputs are incomplete. */
  ready?: boolean;
  approveLabel?: string;
  /** Lets the cashier send the request to a manager's phone instead of a PIN at the till. */
  remote?: RemoteApprovalSpec;
}

export function ManagerApprovalModal({
  reasons,
  subtitle,
  verify,
  onClose,
  onApproved,
  children,
  ready = true,
  approveLabel = "Approve",
  remote,
}: ManagerApprovalModalProps) {
  const titleId = useId();
  const [username, setUsername] = useState("");
  const [pin, setPin] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [waitingId, setWaitingId] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const approvedRef = useRef(onApproved);
  useEffect(() => {
    approvedRef.current = onApproved;
  });

  useEffect(() => {
    if (waitingId === null) return;
    let stopped = false;
    const timer = window.setInterval(() => {
      remoteApprovalStatus(waitingId)
        .then((request) => {
          if (stopped || request.status === "PENDING") return;
          setWaitingId(null);
          if (request.status === "APPROVED" && request.approver) {
            approvedRef.current(request.approver, request.note || `Approved remotely by ${request.approver.full_name}`);
          } else if (request.status === "DECLINED") {
            setError(`${request.decided_by_name ?? "The manager"} declined${request.note ? `: ${request.note}` : "."}`);
          } else {
            setError(request.status === "EXPIRED" ? "No manager answered in time. Ask again or use a PIN." : "The request was cancelled.");
          }
        })
        .catch(() => undefined);
    }, POLL_MS);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [waitingId]);

  const close = () => {
    if (waitingId !== null) void cancelRemoteApproval(waitingId).catch(() => undefined);
    onClose();
  };

  const askPhone = () => {
    if (!remote || !ready) return;
    setAsking(true);
    setError(null);
    askRemoteApproval({ ...remote, details: remote.details ?? reasons })
      .then((request) => setWaitingId(request.id))
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : String(caught)))
      .finally(() => setAsking(false));
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const canSubmit = ready && !busy && username.trim() !== "" && /^\d{4,6}$/.test(pin) && note.trim().length >= 3;

  return (
    <div className="modal-backdrop" role="presentation">
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="modal-card max-w-md">
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-primary text-white">
            <ShieldCheck size={20} aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-xl font-semibold">
              Manager approval
            </h2>
            <p className="text-sm text-charcoal/60 dark:text-zinc-400">{subtitle}</p>
          </div>
          <button type="button" aria-label="Close" onClick={close} disabled={busy} className="modal-close">
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <ul className="mt-5 space-y-2">
          {reasons.map((reason) => (
            <li key={reason} className="rounded-2xl bg-surface dark:bg-zinc-800/60 px-4 py-2.5 text-sm font-medium">
              {reason}
            </li>
          ))}
        </ul>
        <form
          className="mt-5 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (!canSubmit) return;
            setBusy(true);
            setError(null);
            verify(username.trim().toLowerCase(), pin)
              .then((approver) => onApproved(approver, note.trim()))
              .catch((caught: unknown) => {
                setError(caught instanceof Error ? caught.message : String(caught));
                setPin("");
              })
              .finally(() => setBusy(false));
          }}
        >
          {children}
          <div className="grid grid-cols-[1fr_120px] gap-3">
            <label className="text-sm font-medium" htmlFor="approver-username">
              Manager username
              <input
                id="approver-username"
                autoFocus={children === undefined}
                autoComplete="off"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                className="modal-input mt-1.5 font-normal"
              />
            </label>
            <label className="text-sm font-medium" htmlFor="approver-pin">
              PIN
              <input
                id="approver-pin"
                type="password"
                inputMode="numeric"
                autoComplete="off"
                maxLength={6}
                value={pin}
                onChange={(event) => setPin(event.target.value.replace(/\D/g, ""))}
                className="modal-input mt-1.5 font-normal tabular-nums tracking-[0.3em]"
              />
            </label>
          </div>
          <label className="block text-sm font-medium" htmlFor="approver-note">
            Reason for the override
            <textarea
              id="approver-note"
              value={note}
              maxLength={250}
              rows={2}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Logged in the audit trail"
              className="modal-input mt-1.5 resize-none text-sm font-normal"
            />
          </label>
          {error ? (
            <p role="alert" className="text-sm font-medium text-red-600 dark:text-red-400">
              {error}
            </p>
          ) : null}
          {waitingId !== null ? (
            <div role="status" className="flex items-center justify-between gap-3 rounded-2xl bg-primary/10 px-4 py-3 text-sm">
              <span className="flex items-center gap-2 font-medium">
                <Smartphone size={16} aria-hidden="true" className="animate-pulse" /> Waiting for a manager to answer on their phone…
              </span>
              <button
                type="button"
                className="text-xs font-semibold underline"
                onClick={() => {
                  void cancelRemoteApproval(waitingId).catch(() => undefined);
                  setWaitingId(null);
                }}
              >
                Cancel request
              </button>
            </div>
          ) : null}
          <div className="flex flex-wrap items-center justify-end gap-3 pt-2">
            {remote && waitingId === null ? (
              <button
                type="button"
                onClick={askPhone}
                disabled={!ready || asking || busy}
                className="mr-auto inline-flex items-center gap-1.5 text-sm font-semibold text-primary disabled:opacity-40"
              >
                <Smartphone size={15} aria-hidden="true" /> {asking ? "Sending…" : "Ask a manager's phone"}
              </button>
            ) : null}
            <button type="button" onClick={close} disabled={busy} className="modal-cancel">
              Cancel
            </button>
            <button type="submit" disabled={!canSubmit || waitingId !== null} className="modal-save">
              {busy ? "Checking…" : approveLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
