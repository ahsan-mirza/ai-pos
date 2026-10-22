import { formatMoney, type TableStatus } from "@ai-pos/shared-types";
import { TableGridNode, tableCapacityLabel, tableDisplayNumber } from "@ai-pos/ui";
import { useEffect, useState } from "react";
import { useTableAlertFor } from "../features/alerts/TableAlertContext";

/** Responsive table picker. Cards fill the row instead of sitting on a fixed floor-plan cell. */
export const floorTableGridClass = "grid grid-cols-2 gap-4 p-4 md:grid-cols-3 lg:grid-cols-4";

function minutesSince(iso: string | null, now: number): number {
  return iso ? Math.max(0, Math.floor((now - new Date(iso).getTime()) / 60_000)) : 0;
}

/** One table in the choose-a-table grid: vacant cards stay quiet, occupied cards show the running bill. */
export function FloorTableCard({
  tableId = null,
  label,
  seats,
  covers,
  seatedAt,
  openCents,
  currency,
  status,
  selected = false,
  disabled = false,
  onClick,
}: {
  tableId?: string | null;
  label: string;
  seats: number;
  covers: number;
  seatedAt: string | null;
  openCents: number;
  currency: string;
  status: TableStatus;
  selected?: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  const [now, setNow] = useState(() => Date.now());
  const { alert, acknowledge } = useTableAlertFor(tableId);
  const vacant = status === "free" && alert === null;
  const glow = alert?.alert === "request-bill" ? "table-alert-bill" : alert ? "table-alert-waiter" : "";
  const badgeLabel = alert?.alert === "request-bill" ? "Bill Requested" : alert ? "Needs Assistance" : undefined;
  const badgeClassName =
    alert?.alert === "request-bill" ? "bg-blue-500/20 text-blue-200" : alert ? "bg-amber-500/20 text-amber-100" : undefined;

  useEffect(() => {
    if (vacant || !seatedAt) return;
    const timer = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, [seatedAt, vacant]);

  return (
    <TableGridNode
      label={label}
      seats={seats}
      status={status}
      minutes={status === "free" ? null : minutesSince(seatedAt, now)}
      total={status === "free" ? null : formatMoney(openCents, currency)}
      selected={selected}
      disabled={disabled}
      className={glow}
      badgeLabel={badgeLabel}
      badgeClassName={badgeClassName}
      ariaLabel={
        status === "free"
          ? `${tableDisplayNumber(label)}, ${badgeLabel ?? "Available"}, ${tableCapacityLabel(seats)}`
          : `${tableDisplayNumber(label)}, ${badgeLabel ?? (status === "bill" ? "Billed" : "Occupied")}, ${tableCapacityLabel(seats)}, ${Math.max(covers, 0)} guests`
      }
      onClick={onClick}
    >
      {alert ? (
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            acknowledge();
          }}
          className="mt-3 self-start rounded-full bg-white/15 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-white/25"
        >
          Acknowledge
        </button>
      ) : null}
    </TableGridNode>
  );
}
