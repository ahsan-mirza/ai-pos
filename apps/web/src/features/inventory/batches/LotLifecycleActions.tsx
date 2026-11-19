import { Capability, Permission, type BatchItem } from "@ai-pos/shared-types";
import { useEffect, useState } from "react";
import { useAuth } from "../../../lib/auth";
import { useCapability } from "../../../lib/capabilities";
import { apiGet, apiPost } from "../../../lib/api";
import { message } from "../api";

interface LotEvent {
  action: string;
  from_status: string | null;
  to_status: string | null;
  reason: string | null;
  user_name: string | null;
  created_at: string;
}

type Mode = "quarantine" | "return" | "recall" | "release" | "clear";

/** Lot actions for one medicine layer. Release is shown only to an appointed pharmacist. */
export function LotLifecycleActions({ item, onDone }: { item: BatchItem; onDone: () => void }) {
  const pharmacy = useCapability(Capability.PharmacyCatalog);
  const { can } = useAuth();
  const [mode, setMode] = useState<Mode | null>(null);
  const [reason, setReason] = useState("");
  const [reference, setReference] = useState("");
  const [severity, setSeverity] = useState("");
  const [quantity, setQuantity] = useState(String(item.quantity_remaining));
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [authorized, setAuthorized] = useState(false);
  const [events, setEvents] = useState<LotEvent[]>([]);
  const visible = pharmacy && can(Permission.PortalInventoryManage) && Boolean(item.lot_status);

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    void apiGet<{ authorized: boolean }>("/api/v1/pharmacy/pharmacist-authorization")
      .then((row) => {
        if (!cancelled) setAuthorized(row.authorized);
      })
      .catch(() => {
        if (!cancelled) setAuthorized(false);
      });
    void apiGet<LotEvent[]>(`/api/v1/pharmacy/lots/${item.id}/events`)
      .then((rows) => {
        if (!cancelled) setEvents(rows);
      })
      .catch(() => {
        if (!cancelled) setEvents([]);
      });
    return () => {
      cancelled = true;
    };
  }, [visible, item.id, item.lot_status]);

  if (!visible) return null;
  const history = events.length > 0 ? (
    <ul className="mt-1 space-y-0.5 text-[11px] text-charcoal/55">
      {events.map((event) => (
        <li key={`${event.created_at}-${event.action}-${event.to_status ?? ""}`}>
          {event.action.replace(/_/g, " ").toLowerCase()}
          {event.to_status ? ` → ${event.to_status.replace(/_/g, " ").toLowerCase()}` : ""}
          {event.user_name ? ` · ${event.user_name}` : ""}
          {event.reason ? ` · ${event.reason}` : ""}
        </li>
      ))}
    </ul>
  ) : null;
  const closed = item.lot_status === "SUPPLIER_RETURN";
  if (item.quantity_remaining <= 0) {
    return (
      <div className="mt-1">
        <p className="text-[11px] text-charcoal/55">
          {closed
            ? "Returned to the supplier. This layer has no stock left and cannot be sold."
            : "This layer has no stock left."}
        </p>
        {history}
      </div>
    );
  }
  const recalled = item.lot_status === "RECALLED";
  const unreleased = item.lot_status === "UNRELEASED";
  const quarantined = item.lot_status === "QUARANTINED";
  const needsPharmacist = unreleased || quarantined;

  const submit = async () => {
    setPending(true);
    setError(null);
    try {
      if (mode === "quarantine") {
        await apiPost(`/api/v1/pharmacy/lots/${item.id}/quarantine`, { reason: reason.trim() });
      } else if (mode === "return") {
        await apiPost("/api/v1/pharmacy/supplier-returns", {
          reference: reference.trim(),
          reason: reason.trim(),
          lines: [{ batch_item_id: item.id, quantity: Number(quantity) }],
        });
      } else if (mode === "recall" && item.manufacturer_lot) {
        await apiPost("/api/v1/pharmacy/recalls", {
          reference: reference.trim(),
          source_text: reason.trim(),
          severity: severity.trim(),
          reason: reason.trim(),
          lots: [{ product_id: item.product_id, manufacturer_lot: item.manufacturer_lot }],
        });
      } else if (mode === "release" || mode === "clear") {
        const path = mode === "release" ? "release" : "clear-quarantine";
        await apiPost(`/api/v1/pharmacy/lots/${item.id}/${path}`, { reason: reason.trim(), confirm: true });
      }
      setMode(null);
      setReason("");
      setReference("");
      setConfirm(false);
      onDone();
    } catch (caught) {
      setError(message(caught, "The lot could not be updated."));
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="mt-1">
      {item.released_at ? (
        <span className="block text-[11px] text-charcoal/55">
          Released {item.released_at.slice(0, 16).replace("T", " ")}
          {item.released_by_name ? ` by ${item.released_by_name}` : ""}
        </span>
      ) : null}
      <div className="flex flex-wrap gap-1">
        {authorized && unreleased ? (
          <button type="button" className="text-[11px] font-semibold text-charcoal/70 underline" onClick={() => setMode("release")}>
            Release lot
          </button>
        ) : null}
        {authorized && quarantined ? (
          <button type="button" className="text-[11px] font-semibold text-charcoal/70 underline" onClick={() => setMode("clear")}>
            Clear quarantine
          </button>
        ) : null}
        {!recalled && !quarantined && !closed ? (
          <button type="button" className="text-[11px] font-semibold text-charcoal/70 underline" onClick={() => setMode("quarantine")}>
            Quarantine
          </button>
        ) : null}
        {!closed ? (
          <button type="button" className="text-[11px] font-semibold text-charcoal/70 underline" onClick={() => setMode("return")}>
            Return to supplier
          </button>
        ) : null}
        {item.manufacturer_lot && !closed ? (
          <button type="button" className="text-[11px] font-semibold text-charcoal/70 underline" onClick={() => setMode("recall")}>
            Recall lot
          </button>
        ) : null}
      </div>
      {!authorized && needsPharmacist ? (
        <p className="mt-1 text-[11px] text-charcoal/55">Release and quarantine clearance require an authorized pharmacist.</p>
      ) : null}
      {history}
      {mode ? (
        <form
          className="mt-1 space-y-1"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          {mode === "recall" ? (
            <input
              aria-label="Severity"
              value={severity}
              onChange={(event) => setSeverity(event.target.value)}
              placeholder="Severity"
              className="h-8 w-full rounded border border-line px-2 text-[12px]"
            />
          ) : null}
          {mode !== "quarantine" && mode !== "release" && mode !== "clear" ? (
            <input
              aria-label="Reference"
              value={reference}
              onChange={(event) => setReference(event.target.value)}
              placeholder="Reference"
              className="h-8 w-full rounded border border-line px-2 text-[12px]"
            />
          ) : null}
          {mode === "return" ? (
            <input
              aria-label="Quantity to return"
              inputMode="numeric"
              value={quantity}
              onChange={(event) => setQuantity(event.target.value.replace(/\D/g, ""))}
              className="h-8 w-full rounded border border-line px-2 text-[12px]"
            />
          ) : null}
          <input
            aria-label="Reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Reason"
            className="h-8 w-full rounded border border-line px-2 text-[12px]"
          />
          {mode === "release" || mode === "clear" ? (
            <label className="flex items-center gap-1 text-[11px] text-charcoal/70">
              <input type="checkbox" checked={confirm} onChange={(event) => setConfirm(event.target.checked)} />
              I confirm this {mode === "release" ? "release" : "clearance"}
            </label>
          ) : null}
          {error ? <p className="text-[11px] text-red-600">{error}</p> : null}
          <button
            type="submit"
            disabled={pending || ((mode === "release" || mode === "clear") && (!confirm || reason.trim().length < 3))}
            className="text-[11px] font-semibold text-accent"
          >
            {pending ? "Saving…" : "Confirm"}
          </button>
        </form>
      ) : null}
    </div>
  );
}
