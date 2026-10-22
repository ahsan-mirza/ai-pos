import type { DeliveryNote } from "@ai-pos/shared-types";
import { CircleCheck, MapPin, Truck } from "lucide-react";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { ErrorNote } from "../../components/ui/Field";
import { formatDate } from "../inventory/shared";
import { errorMessage } from "../users/api";
import { salesOrdersApi } from "./api";
import { DeliverForm } from "./SalesOrderDetail";

/** The driver's phone page: what is on the van for this drop, then the customer signs for it. */
export function DeliveryPodPage() {
  const { noteId = "" } = useParams();
  const [note, setNote] = useState<DeliveryNote | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void salesOrdersApi
      .delivery(noteId)
      .then(setNote)
      .catch((caught: unknown) => setError(errorMessage(caught, "Could not load the delivery.")));
  }, [noteId]);

  return (
    <main className="mx-auto min-h-screen max-w-md bg-canvas p-4">
      <header className="mb-4 rounded-card bg-charcoal p-5 text-white">
        <p className="flex items-center gap-2 text-xs uppercase tracking-wider text-white/60">
          <Truck size={14} aria-hidden="true" /> Delivery
        </p>
        <h1 className="mt-2 font-mono text-2xl font-semibold">{note?.number ?? "…"}</h1>
        {note ? (
          <>
            <p className="mt-1 text-sm text-white/80">
              {note.customer_name} · order {note.order_number}
            </p>
            {note.delivery_address ? (
              <p className="mt-2 flex items-start gap-1.5 text-sm text-white/70">
                <MapPin size={14} aria-hidden="true" className="mt-0.5 shrink-0" /> {note.delivery_address}
              </p>
            ) : null}
          </>
        ) : null}
      </header>
      <ErrorNote message={error} />
      {note ? (
        <section className="rounded-card border border-line bg-white p-5">
          {note.status === "DELIVERED" ? (
            <div className="py-6 text-center">
              <CircleCheck size={36} aria-hidden="true" className="mx-auto text-accent" />
              <p className="mt-3 text-lg font-semibold">Signed for</p>
              <p className="mt-1 text-sm text-charcoal/60">
                {note.receiver_name}
                {note.delivered_at ? `, ${formatDate(note.delivered_at)}` : ""}
              </p>
            </div>
          ) : (
            <DeliverForm note={note} onDone={setNote} />
          )}
        </section>
      ) : null}
    </main>
  );
}
