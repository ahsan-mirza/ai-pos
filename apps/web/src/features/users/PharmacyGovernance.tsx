import { Capability, type User } from "@ai-pos/shared-types";
import { useEffect, useState } from "react";
import { useCapability } from "../../lib/capabilities";
import { apiGet, apiPost } from "../../lib/api";
import { errorMessage } from "./api";

interface GovernanceItem {
  user_id: string;
  user_name: string;
  status: string;
  requested_by_name: string;
  can_decide: boolean;
}

interface AuthorizationHistory {
  id: string;
  user_name: string;
  status: string;
  requested_at: string;
  requested_by_name: string;
  approved_at: string | null;
  approved_by_name: string;
  revoked_at: string | null;
  revoked_by_name: string;
  revocation_reason: string | null;
  rejected_at: string | null;
  rejection_reason: string | null;
}

interface GovernanceView {
  established: boolean;
  viewer_is_officer: boolean;
  can_nominate: boolean;
  officers: GovernanceItem[];
  appointments: GovernanceItem[];
  appointment_history: AuthorizationHistory[];
}

function when(value: string | null): string {
  return value ? value.slice(0, 16).replace("T", " ") : "not recorded";
}

/** Pharmacy appointment governance. Hidden for every other business profile. */
export function PharmacyGovernance({ users }: { users: User[] }) {
  const pharmacy = useCapability(Capability.PharmacyCatalog);
  const [view, setView] = useState<GovernanceView | null>(null);
  const [hidden, setHidden] = useState(false);
  const [userId, setUserId] = useState("");
  const [reason, setReason] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const load = () => {
    void apiGet<GovernanceView>("/api/v1/pharmacy/governance")
      .then((next) => {
        setView({ ...next, appointment_history: next.appointment_history ?? [] });
        setHidden(false);
      })
      .catch((caught) => {
        setView(null);
        setHidden(true);
        setError(errorMessage(caught, "Appointment governance is not available for this account."));
      });
  };

  useEffect(() => {
    if (!pharmacy) return;
    load();
  }, [pharmacy]);

  if (!pharmacy) return null;
  if (hidden || view === null) {
    return (
      <section className="rounded-card border border-line bg-white p-6">
        <h2 className="text-sm font-semibold">Pharmacy appointment</h2>
        <p className="mt-2 text-[13px] text-charcoal/60">
          Appointment governance is not available for this account.
        </p>
      </section>
    );
  }

  const send = async (path: string) => {
    setPending(true);
    setError(null);
    try {
      await apiPost(path, { user_id: userId || undefined, reason: reason.trim(), confirm: true });
      setReason("");
      setConfirm(false);
      setUserId("");
      load();
    } catch (caught) {
      setError(errorMessage(caught, "The appointment could not be saved."));
    } finally {
      setPending(false);
    }
  };

  const decide = async (path: string) => {
    setPending(true);
    setError(null);
    try {
      await apiPost(path, { reason: reason.trim() || "Recorded decision", confirm: true });
      setReason("");
      setConfirm(false);
      load();
    } catch (caught) {
      setError(errorMessage(caught, "The decision could not be saved."));
    } finally {
      setPending(false);
    }
  };

  return (
    <section className="rounded-card border border-line bg-white p-6">
      <h2 className="text-sm font-semibold">Pharmacy appointment</h2>
      <p className="mt-2 text-[13px] text-charcoal/60">
        {view.established
          ? "A governance officer requests a pharmacist appointment. A different officer approves it. This is not a licence check."
          : "Two different users who manage roles nominate and confirm two governance officers. One account cannot do both steps."}
      </p>
      {view.can_nominate ? (
        <form
          className="mt-3 space-y-2"
          onSubmit={(event) => {
            event.preventDefault();
            void send("/api/v1/pharmacy/governance-officers");
          }}
        >
          <select
            aria-label="Staff member"
            value={userId}
            onChange={(event) => setUserId(event.target.value)}
            className="h-9 w-full rounded border border-line px-2 text-[13px]"
          >
            <option value="">Select a staff member</option>
            {users.map((user) => (
              <option key={user.id} value={user.id}>
                {user.full_name}
              </option>
            ))}
          </select>
          <input
            aria-label="Reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Reason"
            className="h-9 w-full rounded border border-line px-2 text-[13px]"
          />
          <label className="flex items-center gap-2 text-[12px] text-charcoal/70">
            <input type="checkbox" checked={confirm} onChange={(event) => setConfirm(event.target.checked)} />
            I confirm this {view.viewer_is_officer ? "appointment request" : "nomination"}
          </label>
          <div className="flex gap-3">
            {view.viewer_is_officer ? (
              <button
                type="button"
                disabled={pending || !confirm || reason.trim().length < 3 || userId === ""}
                className="text-[12px] font-semibold text-accent"
                onClick={() => void send("/api/v1/pharmacy/pharmacists")}
              >
                Request appointment
              </button>
            ) : null}
            <button
              type="submit"
              disabled={pending || !confirm || reason.trim().length < 3 || userId === ""}
              className="text-[12px] font-semibold text-accent"
            >
              Nominate officer
            </button>
          </div>
        </form>
      ) : null}
      <ul className="mt-3 space-y-2 text-[12px] text-charcoal/70">
        {view.officers.map((item) => (
          <li key={`officer-${item.user_id}`}>
            Officer {item.user_name || item.user_id} · {item.status.toLowerCase()} · requested by {item.requested_by_name}
            {item.can_decide && item.status === "PENDING" ? (
              <button
                type="button"
                className="ml-2 font-semibold text-accent"
                disabled={pending || reason.trim().length < 3}
                onClick={() => void decide(`/api/v1/pharmacy/governance-officers/${item.user_id}/confirm`)}
              >
                Confirm
              </button>
            ) : null}
            {item.can_decide && item.status === "ACTIVE" ? (
              <button
                type="button"
                className="ml-2 font-semibold text-charcoal/70"
                disabled={pending || reason.trim().length < 3}
                onClick={() => void decide(`/api/v1/pharmacy/governance-officers/${item.user_id}/revoke`)}
              >
                Revoke
              </button>
            ) : null}
          </li>
        ))}
        {view.appointments.map((item) => (
          <li key={`appointment-${item.user_id}`}>
            Pharmacist {item.user_name || item.user_id} · {item.status.toLowerCase()} · requested by {item.requested_by_name}
            {item.can_decide && item.status === "PENDING" ? (
              <>
                <button
                  type="button"
                  className="ml-2 font-semibold text-accent"
                  disabled={pending || reason.trim().length < 3}
                  onClick={() => void decide(`/api/v1/pharmacy/pharmacists/${item.user_id}/approve`)}
                >
                  Approve
                </button>
                <button
                  type="button"
                  className="ml-2 font-semibold text-charcoal/70"
                  disabled={pending || reason.trim().length < 3}
                  onClick={() => void decide(`/api/v1/pharmacy/pharmacists/${item.user_id}/reject`)}
                >
                  Reject
                </button>
              </>
            ) : null}
            {item.can_decide && item.status === "ACTIVE" ? (
              <button
                type="button"
                className="ml-2 font-semibold text-charcoal/70"
                disabled={pending || reason.trim().length < 3}
                onClick={() => void decide(`/api/v1/pharmacy/pharmacists/${item.user_id}/revoke`)}
              >
                Revoke
              </button>
            ) : null}
          </li>
        ))}
      </ul>
      <h3 className="mt-4 text-sm font-semibold">Authorization history</h3>
      <p className="mt-1 text-[12px] text-charcoal/60">
        Revoked and rejected appointments stay here. They are not reactivated. A new governed appointment is required.
      </p>
      <ul className="mt-2 space-y-2 text-[12px] text-charcoal/70">
        {view.appointment_history.length === 0 ? <li>No closed appointments.</li> : null}
        {view.appointment_history.map((item) => (
          <li key={item.id}>
            Pharmacist {item.user_name || "Unknown"} · {item.status.toLowerCase()} · requested {when(item.requested_at)} by{" "}
            {item.requested_by_name || "unknown"}
            {item.approved_at ? ` · approved ${when(item.approved_at)} by ${item.approved_by_name || "unknown"}` : ""}
            {item.revoked_at
              ? ` · revoked ${when(item.revoked_at)} by ${item.revoked_by_name || "unknown"} · ${item.revocation_reason || "no reason recorded"}`
              : ""}
            {item.rejected_at
              ? ` · rejected ${when(item.rejected_at)} · ${item.rejection_reason || "no reason recorded"}`
              : ""}
          </li>
        ))}
      </ul>
      {error ? <p className="mt-2 text-[12px] text-red-600">{error}</p> : null}
    </section>
  );
}
