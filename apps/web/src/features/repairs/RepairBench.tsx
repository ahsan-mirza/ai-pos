import { formatMoney, type RepairBoard, type RepairBoardCard } from "@ai-pos/shared-types";
import { useEffect, useState } from "react";
import { apiGet } from "../../lib/api";
import { message } from "../customers/api";

const columnLabel: Record<string, string> = {
  intake: "Intake",
  diagnosing: "Diagnosing",
  awaiting_approval: "Approval",
  in_repair: "On the bench",
  waiting_parts: "Waiting for parts",
  ready: "Ready",
};

const priorityClass: Record<RepairBoardCard["priority"], string> = {
  URGENT: "bg-accent text-white",
  HIGH: "bg-accent/10 text-accent",
  NORMAL: "bg-surface text-charcoal/70",
  LOW: "bg-neutral text-charcoal/60",
};

/** Technician kanban. Cards open the same ticket drawer as the list. */
export function RepairBench({ onOpen }: { onOpen: (id: string) => void }) {
  const [board, setBoard] = useState<RepairBoard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<RepairBoard>("/api/v1/repairs/board")
      .then(setBoard)
      .catch((caught: unknown) => setError(message(caught, "Could not load the bench.")));
  }, []);

  if (error) return <p className="text-sm text-accent">{error}</p>;
  if (board === null) return <p className="text-sm text-charcoal/60">Loading the bench…</p>;

  return (
    <div className="flex gap-3 overflow-x-auto pb-2">
      {board.columns.map((column) => (
        <section key={column.status} className="w-64 shrink-0 rounded-2xl bg-surface p-3">
          <h3 className="mb-2 flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-charcoal/50">
            {columnLabel[column.status] ?? column.status}
            <span>{column.cards.length}</span>
          </h3>
          <div className="space-y-2">
            {column.cards.map((card) => (
              <button
                key={card.id}
                type="button"
                onClick={() => onOpen(card.id)}
                className="block w-full rounded-xl border border-line bg-white p-3 text-left hover:border-accent"
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[11px] text-charcoal/50">{card.reference}</span>
                  {card.priority !== "NORMAL" ? (
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${priorityClass[card.priority]}`}>
                      {card.priority}
                    </span>
                  ) : null}
                </span>
                <span className="mt-1 block text-sm font-semibold">{card.device_model}</span>
                <span className="block truncate text-xs text-charcoal/60">{card.customer_name}</span>
                <span className="mt-2 flex flex-wrap gap-1 text-[10px] font-semibold uppercase">
                  {card.parts_short ? <span className="rounded-full bg-accent/10 px-2 py-0.5 text-accent">Parts short</span> : null}
                  {card.approval_status === "PENDING" ? (
                    <span className="rounded-full bg-surface px-2 py-0.5 text-charcoal/70">Estimate out</span>
                  ) : null}
                  {card.overdue ? <span className="rounded-full bg-accent px-2 py-0.5 text-white">Overdue</span> : null}
                  {card.deposit_held_cents > 0 ? (
                    <span className="rounded-full bg-surface px-2 py-0.5 text-charcoal/70">
                      {formatMoney(card.deposit_held_cents, card.currency)} held
                    </span>
                  ) : null}
                </span>
                {card.technician_name ? <span className="mt-2 block text-xs text-charcoal/50">{card.technician_name}</span> : null}
              </button>
            ))}
            {column.cards.length === 0 ? <p className="px-1 py-4 text-center text-xs text-charcoal/40">Empty</p> : null}
          </div>
        </section>
      ))}
    </div>
  );
}
