import { Permission } from "@ai-pos/shared-types";
import { CheckCircle2, Clock3, RefreshCw, Trash2, TriangleAlert, X } from "lucide-react";
import { useCallback, useEffect, useId, useState } from "react";
import { useConfirm } from "../../components/ConfirmDialog";
import { flushSync, listBatches, resolveBatch, type QueuedBatch } from "../../lib/tauri";
import type { CashierSession } from "../auth/session";

type Filter = "rejected" | "pending" | "synced";

const entityLabels: Record<string, string> = {
  sale: "Sale",
  sale_return: "Return",
  product: "Catalog",
  store: "Store",
  register_shift: "Shift",
  cash_movement: "Cash movement",
  serial_number: "IMEI",
  repair_ticket: "Repair",
};

function describe(batch: QueuedBatch): string {
  const main = batch.entity_types.find((type) => type !== "product" && type !== "store") ?? batch.entity_types[0] ?? "";
  return entityLabels[main] ?? main;
}

/** Every transaction this register has queued, and the server's reason for any it refused. */
export function SyncCenterModal({ session, onClose }: { session: CashierSession; onClose: () => void }) {
  const titleId = useId();
  const [filter, setFilter] = useState<Filter>("rejected");
  const [rows, setRows] = useState<QueuedBatch[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const manager = session.user.permissions.includes(Permission.PosShiftManage);
  const confirm = useConfirm();

  const load = useCallback(() => {
    void listBatches(filter, 100)
      .then(setRows)
      .catch((caught: unknown) => setError(String(caught)));
  }, [filter]);
  useEffect(load, [load]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  const act = async (work: () => Promise<string>) => {
    setBusy(true);
    setError(null);
    try {
      setNotice(await work());
      load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation">
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="modal-card max-w-2xl">
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-charcoal text-white dark:bg-zinc-100 dark:text-zinc-900">
            <RefreshCw size={20} aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-xl font-semibold">
              Sync Center
            </h2>
            <p className="text-sm text-charcoal/60 dark:text-zinc-400">What this register has sent to head office, and anything it refused.</p>
          </div>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void act(async () => {
                const report = await flushSync();
                return report.message;
              })
            }
            className="inline-flex items-center gap-2 rounded-full border border-line dark:border-zinc-800 px-4 py-2 text-sm font-semibold hover:border-primary hover:text-primary disabled:opacity-40"
          >
            <RefreshCw size={15} aria-hidden="true" className={busy ? "animate-spin" : ""} /> Sync now
          </button>
          <button type="button" aria-label="Close" onClick={onClose} disabled={busy} className="modal-close">
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        <div className="mt-5 grid grid-cols-3 gap-1 rounded-full bg-charcoal p-1" role="tablist" aria-label="Queue status">
          {(
            [
              ["rejected", "Needs attention"],
              ["pending", "Waiting"],
              ["synced", "Sent"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={filter === value}
              onClick={() => {
                setFilter(value);
                setNotice(null);
              }}
              className={`rounded-full px-3 py-2 text-sm font-semibold transition ${
                filter === value ? "bg-primary text-white" : "text-white/70 hover:text-white"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <ul className="mt-4 max-h-[50vh] space-y-2 overflow-y-auto">
          {rows.length === 0 ? (
            <li className="rounded-2xl border border-dashed border-line dark:border-zinc-800 p-6 text-center text-sm text-charcoal/60 dark:text-zinc-400">
              {filter === "rejected" ? "Nothing needs attention." : filter === "pending" ? "Everything has been sent." : "Nothing sent yet."}
            </li>
          ) : null}
          {rows.map((batch) => (
            <li key={batch.batch_id} className="rounded-2xl bg-surface dark:bg-zinc-800/60 p-3">
              <div className="flex items-center gap-3">
                {batch.status === "rejected" ? (
                  <TriangleAlert size={18} aria-hidden="true" className="shrink-0 text-primary" />
                ) : batch.status === "synced" ? (
                  <CheckCircle2 size={18} aria-hidden="true" className="shrink-0 text-charcoal dark:text-zinc-100" />
                ) : (
                  <Clock3 size={18} aria-hidden="true" className="shrink-0 text-charcoal/50 dark:text-zinc-400" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold">
                    {describe(batch)}
                    {batch.summary ? <span className="font-normal tabular-nums text-charcoal/60 dark:text-zinc-400"> · {batch.summary}</span> : null}
                  </p>
                  <p className="text-xs text-charcoal/50 dark:text-zinc-400 tabular-nums">
                    {new Date(batch.created_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}
                    {batch.attempts > 0 && batch.status === "pending" ? ` · ${batch.attempts} failed attempts` : ""}
                  </p>
                </div>
                {batch.status === "rejected" ? (
                  <div className="flex shrink-0 gap-1">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        void act(async () => {
                          await resolveBatch(batch.batch_id, "retry");
                          await flushSync().catch(() => undefined);
                          return "Sent again.";
                        })
                      }
                      className="rounded-full bg-primary px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
                    >
                      Retry
                    </button>
                    <button
                      type="button"
                      disabled={busy || !manager}
                      title={manager ? "Drop it for good" : "Only a manager can discard"}
                      aria-label="Discard"
                      onClick={() => {
                        void (async () => {
                          const accepted = await confirm({
                            title: "Discard transaction",
                            message: "Discard this transaction? It will never reach head office.",
                            confirmLabel: "Discard",
                            tone: "danger",
                          });
                          if (!accepted) return;
                          void act(async () => {
                            await resolveBatch(batch.batch_id, "discard");
                            return "Discarded.";
                          });
                        })();
                      }}
                      className="flex h-8 w-8 items-center justify-center rounded-full text-charcoal/50 dark:text-zinc-400 hover:bg-charcoal/10 dark:hover:bg-white/10 hover:text-charcoal disabled:opacity-30"
                    >
                      <Trash2 size={15} aria-hidden="true" />
                    </button>
                  </div>
                ) : null}
              </div>
              {batch.last_error && batch.status !== "synced" ? (
                <p className="mt-2 rounded-xl bg-white dark:bg-zinc-900 px-3 py-2 text-xs text-red-600 dark:text-red-400">{batch.last_error}</p>
              ) : null}
            </li>
          ))}
        </ul>
        {error ? (
          <p role="alert" className="mt-4 text-sm font-medium text-red-600 dark:text-red-400">
            {error}
          </p>
        ) : null}
        {notice ? (
          <p role="status" className="mt-4 text-sm font-medium">
            {notice}
          </p>
        ) : null}
      </div>
    </div>
  );
}
