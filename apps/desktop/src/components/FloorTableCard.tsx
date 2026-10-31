import { formatMoney, type DiningTable, type Order, type TableStatus } from "@ai-pos/shared-types";
import {
  aggregateService,
  tableCapacityLabel,
  tableDisplayNumber,
  TableGridNode,
  type KitchenPhase,
  type OrderPhase,
  type PaymentPhase,
  type TableShape,
} from "@ai-pos/ui";
import { useEffect, useState } from "react";
import { useTableAlertFor } from "../features/alerts/TableAlertContext";

export const floorTableGridClass = "grid grid-cols-[repeat(auto-fill,minmax(156px,1fr))] gap-2";

function minutesSince(iso: string | null, now: number): number {
  return iso ? Math.max(0, Math.floor((now - new Date(iso).getTime()) / 60_000)) : 0;
}

/** Prefer the live order when the register has one; otherwise use the floor snapshot. */
export function serviceOf(table: Pick<DiningTable, "kitchen" | "payment" | "order_progress" | "guest_name" | "kitchen_ready" | "kitchen_sent">, order?: Order | null): {
  kitchen: KitchenPhase;
  payment: PaymentPhase;
  orderProgress: OrderPhase;
  guestName: string | null;
  readyCount: number;
  sentCount: number;
} {
  if (!order) {
    return {
      kitchen: table.kitchen ?? "none",
      payment: table.payment ?? "none",
      orderProgress: table.order_progress ?? "none",
      guestName: table.guest_name ?? null,
      readyCount: table.kitchen_ready ?? 0,
      sentCount: table.kitchen_sent ?? 0,
    };
  }
  const live = order.items.filter((item) => item.voided_at === null);
  const sent = live.filter((item) => item.sent_at !== null);
  const paid = live.filter((item) => item.paid_sale_id !== null).length;
  return {
    ...aggregateService({
      sent: sent.length,
      marks: sent.flatMap((item) => (item.kitchen_status ? [item.kitchen_status] : [])),
      paid,
      unpaid: live.length - paid,
      billRequested: order.bill_requested_at !== null,
      hasItems: live.length > 0,
    }),
    guestName: order.name,
    readyCount: sent.filter((item) => item.kitchen_status === "ready" || item.kitchen_status === "bumped").length,
    sentCount: sent.length,
  };
}

/** One table in the choose-a-table grid. */
export function FloorTableCard({
  tableId = null,
  label,
  seats,
  shape = "square",
  active = true,
  covers,
  seatedAt,
  openCents,
  currency,
  status,
  kitchen = "none",
  payment = "none",
  orderProgress = "none",
  orderNumber = null,
  guestName = null,
  readyCount = 0,
  sentCount = 0,
  selected = false,
  disabled = false,
  onClick,
}: {
  tableId?: string | null;
  label: string;
  seats: number;
  shape?: TableShape;
  active?: boolean;
  covers: number;
  seatedAt: string | null;
  openCents: number;
  currency: string;
  status: TableStatus;
  kitchen?: KitchenPhase;
  payment?: PaymentPhase;
  orderProgress?: OrderPhase;
  orderNumber?: number | null;
  guestName?: string | null;
  readyCount?: number;
  sentCount?: number;
  selected?: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  const [now, setNow] = useState(() => Date.now());
  const { alert, acknowledge } = useTableAlertFor(tableId);
  const vacant = status === "free" && alert === null;
  const badgeLabel = alert?.alert === "request-bill" ? "Bill requested" : alert ? "Needs assistance" : undefined;

  useEffect(() => {
    if (vacant || !seatedAt) return;
    const timer = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, [seatedAt, vacant]);

  const occupied = status !== "free" && active;
  return (
    <TableGridNode
      label={label}
      seats={seats}
      shape={shape}
      active={active}
      status={alert?.alert === "request-bill" ? "bill" : status}
      kitchen={kitchen}
      payment={alert?.alert === "request-bill" ? "pending" : payment}
      orderProgress={orderProgress}
      orderRef={orderNumber !== null ? `#${orderNumber}` : null}
      guestName={guestName}
      covers={covers}
      readyCount={readyCount}
      sentCount={sentCount}
      minutes={occupied ? minutesSince(seatedAt, now) : null}
      total={occupied ? formatMoney(openCents, currency) : null}
      selected={selected}
      disabled={disabled || !active}
      badgeLabel={badgeLabel}
      className={alert ? "ring-2 ring-[var(--table-payment-line)]" : ""}
      ariaLabel={
        occupied
          ? `${tableDisplayNumber(label)}, ${badgeLabel ?? status}, ${tableCapacityLabel(seats)}, ${Math.max(covers, 0)} guests`
          : `${tableDisplayNumber(label)}, ${badgeLabel ?? (active ? "Available" : "Out of service")}, ${tableCapacityLabel(seats)}`
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
          className="inline-flex h-4 items-center rounded-full bg-[var(--table-tone-fill)] px-2 text-[11px] font-semibold leading-none text-[var(--table-tone-ink)]"
        >
          Acknowledge
        </button>
      ) : null}
    </TableGridNode>
  );
}
