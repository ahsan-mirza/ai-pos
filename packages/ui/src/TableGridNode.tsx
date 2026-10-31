import type { ReactNode } from "react";
import { DiningTableShape, type TableShape } from "./DiningTableShape";
import {
  KITCHEN_LABEL,
  PAYMENT_LABEL,
  tableTone,
  toneLabel,
  type KitchenPhase,
  type OrderPhase,
  type PaymentPhase,
  type TableTone,
} from "./floorStatus";

export type TableNodeTone = TableTone;

/** Maps a floor status onto a card color when kitchen and payment are not supplied. */
export function tableNodeTone(status: string): TableNodeTone {
  return tableTone({
    active: true,
    status,
    kitchen: "none",
    payment: status === "bill" ? "pending" : "none",
    orderProgress: status === "free" ? "none" : "draft",
  });
}

/** "4" and "T4" become "T-04". Named tables keep their label. */
export function tableDisplayNumber(label: string): string {
  const digits = /^(?:t-?)?(\d+)$/i.exec(label.trim());
  if (digits?.[1]) return `T-${digits[1].padStart(2, "0")}`;
  return label.trim();
}

/** Elapsed seating time: "35m", "4h 34m", "11h". */
export function formatSeatedDuration(minutes: number): string {
  const total = Math.max(0, Math.floor(minutes));
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  if (hours === 0) return `${rest}m`;
  if (rest === 0) return `${hours}h`;
  return `${hours}h ${rest}m`;
}

/** Size band plus seat count, e.g. "Medium · 6 Person". */
export function tableCapacityLabel(seats: number): string {
  const count = Math.max(0, Math.round(seats));
  const size = count <= 4 ? "Small" : count <= 6 ? "Medium" : "Large";
  return `${size} · ${count} Person`;
}

function graphicSeats(seats: number): 2 | 4 | 6 | 8 {
  if (seats <= 2) return 2;
  if (seats <= 4) return 4;
  if (seats <= 6) return 6;
  return 8;
}

/** Miniature top-down table. The tabletop, border, and chair outlines take the status color. */
export function TableSeatGraphic({
  seats,
  tone,
  shape = "square",
  size = 72,
  guests = 0,
}: {
  seats: number;
  tone: TableNodeTone;
  shape?: TableShape;
  size?: number;
  guests?: number;
}) {
  const shown = graphicSeats(seats);
  const seated = Math.max(0, Math.min(shown, guests));
  return (
    <span
      className="relative block shrink-0"
      style={{ width: size, height: size, ["--table-tone-fill" as string]: `var(--table-${tone}-fill)`, ["--table-tone-line" as string]: `var(--table-${tone}-line)` }}
      aria-hidden="true"
    >
      <DiningTableShape
        shape={shape}
        seats={shown}
        width={size}
        height={size}
        occupied={seated}
        topClassName="border-2 border-[var(--table-tone-line)] bg-[var(--table-tone-fill)]"
        chairClassName="border border-[var(--table-tone-line)] bg-[var(--table-chair-fill)]"
        occupiedChairClassName="border border-[var(--table-tone-line)] bg-[var(--table-tone-fill)]"
      />
    </span>
  );
}

