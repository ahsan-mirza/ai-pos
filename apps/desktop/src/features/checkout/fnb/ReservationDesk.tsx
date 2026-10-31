import { useEffect, useState } from "react";
import { OrderRequestError, call } from "../../orders/ordersClient";

interface ReservationCard {
  id: string;
  customer_name: string;
  customer_phone: string | null;
  guest_count: number;
  status: string;
  table_label: string | null;
  starts_at: string;
  special_requests: string | null;
}

/** Today's bookings on the register. Seating uses the same open order as the floor. */
export function ReservationDesk({ storeId }: { storeId: string }) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<ReservationCard[]>([]);
  const [hidden, setHidden] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const start = new Date();
    start.setHours(0, 0, 0, 0);
    const end = new Date(start);
    end.setDate(end.getDate() + 1);
    const path =
      `/api/v1/reservations?store_id=${storeId}` +
      `&starts_from=${encodeURIComponent(start.toISOString())}` +
      `&starts_to=${encodeURIComponent(end.toISOString())}`;
    void call<ReservationCard[]>("GET", path)
      .then((list) => {
        setRows(list.filter((row) => row.status === "confirmed" || row.status === "arrived" || row.status === "seated"));
        setNotice(null);
      })
      .catch((caught: unknown) => {
        if (caught instanceof OrderRequestError && caught.code === "reservations_unavailable") setHidden(true);
        else setNotice(caught instanceof Error ? caught.message : "Reservations could not be loaded.");
      });
  }, [open, storeId]);

  if (hidden) return null;

  async function act(id: string, action: "arrive" | "seat") {
    try {
      const result = await call<{ table_label?: string }>("POST", `/api/v1/reservations/${id}/${action}`, {});
      setNotice(action === "seat" ? `Seated at ${result.table_label ?? "the table"}. Open that table to order.` : "Marked arrived.");
      setOpen(false);
    } catch (caught) {
      setNotice(caught instanceof Error ? caught.message : "That reservation could not be updated.");
    }
  }

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-3 dark:border-zinc-700 dark:bg-zinc-900">
      <button type="button" className="text-sm font-semibold text-zinc-900 dark:text-zinc-100" onClick={() => setOpen((value) => !value)}>
        Reservations
      </button>
      {notice ? <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-300">{notice}</p> : null}
      {open ? (
        <ul className="mt-2 space-y-2">
          {rows.map((row) => (
            <li key={row.id} className="rounded-lg border border-zinc-200 px-2 py-2 text-sm dark:border-zinc-700">
              <p className="font-medium">
                {row.customer_name} · {row.guest_count} · {row.table_label ?? "No table"}
              </p>
              <p className="text-xs text-zinc-500">
                {new Date(row.starts_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })} · {row.status}
                {row.special_requests ? " · Request" : ""}
                {row.customer_phone ? ` · ${row.customer_phone}` : ""}
              </p>
              <div className="mt-1 flex gap-2">
                {row.status === "confirmed" ? (
                  <button type="button" className="text-xs font-medium text-sky-700" onClick={() => void act(row.id, "arrive")}>
                    Arrived
                  </button>
                ) : null}
                {row.status === "arrived" ? (
                  <button type="button" className="text-xs font-medium text-emerald-700" onClick={() => void act(row.id, "seat")}>
                    Seat
                  </button>
                ) : null}
              </div>
            </li>
          ))}
          {rows.length === 0 ? <li className="text-xs text-zinc-500">No active reservations today.</li> : null}
        </ul>
      ) : null}
    </div>
  );
}
