import type { TableStatus } from "@ai-pos/shared-types";
import { tableDisplayNumber, tableFootprint, type KitchenPhase, type OrderPhase, type PaymentPhase, type TableShape } from "@ai-pos/ui";

export interface TableChoice {
  key: string;
  id: string | null;
  areaId: string;
  label: string;
  seats: number;
  busy: boolean;
  shape: TableShape;
  active: boolean;
  x: number;
  y: number;
  w: number;
  h: number;
  status: TableStatus;
  covers: number;
  seatedAt: string | null;
  openCents: number;
  orderId: string | null;
  orderNumber: number | null;
  guestName: string | null;
  kitchen: KitchenPhase;
  payment: PaymentPhase;
  orderProgress: OrderPhase;
  search: string;
}

/** Places unnamed fallback tables on a floor so they use the same shape as a real floor plan. */
export function layoutFallback(labels: string[]): TableChoice[] {
  let x = 0;
  let y = 0;
  let rowHeight = 0;
  return labels.map((label) => {
    const footprint = tableFootprint("square", 4);
    if (x > 0 && x + footprint.w > 8) {
      x = 0;
      y += rowHeight;
      rowHeight = 0;
    }
    const table: TableChoice = {
      key: label,
      id: null,
      areaId: "floor",
      label,
      seats: 4,
      busy: false,
      shape: "square",
      active: true,
      x,
      y,
      w: footprint.w,
      h: footprint.h,
      status: "free",
      covers: 0,
      seatedAt: null,
      openCents: 0,
      orderId: null,
      orderNumber: null,
      guestName: null,
      kitchen: "none",
      payment: "none",
      orderProgress: "none",
      search: tableDisplayNumber(label),
    };
    x += footprint.w;
    rowHeight = Math.max(rowHeight, footprint.h);
    return table;
  });
}