/** Measured height of the current floor card. Status changes color, not this box. */
const CARD_HEIGHT = "h-[167px]";
export function TableGridNode({
  label,
  seats,
  status,
  minutes,
  total,
  shape = "square",
  active = true,
  kitchen = "none",
  payment = "none",
  orderProgress = "none",
  orderRef = null,
  guestName = null,
  covers = 0,
  readyCount = 0,
  sentCount = 0,
  selected = false,
  disabled = false,
  className = "",
  badgeLabel,
  ariaLabel,
  onClick,
  children,
}: {
  label: string;
  seats: number;
  status: string;
  minutes: number | null;
  total: string | null;
  shape?: TableShape;
  active?: boolean;
  kitchen?: KitchenPhase;
  payment?: PaymentPhase;
  orderProgress?: OrderPhase;
  orderRef?: string | null;
  guestName?: string | null;
  covers?: number;
  /** Sent lines that are ready or already served, and how many lines are in the kitchen. */
  readyCount?: number;
  sentCount?: number;
  selected?: boolean;
  disabled?: boolean;
  className?: string;
  badgeLabel?: string;
  badgeClassName?: string;
  ariaLabel?: string;
  onClick: () => void;
  children?: ReactNode;
}) {
  const tone = tableTone({ active, status, kitchen, payment, orderProgress });
  const title = tableDisplayNumber(label);
  const capacity = tableCapacityLabel(seats);
  const headline = badgeLabel ?? toneLabel(tone);
  const occupancy = !active ? "Out of service" : status === "free" ? "Available" : "Occupied";
  const kitchenNote = kitchen !== "none" && KITCHEN_LABEL[kitchen] !== headline ? KITCHEN_LABEL[kitchen] : "";
  const paymentNote = payment !== "none" && PAYMENT_LABEL[payment] !== headline ? PAYMENT_LABEL[payment] : "";
  const progressNote = sentCount > 0 ? `${readyCount}/${sentCount} items ready` : "";
  const occupied = status !== "free" && active;
  const details = [occupancy !== headline ? occupancy : "", guestName, kitchenNote, paymentNote].filter(
    (part): part is string => Boolean(part),
  );
  const guestLabel = occupied && covers > 0 ? `${covers} ${covers === 1 ? "Guest" : "Guests"}` : "";

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-disabled={disabled || undefined}
      aria-pressed={selected}
      aria-label={
        ariaLabel ??
        `${title}, ${headline}, ${capacity}${orderRef ? `, ${orderRef}` : ""}${progressNote ? `, ${progressNote}` : ""}${details.length ? `, ${details.join(", ")}` : ""}`
      }
      onClick={() => {
        if (!disabled) onClick();
      }}
      onKeyDown={(event) => {
        if (disabled || event.target !== event.currentTarget) return;
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onClick();
        }
      }}
      style={{
        background: "var(--table-tone-fill)",
        color: "var(--table-card-ink)",
        borderColor: "var(--table-tone-line)",
        ["--table-tone-fill" as string]: `var(--table-${tone}-fill)`,
        ["--table-tone-line" as string]: `var(--table-${tone}-line)`,
        ["--table-tone-ink" as string]: `var(--table-${tone}-ink)`,
      }}
      className={`flex ${CARD_HEIGHT} w-full min-w-0 cursor-pointer flex-col gap-px overflow-hidden rounded-xl border-2 px-2.5 py-2 text-left shadow-sm transition-colors duration-200 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--primary)] active:scale-[0.98] ${className} ${
        selected ? "ring-2 ring-[var(--table-tone-line)]" : ""
      } ${disabled ? "cursor-not-allowed opacity-60 active:scale-100" : ""}`}
    >
      <span className="inline-flex h-5 max-w-full shrink-0 items-center self-start overflow-hidden rounded-full border border-[var(--table-tone-line)] bg-[var(--table-tone-fill)] px-2 text-[var(--table-tone-ink)]">
        <span className="truncate text-[11px] font-semibold leading-4">{headline}</span>
      </span>
      <span className="flex h-[72px] shrink-0 items-center justify-center">
        <TableSeatGraphic seats={seats} tone={tone} shape={shape} size={72} guests={occupied ? Math.max(covers, 1) : 0} />
      </span>
      <span className="flex min-w-0 shrink-0 flex-col">
        <span className="flex h-5 min-w-0 items-center gap-1">
          <span className="min-w-0 truncate text-base font-bold leading-5">{title}</span>
          {orderRef ? <span className="shrink-0 whitespace-nowrap text-xs font-semibold leading-4">{orderRef}</span> : null}
        </span>
        <span
          className="block h-4 min-w-0 truncate text-xs font-medium leading-4"
          style={{ color: "var(--table-card-muted)" }}
          title={occupied ? guestLabel || capacity : capacity}
        >
          {occupied ? guestLabel || capacity : capacity}
        </span>
      </span>
      <span className="mt-auto flex h-4 min-w-0 shrink-0 items-center justify-between gap-2 text-sm leading-4">
        {children ? (
          <span className="shrink-0">{children}</span>
        ) : (
          <span className="min-w-0 truncate" style={{ color: "var(--table-card-muted)" }}>
            {occupied && minutes !== null ? formatSeatedDuration(minutes) : ""}
          </span>
        )}
        {occupied && total ? (
          <span className="shrink-0 whitespace-nowrap font-bold tabular-nums text-[var(--table-tone-ink)]">{total}</span>
        ) : (
          <span className="shrink-0" />
        )}
      </span>
    </div>
  );
}
